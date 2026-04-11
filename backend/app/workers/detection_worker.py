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
def run_detection_pipeline_task(self: Task, event_ids: list[int]) -> dict[str, object]:
    """Celery task that runs the detection pipeline for a list of event IDs."""
    try:
        result = asyncio.run(_run_pipeline(event_ids))
        return {
            "status": "ok",
            "detections_written": result["detections_written"],
            "detection_ids": result["detection_ids"],
        }
    except Exception as exc:
        logger.error(
            "detection_worker.task_failed",
            event_ids=event_ids[:5],  # log first 5 only
            error=str(exc),
        )
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _run_pipeline(event_ids: list[int]) -> dict[str, object]:
    """Async wrapper so we can reuse the async detection_service from a Celery task."""
    from app.services.detection_service import run_detection_pipeline

    async with AsyncSessionLocal() as session:
        try:
            result = await run_detection_pipeline(session, event_ids=event_ids)
            await session.commit()

            detection_ids = result.detection_ids

            # Chain notification tasks for each new detection
            if detection_ids:
                try:
                    from app.workers.notification_worker import (
                        send_detection_notifications_task,
                    )

                    for det_id in detection_ids:
                        send_detection_notifications_task.delay(det_id)
                    logger.info(
                        "detection_worker.notifications_queued",
                        detection_count=len(detection_ids),
                    )
                except Exception as exc:
                    # Notification failures must not break the detection pipeline
                    logger.warning(
                        "detection_worker.notification_chain_failed",
                        error=str(exc),
                    )

            return {
                "detections_written": result.detections_written,
                "detection_ids": detection_ids,
            }
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


@celery_app.task(
    name="app.workers.detection_worker.sync_ticket_statuses",
    bind=True,
    max_retries=3,
)
def sync_ticket_statuses_task(self: Task) -> dict[str, object]:
    """Celery task that syncs ticket statuses from external ticketing platforms."""
    try:
        updated = asyncio.run(_sync_tickets())
        return {"status": "ok", "tickets_updated": updated}
    except Exception as exc:
        logger.error("detection_worker.sync_tickets_failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _sync_tickets() -> int:
    """Async wrapper for ticket status synchronization."""
    from app.services.ticketing_service import sync_ticket_statuses

    async with AsyncSessionLocal() as session:
        try:
            updated = await sync_ticket_statuses(session)
            await session.commit()
            return updated
        except Exception:
            await session.rollback()
            raise
