"""Celery worker: enforce retention policies for all managed tables.

Runs daily via Celery beat. For each table the worker deletes rows older than
the configured retention window.
"""

from __future__ import annotations

import asyncio
import secrets

import structlog
from celery import Task

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.retention_worker.enforce_all_retention_policies",
    bind=True,
    max_retries=3,
)
def enforce_all_retention_policies(self: Task) -> dict[str, object]:
    """Celery beat task: enforce retention on all time-series tables."""
    try:
        result = asyncio.run(_enforce_all())
        return {"status": "ok", "results": result}
    except Exception as exc:
        logger.error("retention_worker.failed", error=str(exc))
        backoff = min(60 * (2**self.request.retries), 1200)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _enforce_all() -> dict[str, int]:
    """Run inside an asyncio context: open a DB session and enforce retention."""
    from app.database import AsyncSessionLocal
    from app.services import retention_service

    async with AsyncSessionLocal() as db:
        results = await retention_service.enforce_all(
            db,
            archive_callback=None,
        )
        await db.commit()
        return results
