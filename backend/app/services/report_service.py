"""Report service: TimescaleDB-backed metric aggregations for 8 report buckets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _window_start(window_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=window_days)


def _bucket_interval(granularity: str) -> timedelta:
    return {"daily": timedelta(days=1), "weekly": timedelta(days=7), "monthly": timedelta(days=30)}.get(
        granularity, timedelta(days=1)
    )


async def get_mau_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Monthly Active Users (unique actors per time bucket)."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)  AS bucket,
            COUNT(DISTINCT actor)               AS unique_actors,
            COUNT(*)                            AS total_events
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND actor IS NOT NULL
        GROUP BY 1
        ORDER BY 1 ASC
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "unique_actors": row.unique_actors,
            "total_events": row.total_events,
        }
        for row in result.fetchall()
    ]


async def get_seat_utilization_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Seat utilization: active actors / licensed seat count per org per bucket."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)  AS bucket,
            org,
            COUNT(DISTINCT actor)               AS active_seats
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND actor IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "org": row.org,
            "active_seats": row.active_seats,
        }
        for row in result.fetchall()
    ]


async def get_repo_creation_rate_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Repository creation rate: repos.create events per time bucket."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            COUNT(*)                             AS repos_created,
            COUNT(DISTINCT actor)                AS unique_creators
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action = 'repos.create'
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "org": row.org,
            "repos_created": row.repos_created,
            "unique_creators": row.unique_creators,
        }
        for row in result.fetchall()
    ]


async def get_actions_volume_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """GitHub Actions workflow volume per time bucket."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            COUNT(*)                             AS workflow_runs,
            COUNT(DISTINCT actor)                AS unique_actors,
            COUNT(DISTINCT repo)                 AS unique_repos
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action LIKE 'workflow_run.%'
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "org": row.org,
            "workflow_runs": row.workflow_runs,
            "unique_actors": row.unique_actors,
            "unique_repos": row.unique_repos,
        }
        for row in result.fetchall()
    ]


async def get_copilot_seats_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Copilot seat assignment / removal trends."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            action,
            COUNT(*)                             AS seat_events
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action IN (
              'copilot.enable_organization',
              'copilot.disable_organization',
              'copilot.add_seats',
              'copilot.remove_seats',
              'copilot.seat_allotment_added',
              'copilot.seat_allotment_removed'
          )
        GROUP BY 1, 2, 3
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    rows = result.fetchall()

    # Pivot into per-bucket summaries
    buckets: dict[str, dict] = {}
    for row in rows:
        key = row.bucket.isoformat()
        if key not in buckets:
            buckets[key] = {"bucket": key, "org": row.org, "events": {}}
        buckets[key]["events"][row.action] = row.seat_events

    return list(buckets.values())


async def get_codespace_hours_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Codespace billable hours aggregated from billing events."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)         AS bucket,
            org,
            COUNT(*)                                   AS codespace_events,
            COUNT(DISTINCT actor)                      AS unique_users,
            SUM((data->>'billable_hours')::numeric)    AS total_billable_hours
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action LIKE 'codespaces.%'
          AND data ? 'billable_hours'
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "org": row.org,
            "codespace_events": row.codespace_events,
            "unique_users": row.unique_users,
            "total_billable_hours": float(row.total_billable_hours or 0),
        }
        for row in result.fetchall()
    ]


async def get_pat_counts_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Personal Access Token creation / deletion events per bucket."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            action,
            COUNT(*)                             AS pat_events,
            COUNT(DISTINCT actor)                AS unique_actors
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action IN (
              'personal_access_token.create',
              'personal_access_token.revoke',
              'personal_access_token.expire',
              'personal_access_token_request.create',
              'personal_access_token_request.deny',
              'personal_access_token_request.approve'
          )
        GROUP BY 1, 2, 3
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    rows = result.fetchall()

    buckets: dict[str, dict] = {}
    for row in rows:
        key = row.bucket.isoformat()
        if key not in buckets:
            buckets[key] = {"bucket": key, "org": row.org, "actions": {}}
        buckets[key]["actions"].setdefault(row.action, 0)
        buckets[key]["actions"][row.action] += row.pat_events

    return list(buckets.values())


async def get_webhook_counts_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Webhook creation / deletion counts per bucket."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            action,
            COUNT(*)                             AS webhook_events
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action LIKE 'hook.%'
        GROUP BY 1, 2, 3
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    rows = result.fetchall()

    buckets: dict[str, dict] = {}
    for row in rows:
        key = row.bucket.isoformat()
        if key not in buckets:
            buckets[key] = {"bucket": key, "org": row.org, "actions": {}}
        buckets[key]["actions"].setdefault(row.action, 0)
        buckets[key]["actions"][row.action] += row.webhook_events

    return list(buckets.values())


async def get_top_actors_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    limit: int = 25,
    org: str | None = None,
) -> list[dict]:
    """Top actors by event count in window (admin endpoint)."""
    start = _window_start(window_days)
    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT actor, COUNT(*) AS event_count
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND actor IS NOT NULL
        GROUP BY actor
        ORDER BY event_count DESC
        LIMIT :limit
    """)
    params: dict = {"start": start, "limit": limit}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [{"actor": row.actor, "event_count": row.event_count} for row in result.fetchall()]


async def get_event_trend_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "hourly",
    org: str | None = None,
) -> list[dict]:
    """Overall event volume trend. Uses pre-computed events_hourly if available."""
    start = _window_start(window_days)
    org_filter = "AND org = :org" if org else ""

    if granularity == "hourly":
        # Use pre-computed continuous aggregate
        stmt = text(f"""
            SELECT bucket, org, event_count, unique_actors
            FROM events_hourly
            WHERE bucket >= :start
              {org_filter}
            ORDER BY bucket ASC
        """)
    else:
        _interval = _bucket_interval(granularity)
        stmt = text(f"""
            SELECT
                time_bucket(:interval, created_at) AS bucket,
                org,
                COUNT(*) AS event_count,
                COUNT(DISTINCT actor) AS unique_actors
            FROM events
            WHERE created_at >= :start
              {org_filter}
            GROUP BY 1, 2
            ORDER BY 1 ASC
        """)

    params: dict = {"start": start}
    if granularity != "hourly":
        params["interval"] = _bucket_interval(granularity)
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "org": row.org,
            "event_count": row.event_count,
            "unique_actors": row.unique_actors,
        }
        for row in result.fetchall()
    ]
