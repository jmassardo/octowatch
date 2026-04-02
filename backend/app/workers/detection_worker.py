"""Detection Celery worker: run the detection pipeline on ingested event batches."""

from __future__ import annotations

import asyncio
import secrets

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="workers.run_detection_pipeline",
    bind=True,
    max_retries=3,
)
def run_detection_pipeline_task(self: Task, event_ids: list[int]) -> dict:
    """Celery task that runs the detection pipeline for a list of event IDs."""
    try:
        result = asyncio.run(_run_pipeline(event_ids))
        return {"status": "ok", "detections_written": result}
    except Exception as exc:
        logger.error(
            "detection_worker.task_failed",
            event_ids=event_ids[:5],  # log first 5 only
            error=str(exc),
        )
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _run_pipeline(event_ids: list[int]) -> int:
    """Async wrapper so we can reuse the async detection_service from a Celery task."""
    from app.services.detection_service import run_detection_pipeline

    async with AsyncSessionLocal() as session:
        try:
            result = await run_detection_pipeline(session, event_ids=event_ids)
            await session.commit()
            return result.detections_written
        except Exception:
            await session.rollback()
            raise


@celery_app.task(
    name="workers.run_detection_pipeline_after_ingest",
    bind=True,
    max_retries=2,
)
def run_detection_after_ingest(self: Task, event_ids: list[int]) -> None:
    """Celery task chained after ingestion to trigger detection on fresh events."""
    run_detection_pipeline_task.delay(event_ids)
