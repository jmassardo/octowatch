"""Threat intel feed refresh worker: periodic fetch and upsert of indicators."""

from __future__ import annotations

import asyncio
import secrets

import httpx
import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="workers.refresh_threat_intel_feeds",
    bind=True,
    max_retries=2,
)
def refresh_threat_intel_feeds_task(self: Task) -> dict[str, object]:
    """Celery beat task: fetch all enabled threat intel feeds and upsert indicators."""
    try:
        result = asyncio.run(_refresh_feeds())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("threat_intel_worker.task_failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _refresh_feeds() -> dict[str, object]:
    """Fetch all enabled feeds and upsert their indicators."""
    from sqlalchemy import text

    from app.services.threat_intel_service import fetch_feed_indicators

    feeds_processed = 0
    indicators_total = 0

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT id, url, feed_type, name
                    FROM threat_intel_feeds
                    WHERE enabled = TRUE
                      AND (
                          last_fetched_at IS NULL
                          OR last_fetched_at + (refresh_interval_minutes || ' minutes')::interval
                             < NOW()
                      )
                """)
            )
            feeds = result.fetchall()

            async with httpx.AsyncClient(timeout=30.0) as client:
                for feed in feeds:
                    try:
                        response = await client.get(feed.url)
                        response.raise_for_status()
                        content = response.text

                        count = await fetch_feed_indicators(
                            session,
                            feed_id=feed.id,
                            content=content,
                            feed_type=feed.feed_type,
                            added_by="system:feed_refresh",
                        )
                        feeds_processed += 1
                        indicators_total += count

                        logger.info(
                            "threat_intel_worker.feed_refreshed",
                            feed_id=feed.id,
                            feed_name=feed.name,
                            indicators=count,
                        )
                    except Exception as exc:
                        logger.error(
                            "threat_intel_worker.feed_error",
                            feed_id=feed.id,
                            feed_name=feed.name,
                            error=str(exc),
                        )
                        await session.execute(
                            text("""
                                UPDATE threat_intel_feeds
                                SET last_fetched_at = NOW(),
                                    last_fetch_status = :status,
                                    updated_at = NOW()
                                WHERE id = :feed_id
                            """),
                            {"feed_id": feed.id, "status": f"error: {str(exc)[:200]}"},
                        )
                        await session.commit()

        except Exception:
            await session.rollback()
            raise

    return {"feeds_processed": feeds_processed, "indicators_total": indicators_total}
