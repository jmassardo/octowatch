"""Celery worker: aggregate evaluation for classification and utilization rules."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

import structlog
from celery import Task

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.aggregate_evaluator_worker.run_classification",
    bind=True,
    max_retries=2,
)
def run_classification_task(self: Task) -> dict[str, object]:
    """Daily: evaluate classification rules and assign personas."""
    try:
        result = asyncio.run(_run_classification())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("aggregate_evaluator.classification_failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


@celery_app.task(
    name="app.workers.aggregate_evaluator_worker.run_utilization_detection",
    bind=True,
    max_retries=2,
)
def run_utilization_detection_task(self: Task) -> dict[str, object]:
    """Every 15 min: evaluate utilization rules for anomaly detection."""
    try:
        result = asyncio.run(_run_utilization())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("aggregate_evaluator.utilization_failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _run_classification() -> dict[str, Any]:
    from app.database import AsyncSessionLocal
    from app.services.aggregate_evaluation import run_aggregate_evaluation

    async with AsyncSessionLocal() as db:
        result = await run_aggregate_evaluation(db, mode="classification")
        return result


async def _run_utilization() -> dict[str, Any]:
    from app.database import AsyncSessionLocal
    from app.services.aggregate_evaluation import run_aggregate_evaluation

    async with AsyncSessionLocal() as db:
        result = await run_aggregate_evaluation(db, mode="utilization")
        return result
