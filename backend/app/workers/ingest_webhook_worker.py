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
    """Async wrapper that uses the standard ingestion pipeline for a single event.

    Creates a disposable engine with NullPool per invocation to avoid
    asyncio event-loop mismatch: Celery's ``asyncio.run()`` creates a new
    loop each call, but pooled asyncpg connections are bound to the loop
    that opened them.  NullPool opens a fresh connection each time and
    closes it immediately, eliminating cross-loop leaks.
    """
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings
    from app.workers.ingestion.base import AbstractIngestWorker

    class WebhookIngestWorker(AbstractIngestWorker):
        """Minimal ingest worker for HEC/webhook events."""

        ingestion_source: str = "hec"

        async def run(self) -> None:
            """Not used for single-event ingestion."""
            raise NotImplementedError

    # Disposable engine — no pool, no cross-loop leaks
    tmp_engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=settings.LOG_LEVEL == "DEBUG",
    )
    tmp_session_factory = async_sessionmaker(
        bind=tmp_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    valkey = aioredis.from_url(settings.VALKEY_URL, decode_responses=False)
    try:
        worker = WebhookIngestWorker(
            valkey_client=valkey,
            db_session_factory=tmp_session_factory,
        )
        inserted = await worker.ingest_batch(
            raw_events=[event],
            source_file_path="hec",
        )

        # Detection pipeline is chained automatically by ingest_batch()
        if inserted > 0:
            logger.info(
                "ingest_webhook_worker.inserted",
                action=event.get("action"),
                inserted=inserted,
            )

        return {"inserted": inserted}
    finally:
        await valkey.aclose()
        await tmp_engine.dispose()
