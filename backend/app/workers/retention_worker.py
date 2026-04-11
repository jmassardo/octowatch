"""Celery worker: enforce retention policies for all managed tables.

Runs daily via Celery beat.  For each table the worker:
1. (optionally) archives rows to S3/MinIO before deletion
2. deletes rows older than the configured retention window

Archive behaviour is controlled by the ``archive.enabled`` app setting.
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
    from app.services.settings_service import get_setting

    async with AsyncSessionLocal() as db:
        # Determine whether archival is enabled
        archive_enabled = (await get_setting(db, "archive.enabled") or "").lower() == "true"

        archive_callback = None
        if archive_enabled:
            archive_callback = await _build_archive_callback(db)

        results = await retention_service.enforce_all(
            db,
            archive_callback=archive_callback,
        )
        await db.commit()
        return results


async def _build_archive_callback(db: object) -> object:
    """Build an async callback that archives rows to S3 before deletion."""
    from app.services import archive_service
    from app.services.archive_service import get_archive_bucket, get_s3_client

    s3_client = get_s3_client()
    bucket = get_archive_bucket()

    async def _archive(inner_db: object, table_name: str, cutoff: object) -> None:
        from datetime import datetime

        from sqlalchemy.ext.asyncio import AsyncSession

        assert isinstance(inner_db, AsyncSession)
        assert isinstance(cutoff, datetime)
        await archive_service.archive_rows(
            inner_db,
            table_name,
            cutoff,
            s3_client=s3_client,
            bucket=bucket,
        )

    return _archive
