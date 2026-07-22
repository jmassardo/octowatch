"""Celery worker: dispatch detection-triggered automation (webhooks, repo_dispatch)."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

import structlog
from celery import Task

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.automation_worker.dispatch_automation",
    bind=True,
    max_retries=2,
)
def dispatch_automation_task(
    self: Task, detection_id: int, *, dry_run: bool = False
) -> dict[str, object]:
    """Dispatch automation targets for a single detection."""
    try:
        result = asyncio.run(_dispatch(detection_id, dry_run=dry_run))
        return {"status": "ok", "detection_id": detection_id, **result}
    except Exception as exc:
        logger.error(
            "automation_worker.dispatch_failed",
            detection_id=detection_id,
            error=str(exc),
        )
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


@celery_app.task(
    name="app.workers.automation_worker.retry_failed_deliveries",
    bind=True,
    max_retries=1,
)
def retry_failed_deliveries_task(self: Task) -> dict[str, object]:
    """Periodic task: retry failed automation deliveries."""
    try:
        result = asyncio.run(_retry_failed())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("automation_worker.retry_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60) from exc


async def _dispatch(detection_id: int, *, dry_run: bool = False) -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings
    from app.services.automation_service import dispatch_automation

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

    try:
        async with tmp_session_factory() as session:
            result = await dispatch_automation(session, detection_id, dry_run=dry_run)
            return result
    finally:
        await tmp_engine.dispose()


async def _retry_failed() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings
    from app.services.automation_service import retry_failed_deliveries

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

    try:
        async with tmp_session_factory() as session:
            result = await retry_failed_deliveries(session)
            return result
    finally:
        await tmp_engine.dispose()
