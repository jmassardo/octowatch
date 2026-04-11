"""Celery worker: ingest a single webhook event through the standard dedup pipeline."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

import structlog
from celery import Task

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.ingest_webhook_worker.ingest_webhook_event",
    bind=True,
    max_retries=3,
)
def ingest_webhook_event_task(self: Task, event: dict[str, Any]) -> dict[str, object]:
    """Ingest a single webhook event using the standard dedup + insert pipeline.

    The event dict has already been normalized by the webhook receiver router.
    This task runs the bloom filter + DB dedup and inserts the event if new.

    Args:
        event: Normalized event dict from the webhook receiver.

    Returns:
        Dict with status and insert count.
    """
    try:
        result = asyncio.run(_ingest_event(event))
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error(
            "ingest_webhook_worker.failed",
            action=event.get("action"),
            error=str(exc),
        )
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _ingest_event(event: dict[str, Any]) -> dict[str, object]:
    """Async wrapper that uses the standard ingestion pipeline for a single event."""
    import redis.asyncio as aioredis

    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.workers.ingestion.base import AbstractIngestWorker

    class WebhookIngestWorker(AbstractIngestWorker):
        """Minimal ingest worker for webhook events."""

        ingestion_source: str = "webhook"

        async def run(self) -> None:
            """Not used for single-event ingestion."""
            raise NotImplementedError

    valkey = aioredis.from_url(settings.VALKEY_URL, decode_responses=False)
    try:
        worker = WebhookIngestWorker(
            valkey_client=valkey,
            db_session_factory=AsyncSessionLocal,
        )
        inserted = await worker.ingest_batch(
            raw_events=[event],
            source_file_path="webhook",
        )

        # Chain detection pipeline if events were inserted
        if inserted > 0:
            logger.info(
                "ingest_webhook_worker.inserted",
                action=event.get("action"),
                inserted=inserted,
            )

        return {"inserted": inserted}
    finally:
        await valkey.aclose()
