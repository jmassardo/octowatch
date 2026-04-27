"""Issue stats service: per-org and per-repo issue metrics from the events hypertable."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _window_start(window_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=window_days)


async def get_issue_stats_by_org(
    session: AsyncSession,
    *,
    window_days: int = 30,
    org: str | None = None,
) -> list[dict[str, Any]]:
    """Return issue opened/closed counts grouped by organization.

    Counts ``issue.opened`` and ``issue.closed`` events within the time window
    and computes average time-to-close for issues that have both events.
    """
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            org,
            COUNT(*) FILTER (WHERE action = 'issue.opened') AS opened,
            COUNT(*) FILTER (WHERE action = 'issue.closed') AS closed
        FROM events
        WHERE action IN ('issue.opened', 'issue.closed')
          AND created_at >= :start
          {org_filter}
        GROUP BY org
        ORDER BY COUNT(*) FILTER (WHERE action = 'issue.opened') DESC
    """)
    params: dict[str, Any] = {"start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    org_rows = [
        {
            "org": row.org,
            "opened": row.opened,
            "closed": row.closed,
            "net_open": row.opened - row.closed,
        }
        for row in result.fetchall()
    ]

    # Compute average time-to-close per org
    avg_stmt = text(f"""
        SELECT
            o.org,
            AVG(EXTRACT(EPOCH FROM (c.created_at - o.created_at)) / 3600)
                AS avg_hours_to_close
        FROM events o
        INNER JOIN events c
            ON c.action = 'issue.closed'
           AND c.repo = o.repo
           AND c.data->>'number' = o.data->>'number'
           AND c.created_at >= :start
        WHERE o.action = 'issue.opened'
          AND o.created_at >= :start
          {org_filter.replace("org", "o.org") if org_filter else ""}
        GROUP BY o.org
    """)
    avg_result = await session.execute(avg_stmt, params)
    avg_map: dict[str, float | None] = {}
    for row in avg_result.fetchall():
        avg_map[row.org] = round(row.avg_hours_to_close, 1) if row.avg_hours_to_close else None

    for item in org_rows:
        item["avg_hours_to_close"] = avg_map.get(item["org"])

    return org_rows


async def get_issue_stats_by_repo(
    session: AsyncSession,
    *,
    window_days: int = 30,
    org: str | None = None,
) -> list[dict[str, Any]]:
    """Return issue opened/closed counts grouped by org and repo.

    Counts ``issue.opened`` and ``issue.closed`` events within the time window
    and computes average time-to-close for issues that have both events.
    """
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            org,
            repo,
            COUNT(*) FILTER (WHERE action = 'issue.opened') AS opened,
            COUNT(*) FILTER (WHERE action = 'issue.closed') AS closed
        FROM events
        WHERE action IN ('issue.opened', 'issue.closed')
          AND created_at >= :start
          {org_filter}
        GROUP BY org, repo
        ORDER BY org ASC,
                 COUNT(*) FILTER (WHERE action = 'issue.opened') DESC
    """)
    params: dict[str, Any] = {"start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    repo_rows = [
        {
            "org": row.org,
            "repo": row.repo,
            "opened": row.opened,
            "closed": row.closed,
            "net_open": row.opened - row.closed,
        }
        for row in result.fetchall()
    ]

    # Compute average time-to-close per repo
    avg_stmt = text(f"""
        SELECT
            o.repo,
            AVG(EXTRACT(EPOCH FROM (c.created_at - o.created_at)) / 3600)
                AS avg_hours_to_close
        FROM events o
        INNER JOIN events c
            ON c.action = 'issue.closed'
           AND c.repo = o.repo
           AND c.data->>'number' = o.data->>'number'
           AND c.created_at >= :start
        WHERE o.action = 'issue.opened'
          AND o.created_at >= :start
          {org_filter.replace("org", "o.org") if org_filter else ""}
        GROUP BY o.repo
    """)
    avg_result = await session.execute(avg_stmt, params)
    avg_map: dict[str, float | None] = {}
    for row in avg_result.fetchall():
        avg_map[row.repo] = round(row.avg_hours_to_close, 1) if row.avg_hours_to_close else None

    for item in repo_rows:
        item["avg_hours_to_close"] = avg_map.get(item["repo"])

    return repo_rows
