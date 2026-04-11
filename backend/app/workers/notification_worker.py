"""Notification Celery worker: dispatch alerts for new detections."""

from __future__ import annotations

import asyncio
import secrets

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.notification.send_detection_notifications",
    bind=True,
    max_retries=3,
)
def send_detection_notifications_task(self: Task, detection_id: int) -> dict[str, object]:
    """Send notifications for a single detection via all configured channels.

    Loads the Detection from the database and delegates to the notification
    service which handles Slack, email, and deduplication logic.
    """
    try:
        result = asyncio.run(_send_notifications(detection_id))
        return {"status": "ok", "detection_id": detection_id, **result}
    except Exception as exc:
        logger.error(
            "notification_worker.task_failed",
            detection_id=detection_id,
            error=str(exc),
        )
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _send_notifications(detection_id: int) -> dict[str, object]:
    """Async wrapper that loads the detection and calls the notification service."""
    import redis.asyncio as aioredis
    from sqlalchemy import select

    from app.config import settings
    from app.models.detection import Detection
    from app.services.notification_service import send_detection_notifications

    valkey = aioredis.from_url(settings.VALKEY_URL, decode_responses=True)
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Detection).where(Detection.id == detection_id))
            detection = result.scalar_one_or_none()

            if detection is None:
                logger.warning(
                    "notification_worker.detection_not_found",
                    detection_id=detection_id,
                )
                return {"skipped": True, "reason": "detection_not_found"}

            await send_detection_notifications(session, valkey, detection)
            return {"skipped": False}
    finally:
        await valkey.aclose()
