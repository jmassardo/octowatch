"""Threat intel feed refresh worker: periodic fetch and upsert of indicators."""

from __future__ import annotations

import asyncio
import secrets
from typing import Any

import httpx
import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.threat_intel_worker.refresh_threat_intel_feeds",
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


def _build_auth_headers(parser_config: dict[str, Any] | None) -> dict[str, str]:
    """Build authentication headers from feed parser_config.

    Supports:
      - {"auth_token": "..."} → Authorization: Bearer ...
      - {"auth_header": "X-Api-Key", "auth_value": "..."} → X-Api-Key: ...
    """
    if not parser_config:
        return {}

    headers: dict[str, str] = {}

    if token := parser_config.get("auth_token"):
        headers["Authorization"] = f"Bearer {token}"
    elif header_name := parser_config.get("auth_header"):
        if header_value := parser_config.get("auth_value"):
            headers[header_name] = header_value

    return headers


async def _refresh_feeds() -> dict[str, object]:
    """Fetch all enabled feeds and upsert their indicators.

    Orchestrates the full adaptive feed pipeline:
    1. Fetch content (with auth headers if configured)
    2. Parse with the correct parser via fetch_feed_indicators
    3. Upsert indicators with campaign linking
    4. Synthesize rules (if auto_rule_generation enabled and new indicators)
    5. Trigger retro scan for newly-created rules
    6. Send notification about new threat intel
    """
    from sqlalchemy import text

    from app.services.threat_intel_service import fetch_feed_indicators

    feeds_processed = 0
    indicators_total = 0

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT id, url, feed_type, name,
                           parser_type, parser_config, default_campaign_id,
                           auto_rule_generation
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
                        # Build auth headers from parser_config
                        auth_headers = _build_auth_headers(feed.parser_config)

                        response = await client.get(feed.url, headers=auth_headers)
                        response.raise_for_status()
                        content = response.text

                        count = await fetch_feed_indicators(
                            session,
                            feed_id=feed.id,
                            content=content,
                            feed_type=feed.feed_type,
                            added_by="system:feed_refresh",
                            parser_type=feed.parser_type,
                            parser_config=feed.parser_config,
                            default_campaign_id=feed.default_campaign_id,
                            auto_rule_generation=feed.auto_rule_generation,
                        )
                        feeds_processed += 1
                        indicators_total += count

                        logger.info(
                            "threat_intel_worker.feed_refreshed",
                            feed_id=feed.id,
                            feed_name=feed.name,
                            indicators=count,
                            auto_rules=feed.auto_rule_generation,
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
