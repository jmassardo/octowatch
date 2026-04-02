"""Celery task for detecting ingestion gaps."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from sqlalchemy import text

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(name="app.workers.ingestion_health.check_ingestion_gaps")
def check_ingestion_gaps() -> dict[str, Any]:
    """Check for ingestion gaps and create system health events."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_check_gaps())
    finally:
        loop.close()


async def _check_gaps() -> dict[str, Any]:
    """Find orgs with no events in last 90 minutes and record warnings."""
    async with AsyncSessionLocal() as session:
        # Find orgs with no events in last 90 minutes
        result = await session.execute(
            text("""
                WITH org_last_event AS (
                    SELECT org, MAX(created_at) AS last_event_at
                    FROM events
                    WHERE created_at >= NOW() - INTERVAL '24 hours'
                      AND org IS NOT NULL
                    GROUP BY org
                )
                SELECT org, last_event_at,
                       EXTRACT(EPOCH FROM NOW() - last_event_at)::INT / 60 AS minutes_gap
                FROM org_last_event
                WHERE last_event_at < NOW() - INTERVAL '90 minutes'
            """)
        )
        gaps = [dict(row._mapping) for row in result.fetchall()]

        for gap in gaps:
            await session.execute(
                text("""
                    INSERT INTO system_health_events
                        (org, signal_type, severity, detail)
                    VALUES (
                        :org, 'ingestion_gap', 'warning',
                        jsonb_build_object(
                            'minutes_gap', :minutes_gap,
                            'last_event_at', :last_event_at::TEXT
                        )
                    )
                    ON CONFLICT DO NOTHING
                """),
                {
                    "org": gap["org"],
                    "minutes_gap": gap["minutes_gap"],
                    "last_event_at": gap["last_event_at"],
                },
            )

        await session.commit()
        logger.info("ingestion_gap.check_complete", gaps_found=len(gaps))
        return {"gaps_found": len(gaps), "orgs": [g["org"] for g in gaps]}
