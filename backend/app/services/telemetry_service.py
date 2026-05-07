"""Telemetry service: SQL queries for ingestion telemetry dashboard.

Provides real-time visibility into event ingestion pipeline health,
worker status, event volume trends, and ingestion errors.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def get_stream_status(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Per-org ingestion stream status for the last 24 hours."""
    result = await session.execute(
        text("""
            SELECT
                org,
                ingestion_source,
                MAX(created_at) AS last_event_at,
                COUNT(*) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '1 hour'
                ) AS events_last_hour,
                ROUND(
                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - INTERVAL '1 hour'
                    ) / 60.0,
                    2
                ) AS events_per_minute,
                AVG(
                    EXTRACT(EPOCH FROM ingested_at - created_at)
                ) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '1 hour'
                ) AS avg_latency_seconds,
                EXTRACT(MINUTES FROM NOW() - MAX(created_at))::INT
                    AS minutes_since_last
            FROM events
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY org, ingestion_source
            ORDER BY last_event_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_worker_health(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """System health events and active worker summaries."""
    health_result = await session.execute(
        text("""
            SELECT
                signal_type,
                severity,
                org,
                occurred_at,
                detail,
                resolved_at
            FROM system_health_events
            WHERE (org = ANY(:scoped_orgs) OR org IS NULL)
              AND (
                    signal_type LIKE 'worker.%'
                 OR signal_type LIKE 'ingestion.%'
                 OR signal_type LIKE 'celery.%'
              )
            ORDER BY occurred_at DESC
        """),
        {"scoped_orgs": scoped_orgs},
    )
    worker_result = await session.execute(
        text("""
            SELECT
                ingestion_source AS worker_type,
                COUNT(*) AS tasks_processed_24h,
                MAX(ingested_at) AS last_heartbeat,
                MIN(ingested_at) AS first_seen_24h
            FROM events
            WHERE ingested_at >= NOW() - INTERVAL '24 hours'
              AND org = ANY(:scoped_orgs)
            GROUP BY ingestion_source
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return {
        "health_events": [dict(row) for row in health_result.mappings().all()],
        "active_workers": [dict(row) for row in worker_result.mappings().all()],
    }


async def get_event_volume(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    bucket: str = "hour",
    hours: int = 24,
) -> dict[str, Any]:
    """Time-series event volume and top actions."""
    volume_result = await session.execute(
        text("""
            SELECT
                date_trunc(:bucket, created_at) AS bucket_time,
                namespace AS category,
                COUNT(*) AS event_count
            FROM events
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - make_interval(hours => :hours)
            GROUP BY bucket_time, category
            ORDER BY bucket_time ASC, event_count DESC
        """),
        {"scoped_orgs": scoped_orgs, "bucket": bucket, "hours": hours},
    )
    actions_result = await session.execute(
        text("""
            SELECT
                action,
                COUNT(*) AS count
            FROM events
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - make_interval(hours => :hours)
            GROUP BY action
            ORDER BY count DESC
            LIMIT 20
        """),
        {"scoped_orgs": scoped_orgs, "hours": hours},
    )
    return {
        "volume": [dict(row) for row in volume_result.mappings().all()],
        "top_actions": [dict(row) for row in actions_result.mappings().all()],
    }


async def get_ingestion_errors(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 100,
) -> dict[str, Any]:
    """Recent ingestion errors and orgs with ingestion gaps."""
    error_result = await session.execute(
        text("""
            SELECT id, occurred_at, org, signal_type, severity, detail, resolved_at
            FROM system_health_events
            WHERE (org = ANY(:scoped_orgs) OR org IS NULL)
              AND severity IN ('error', 'critical')
              AND signal_type LIKE 'ingestion.%'
            ORDER BY occurred_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    gap_result = await session.execute(
        text("""
            SELECT
                org,
                MAX(created_at) AS last_event_at,
                EXTRACT(EPOCH FROM NOW() - MAX(created_at))::INT / 60
                    AS minutes_since_last
            FROM events
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY org
            HAVING EXTRACT(EPOCH FROM NOW() - MAX(created_at)) > 300
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return {
        "errors": [dict(row) for row in error_result.mappings().all()],
        "gaps": [dict(row) for row in gap_result.mappings().all()],
    }


async def get_telemetry_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Aggregate summary telemetry metrics for the dashboard header."""
    summary_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '1 day'
                ) AS events_today,
                COUNT(*) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '1 minute'
                ) AS events_last_minute,
                ROUND(
                    COUNT(*) FILTER (
                        WHERE created_at >= NOW() - INTERVAL '1 hour'
                    ) / 3600.0,
                    2
                ) AS events_per_second,
                MAX(created_at) AS last_event_at,
                COUNT(DISTINCT ingestion_source) FILTER (
                    WHERE ingested_at >= NOW() - INTERVAL '5 minutes'
                ) AS active_workers
            FROM events
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '1 day'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    error_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE severity IN ('error', 'critical')
                ) AS error_count,
                COUNT(*) AS total_count
            FROM system_health_events
            WHERE (org = ANY(:scoped_orgs) OR org IS NULL)
              AND occurred_at >= NOW() - INTERVAL '1 hour'
        """),
        {"scoped_orgs": scoped_orgs},
    )

    summary_mapping = summary_result.mappings().first()
    error_mapping = error_result.mappings().first()

    events_per_second = 0
    events_today = 0
    active_workers = 0
    last_event_at = None
    if summary_mapping:
        events_per_second = summary_mapping["events_per_second"] or 0
        events_today = summary_mapping["events_today"] or 0
        active_workers = summary_mapping["active_workers"] or 0
        last_event_at = summary_mapping["last_event_at"]

    error_count = 0
    total_count = 0
    if error_mapping:
        error_count = error_mapping["error_count"] or 0
        total_count = error_mapping["total_count"] or 0
    error_rate = round(error_count / total_count, 4) if total_count else 0.0

    return {
        "events_per_second": events_per_second,
        "events_today": events_today,
        "active_workers": active_workers,
        "queue_depth": 0,
        "last_event_at": last_event_at,
        "error_rate": error_rate,
    }
