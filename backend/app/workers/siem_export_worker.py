"""SIEM export Celery worker: dispatch detection exports to configured SIEM destinations."""

from __future__ import annotations

import asyncio
import secrets

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.siem_export_worker.export_detection_siem",
    bind=True,
    max_retries=3,
)
def export_detection_siem_task(self: Task, detection_id: int) -> dict[str, object]:
    """Export a detection to all enabled SIEM/SOAR destinations.

    Loads the detection from the database and dispatches to all configured
    SIEM export destinations (syslog/CEF, Splunk HEC, SOAR webhooks).

    Args:
        detection_id: The ID of the detection to export.

    Returns:
        Dict with status and export counts.
    """
    try:
        result = asyncio.run(_export_detection(detection_id))
        return {"status": "ok", "detection_id": detection_id, **result}
    except Exception as exc:
        logger.error(
            "siem_export_worker.task_failed",
            detection_id=detection_id,
            error=str(exc),
        )
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _export_detection(detection_id: int) -> dict[str, object]:
    """Async wrapper that loads the detection and calls the SIEM export service."""
    from sqlalchemy import select

    from app.models.detection import Detection
    from app.services.siem_export_service import export_detection

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Detection).where(Detection.id == detection_id))
        detection = result.scalar_one_or_none()

        if detection is None:
            logger.warning(
                "siem_export_worker.detection_not_found",
                detection_id=detection_id,
            )
            return {"skipped": True, "reason": "detection_not_found"}

        export_result = await export_detection(session, detection)
        return {"skipped": False, **export_result}
