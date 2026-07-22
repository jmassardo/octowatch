"""Platform usage analytics service.

Provides aggregated views of platform feature utilization across orgs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

FEATURE_NAME = "platform_usage"


async def _check_feature_enabled(db: AsyncSession) -> None:
    """Check if the platform usage feature is enabled (no-op for now, always enabled)."""


async def get_usage_summary(
    db: AsyncSession,
    *,
    org: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Get aggregated usage summary across all feature areas.

    Returns totals and daily averages for each feature area.
    """
    await _check_feature_enabled(db)

    cutoff = date.today() - timedelta(days=days)

    org_filter = "AND org_slug = :org" if org else ""
    params: dict[str, Any] = {"cutoff": cutoff}
    if org:
        params["org"] = org

    result = await db.execute(
        text(f"""
            SELECT
                feature_area,
                COUNT(DISTINCT actor_login) AS unique_actors,
                COUNT(DISTINCT metric_date) AS active_days,
                SUM(actions_minutes) AS total_actions_minutes,
                SUM(actions_runs) AS total_actions_runs,
                SUM(copilot_suggestions) AS total_copilot_suggestions,
                SUM(copilot_acceptances) AS total_copilot_acceptances,
                SUM(copilot_credits) AS total_copilot_credits,
                SUM(git_clones) AS total_git_clones,
                SUM(git_pushes) AS total_git_pushes,
                SUM(packages_published) AS total_packages_published
            FROM utilization_facts
            WHERE metric_date >= :cutoff {org_filter}
            GROUP BY feature_area
            ORDER BY feature_area
        """),
        params,
    )

    rows = result.fetchall()
    features = []
    for row in rows:
        features.append(
            {
                "feature_area": row[0],
                "unique_actors": row[1],
                "active_days": row[2],
                "total_actions_minutes": float(row[3]) if row[3] else 0,
                "total_actions_runs": row[4] or 0,
                "total_copilot_suggestions": row[5] or 0,
                "total_copilot_acceptances": row[6] or 0,
                "total_copilot_credits": float(row[7]) if row[7] else 0,
                "total_git_clones": row[8] or 0,
                "total_git_pushes": row[9] or 0,
                "total_packages_published": row[10] or 0,
            }
        )

    return {"features": features, "period_days": days}


async def get_top_consumers(
    db: AsyncSession,
    *,
    org: str | None = None,
    feature_area: str = "actions",
    days: int = 30,
    limit: int = 20,
) -> dict[str, Any]:
    """Get top consumers for a specific feature area."""
    await _check_feature_enabled(db)

    cutoff = date.today() - timedelta(days=days)

    org_filter = "AND org_slug = :org" if org else ""
    params: dict[str, Any] = {
        "cutoff": cutoff,
        "feature_area": feature_area,
        "limit": limit,
    }
    if org:
        params["org"] = org

    result = await db.execute(
        text(f"""
            SELECT
                actor_login,
                org_slug,
                SUM(actions_minutes) AS total_actions_minutes,
                SUM(actions_runs) AS total_actions_runs,
                SUM(copilot_suggestions) AS total_copilot_suggestions,
                SUM(copilot_acceptances) AS total_copilot_acceptances,
                SUM(copilot_credits) AS total_copilot_credits,
                SUM(git_clones) AS total_git_clones,
                SUM(git_pushes) AS total_git_pushes,
                COUNT(DISTINCT metric_date) AS active_days
            FROM utilization_facts
            WHERE feature_area = :feature_area
              AND metric_date >= :cutoff
              AND actor_login != '__org_aggregate__'
              {org_filter}
            GROUP BY actor_login, org_slug
            ORDER BY COALESCE(SUM(actions_minutes), 0)
                   + COALESCE(SUM(copilot_credits), 0)
                   + COALESCE(SUM(git_clones), 0) DESC
            LIMIT :limit
        """),
        params,
    )

    rows = result.fetchall()
    consumers = []
    for row in rows:
        consumers.append(
            {
                "actor_login": row[0],
                "org_slug": row[1],
                "total_actions_minutes": float(row[2]) if row[2] else 0,
                "total_actions_runs": row[3] or 0,
                "total_copilot_suggestions": row[4] or 0,
                "total_copilot_acceptances": row[5] or 0,
                "total_copilot_credits": float(row[6]) if row[6] else 0,
                "total_git_clones": row[7] or 0,
                "total_git_pushes": row[8] or 0,
                "active_days": row[9],
            }
        )

    return {"consumers": consumers, "feature_area": feature_area, "period_days": days}


async def get_usage_trends(
    db: AsyncSession,
    *,
    org: str | None = None,
    feature_area: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    """Get daily usage trends for charting."""
    await _check_feature_enabled(db)

    cutoff = date.today() - timedelta(days=days)

    filters = ["metric_date >= :cutoff"]
    params: dict[str, Any] = {"cutoff": cutoff}
    if org:
        filters.append("org_slug = :org")
        params["org"] = org
    if feature_area:
        filters.append("feature_area = :feature_area")
        params["feature_area"] = feature_area

    where_clause = " AND ".join(filters)

    result = await db.execute(
        text(f"""
            SELECT
                metric_date,
                feature_area,
                COUNT(DISTINCT actor_login) AS unique_actors,
                SUM(actions_minutes) AS actions_minutes,
                SUM(copilot_credits) AS copilot_credits,
                SUM(git_clones) AS git_clones,
                SUM(git_pushes) AS git_pushes
            FROM utilization_facts
            WHERE {where_clause}
              AND actor_login != '__org_aggregate__'
            GROUP BY metric_date, feature_area
            ORDER BY metric_date
        """),
        params,
    )

    rows = result.fetchall()
    trends = []
    for row in rows:
        trends.append(
            {
                "date": row[0].isoformat() if row[0] else None,
                "feature_area": row[1],
                "unique_actors": row[2],
                "actions_minutes": float(row[3]) if row[3] else 0,
                "copilot_credits": float(row[4]) if row[4] else 0,
                "git_clones": row[5] or 0,
                "git_pushes": row[6] or 0,
            }
        )

    return {"trends": trends, "period_days": days}


async def get_anomalies(
    db: AsyncSession,
    *,
    org: str | None = None,
    days: int = 7,
    limit: int = 50,
) -> dict[str, Any]:
    """Get recent utilization anomaly detections."""
    await _check_feature_enabled(db)

    cutoff = datetime.now(UTC) - timedelta(days=days)

    org_filter = ""
    params: dict[str, Any] = {"cutoff": cutoff, "limit": limit}
    if org:
        org_filter = "AND d.data->>'org' = :org"
        params["org"] = org

    result = await db.execute(
        text(f"""
            SELECT
                d.id,
                d.triggered_at,
                d.severity,
                d.confidence_score,
                d.actor,
                d.data->>'org' AS org,
                r.name AS rule_name,
                r.slug AS rule_slug,
                r.category
            FROM detections d
            JOIN rule_definitions r ON d.rule_id = r.id
            WHERE r.category = 'utilization'
              AND d.triggered_at >= :cutoff
              AND d.status != 'dismissed'
              {org_filter}
            ORDER BY d.triggered_at DESC
            LIMIT :limit
        """),
        params,
    )

    rows = result.fetchall()
    anomalies = []
    for row in rows:
        anomalies.append(
            {
                "id": row[0],
                "triggered_at": row[1].isoformat() if row[1] else None,
                "severity": row[2],
                "confidence_score": row[3],
                "actor": row[4],
                "org": row[5],
                "rule_name": row[6],
                "rule_slug": row[7],
                "category": row[8],
            }
        )

    return {"anomalies": anomalies, "period_days": days}


async def get_user_usage(
    db: AsyncSession,
    *,
    login: str,
    org: str | None = None,
    days: int = 90,
) -> dict[str, Any]:
    """Get usage profile for a specific user."""
    await _check_feature_enabled(db)

    cutoff = date.today() - timedelta(days=days)

    org_filter = "AND org_slug = :org" if org else ""
    params: dict[str, Any] = {"cutoff": cutoff, "login": login}
    if org:
        params["org"] = org

    result = await db.execute(
        text(f"""
            SELECT
                feature_area,
                metric_date,
                actions_minutes,
                actions_runs,
                copilot_suggestions,
                copilot_acceptances,
                copilot_credits,
                git_clones,
                git_pushes,
                packages_published,
                storage_bytes
            FROM utilization_facts
            WHERE actor_login = :login
              AND metric_date >= :cutoff
              {org_filter}
            ORDER BY metric_date DESC
        """),
        params,
    )

    rows = result.fetchall()
    facts = []
    for row in rows:
        facts.append(
            {
                "feature_area": row[0],
                "date": row[1].isoformat() if row[1] else None,
                "actions_minutes": float(row[2]) if row[2] else None,
                "actions_runs": row[3],
                "copilot_suggestions": row[4],
                "copilot_acceptances": row[5],
                "copilot_credits": float(row[6]) if row[6] else None,
                "git_clones": row[7],
                "git_pushes": row[8],
                "packages_published": row[9],
                "storage_bytes": row[10],
            }
        )

    return {"login": login, "facts": facts, "period_days": days}
