"""Detection Celery worker: run the detection pipeline on ingested event batches."""

from __future__ import annotations

import asyncio
import secrets
from typing import TYPE_CHECKING

import structlog
from celery import Task
from celery.signals import worker_process_shutdown

from app.celery_app import celery_app

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

logger = structlog.get_logger(__name__)

# Per-worker-process event loop + pooled engine for ``run_detection_pipeline_task``.
#
# The pipeline issues dozens of ad-hoc queries against the ``events``
# TimescaleDB hypertable (59+ chunks). Postgres' per-backend catalog/relcache
# is cold on a brand-new connection, so the *first* query against the
# hypertable on a fresh connection can take 150ms-1.2s to *plan* alone (vs.
# ~1-2ms once that backend has touched the table once). Opening a disposable
# ``NullPool`` connection per task (the previous approach) meant every task
# paid that cold-cache tax on every one of those queries, which is the
# dominant cost behind the pipeline's 40-65s per-task latency.
#
# Celery's prefork workers execute one task at a time per child process, so
# it's safe to create a single event loop + pooled engine lazily on first use
# and reuse both for every subsequent task in that process: there is no
# concurrent access to race on, and the backend connection(s) stay warm.
_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_engine: AsyncEngine | None = None
_worker_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_worker_loop_and_session_factory() -> tuple[
    asyncio.AbstractEventLoop, async_sessionmaker[AsyncSession]
]:
    """Return (creating once, lazily) this worker process's persistent loop + sessions."""
    global _worker_loop, _worker_engine, _worker_session_factory

    if _worker_loop is None:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings

        _worker_loop = asyncio.new_event_loop()
        _worker_engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=2,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=settings.LOG_LEVEL == "DEBUG",
        )
        _worker_session_factory = async_sessionmaker(
            bind=_worker_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    assert _worker_session_factory is not None
    return _worker_loop, _worker_session_factory


@worker_process_shutdown.connect
def _close_worker_loop(**_kwargs: object) -> None:
    """Dispose the persistent engine/loop when the Celery worker process exits."""
    global _worker_loop, _worker_engine, _worker_session_factory

    if _worker_loop is None:
        return
    try:
        if _worker_engine is not None:
            _worker_loop.run_until_complete(_worker_engine.dispose())
    finally:
        _worker_loop.close()
        _worker_loop = None
        _worker_engine = None
        _worker_session_factory = None


@celery_app.task(
    name="app.workers.detection_worker.run_detection_pipeline",
    bind=True,
    max_retries=3,
)
def run_detection_pipeline_task(
    self: Task,
    event_ids: list[int],
    since: str | None = None,
    until: str | None = None,
) -> dict[str, object]:
    """Celery task that runs the detection pipeline for a list of event IDs.

    ``since``/``until`` are optional ISO-8601 bounds (the exact min/max
    ``created_at`` of the batch) that let the DB query prune TimescaleDB
    chunks instead of scanning the entire hypertable by id alone.
    """
    try:
        loop, session_factory = _get_worker_loop_and_session_factory()
        result = loop.run_until_complete(_run_pipeline(session_factory, event_ids, since, until))
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


async def _run_pipeline(
    session_factory: async_sessionmaker[AsyncSession],
    event_ids: list[int],
    since: str | None = None,
    until: str | None = None,
) -> dict[str, object]:
    """Async wrapper so we can reuse the async detection_service from a Celery task.

    Uses this worker process's persistent, pooled session factory (see
    ``_get_worker_loop_and_session_factory``) so repeated tasks reuse warm
    connections instead of paying a cold-cache planning tax on every query.
    """
    from datetime import datetime

    from app.services.detection_service import run_detection_pipeline

    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None

    async with session_factory() as session:
        try:
            result = await run_detection_pipeline(
                session, event_ids=event_ids, since=since_dt, until=until_dt
            )
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

                # Chain SIEM export tasks for each new detection
                try:
                    from app.workers.siem_export_worker import (
                        export_detection_siem_task,
                    )

                    for det_id in detection_ids:
                        export_detection_siem_task.delay(det_id)
                    logger.info(
                        "detection_worker.siem_exports_queued",
                        detection_count=len(detection_ids),
                    )
                except Exception as exc:
                    # SIEM export failures must not break the detection pipeline
                    logger.warning(
                        "detection_worker.siem_export_chain_failed",
                        error=str(exc),
                    )

                # Chain automation dispatch tasks for each new detection
                try:
                    from app.workers.automation_worker import (
                        dispatch_automation_task,
                    )

                    for det_id in detection_ids:
                        dispatch_automation_task.delay(det_id)
                    logger.info(
                        "detection_worker.automation_queued",
                        detection_count=len(detection_ids),
                    )
                except Exception as exc:
                    # Automation failures must not break the detection pipeline
                    logger.warning(
                        "detection_worker.automation_chain_failed",
                        error=str(exc),
                    )

            # Chain workflow scanner for workflow-related events
            try:
                from app.workers.workflow_scan_worker import scan_workflow_events_task

                scan_workflow_events_task.delay(event_ids, since=since, until=until)
                logger.info(
                    "detection_worker.workflow_scan_chained",
                    event_count=len(event_ids),
                )
            except Exception as exc:
                logger.warning(
                    "detection_worker.workflow_scan_chain_failed",
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
    name="app.workers.detection_worker.run_detection_pipeline_after_ingest",
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
    from app.database import AsyncSessionLocal
    from app.services.ticketing_service import sync_ticket_statuses

    async with AsyncSessionLocal() as session:
        try:
            updated = await sync_ticket_statuses(session)
            await session.commit()
            return updated
        except Exception:
            await session.rollback()
            raise
