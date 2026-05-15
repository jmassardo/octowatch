"""Celery worker: daily user behavior classification.

Classifies users across all active orgs into behavioral personas based on
audit log event patterns.
"""

from __future__ import annotations

import asyncio
import secrets

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.user_classification_worker.classify_all_orgs",
    bind=True,
    max_retries=2,
)
def classify_all_orgs(self: Task) -> dict[str, object]:
    """Celery beat task: classify users for all orgs with recent activity."""
    try:
        result = asyncio.run(_classify_all())
        return {
            "status": "ok",
            "orgs_processed": result["orgs"],
            "users_classified": result["users"],
        }
    except Exception as exc:
        logger.error("user_classification_worker.task_failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _classify_all() -> dict[str, int]:
    """Classify users for all orgs that have recent events."""
    from sqlalchemy import text

    from app.services.user_classification_service import classify_users

    total_users = 0
    total_orgs = 0

    async with AsyncSessionLocal() as session:
        try:
            # Get distinct orgs with recent activity
            orgs_result = await session.execute(
                text("""
                    SELECT DISTINCT org
                    FROM events
                    WHERE org IS NOT NULL
                      AND created_at >= NOW() - INTERVAL '90 days'
                    LIMIT 500
                """)
            )
            orgs = [row[0] for row in orgs_result.fetchall()]

            for org in orgs:
                count = await classify_users(db=session, org=org, window_days=90)
                total_users += count
                total_orgs += 1

            await session.commit()
            logger.info(
                "user_classification_worker.complete",
                orgs_processed=total_orgs,
                users_classified=total_users,
            )
        except Exception:
            await session.rollback()
            raise

    return {"orgs": total_orgs, "users": total_users}
