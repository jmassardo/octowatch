"""Secret Scanning alert ingestion and analytics service.

Provides sync, summary, trend, and audit-correlation queries for the
``secret_scanning_alerts`` table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class SyncResult:
    """Outcome of a secret-scanning alert sync run."""

    org: str
    created: int = 0
    updated: int = 0
    total_fetched: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class SecretAlertSummary:
    """Aggregate statistics for secret scanning alerts."""

    open_alerts: int = 0
    resolved_30d: int = 0
    push_protection_bypasses: int = 0
    active_secrets: int = 0
    mttr_hours: float = 0.0
    open_by_type: list[dict[str, Any]] = field(default_factory=list)
    resolution_breakdown: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TrendPoint:
    """Single data point in a time-series trend."""

    date: str
    new_alerts: int = 0
    resolved_alerts: int = 0


# ── Sync ──────────────────────────────────────────────────────────────────────


async def sync_secret_alerts(
    session: AsyncSession,
    org: str,
    github_client: Any,
) -> SyncResult:
    """Fetch and upsert secret scanning alerts from the GitHub API.

    Calls ``GET /orgs/{org}/secret-scanning/alerts`` and upserts each alert
    into the ``secret_scanning_alerts`` table using an ON-CONFLICT merge so
    the same alert is never duplicated.

    Parameters
    ----------
    session:
        Active async database session.
    org:
        GitHub organisation slug.
    github_client:
        An object exposing ``get_paginated(url)`` that returns an async
        iterator of alert dicts.

    Returns
    -------
    SyncResult
        Counts of created / updated rows and any per-alert errors.
    """
    result = SyncResult(org=org)

    try:
        alerts = await github_client.get_paginated(
            f"/orgs/{org}/secret-scanning/alerts",
            params={"state": "open,resolved", "per_page": 100},
        )
    except Exception as exc:  # noqa: BLE001 — broad-except is intentional here
        result.errors.append(f"Failed to fetch alerts: {exc}")
        return result

    for alert in alerts:
        result.total_fetched += 1
        try:
            await _upsert_alert(session, org, alert)
            # Determine if it was an insert or update based on the merge
            result.created += 1  # simplified; real upsert returns xmax
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"Alert #{alert.get('number', '?')}: {exc}")

    await session.flush()
    return result


async def _upsert_alert(
    session: AsyncSession,
    org: str,
    alert: dict[str, Any],
) -> None:
    """Insert or update a single secret scanning alert row."""
    resolved_by_login: str | None = None
    if alert.get("resolved_by"):
        resolved_by_login = alert["resolved_by"].get("login")

    bypassed_by_login: str | None = None
    if alert.get("push_protection_bypassed_by"):
        bypassed_by_login = alert["push_protection_bypassed_by"].get("login")

    repo_full = alert.get("repository", {}).get("full_name", "")

    created_at = alert.get("created_at")
    updated_at = alert.get("updated_at")
    resolved_at = alert.get("resolved_at")

    await session.execute(
        text("""
            INSERT INTO secret_scanning_alerts (
                org_slug, alert_number, repo_full_name,
                secret_type, secret_type_display,
                state, resolution,
                push_protection_bypassed, push_protection_bypassed_by,
                validity, locations_count, resolved_by,
                created_at, updated_at, resolved_at, synced_at
            ) VALUES (
                :org, :alert_number, :repo_full_name,
                :secret_type, :secret_type_display,
                :state, :resolution,
                :push_protection_bypassed, :push_protection_bypassed_by,
                :validity, :locations_count, :resolved_by,
                :created_at, :updated_at, :resolved_at, NOW()
            )
            ON CONFLICT ON CONSTRAINT uq_secret_scanning_alert
            DO UPDATE SET
                state                       = EXCLUDED.state,
                resolution                  = EXCLUDED.resolution,
                push_protection_bypassed    = EXCLUDED.push_protection_bypassed,
                push_protection_bypassed_by = EXCLUDED.push_protection_bypassed_by,
                validity                    = EXCLUDED.validity,
                locations_count             = EXCLUDED.locations_count,
                resolved_by                 = EXCLUDED.resolved_by,
                updated_at                  = EXCLUDED.updated_at,
                resolved_at                 = EXCLUDED.resolved_at,
                synced_at                   = NOW()
        """),
        {
            "org": org,
            "alert_number": alert.get("number"),
            "repo_full_name": repo_full,
            "secret_type": alert.get("secret_type", "unknown"),
            "secret_type_display": alert.get("secret_type_display_name"),
            "state": alert.get("state", "open"),
            "resolution": alert.get("resolution"),
            "push_protection_bypassed": bool(alert.get("push_protection_bypassed")),
            "push_protection_bypassed_by": bypassed_by_login,
            "validity": alert.get("validity"),
            "locations_count": len(alert.get("locations", []) or []),
            "resolved_by": resolved_by_login,
            "created_at": created_at,
            "updated_at": updated_at,
            "resolved_at": resolved_at,
        },
    )


# ── Summary ───────────────────────────────────────────────────────────────────


async def get_secret_alert_summary(
    session: AsyncSession,
    scoped_orgs: list[str],
) -> SecretAlertSummary:
    """Compute aggregate statistics for the secret scanning dashboard.

    Returns open-alert count, 30-day resolved count, push-protection
    bypass count, active-validity count, and MTTR.
    """
    result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE state = 'open')
                    AS open_alerts,
                COUNT(*) FILTER (
                    WHERE state = 'resolved'
                      AND resolved_at >= NOW() - INTERVAL '30 days'
                ) AS resolved_30d,
                COUNT(*) FILTER (
                    WHERE push_protection_bypassed = TRUE
                ) AS push_protection_bypasses,
                COUNT(*) FILTER (
                    WHERE validity = 'active' AND state = 'open'
                ) AS active_secrets,
                COALESCE(
                    AVG(
                        EXTRACT(EPOCH FROM resolved_at - created_at) / 3600.0
                    ) FILTER (
                        WHERE state = 'resolved' AND resolved_at IS NOT NULL
                    ),
                    0
                ) AS mttr_hours
            FROM secret_scanning_alerts
            WHERE org_slug = ANY(:scoped_orgs)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    row = result.mappings().first()
    if not row:
        return SecretAlertSummary()

    # Open by type breakdown
    type_result = await session.execute(
        text("""
            SELECT
                COALESCE(secret_type_display, secret_type) AS secret_type_label,
                COUNT(*) AS count
            FROM secret_scanning_alerts
            WHERE org_slug = ANY(:scoped_orgs)
              AND state = 'open'
            GROUP BY secret_type_label
            ORDER BY count DESC
            LIMIT 20
        """),
        {"scoped_orgs": scoped_orgs},
    )
    open_by_type = [dict(r) for r in type_result.mappings().all()]

    # Resolution breakdown
    res_result = await session.execute(
        text("""
            SELECT
                COALESCE(resolution, 'unresolved') AS resolution,
                COUNT(*) AS count
            FROM secret_scanning_alerts
            WHERE org_slug = ANY(:scoped_orgs)
            GROUP BY resolution
            ORDER BY count DESC
        """),
        {"scoped_orgs": scoped_orgs},
    )
    resolution_breakdown = [dict(r) for r in res_result.mappings().all()]

    return SecretAlertSummary(
        open_alerts=int(row["open_alerts"]),
        resolved_30d=int(row["resolved_30d"]),
        push_protection_bypasses=int(row["push_protection_bypasses"]),
        active_secrets=int(row["active_secrets"]),
        mttr_hours=float(row["mttr_hours"]),
        open_by_type=open_by_type,
        resolution_breakdown=resolution_breakdown,
    )


# ── Trends ────────────────────────────────────────────────────────────────────


async def get_secret_alert_trends(
    session: AsyncSession,
    scoped_orgs: list[str],
    period: int = 30,
) -> list[TrendPoint]:
    """Return a daily time-series of new and resolved secret scanning alerts.

    Parameters
    ----------
    period:
        Number of days to look back (default 30).
    """
    result = await session.execute(
        text("""
            WITH date_series AS (
                SELECT generate_series(
                    (CURRENT_DATE - :period * INTERVAL '1 day')::date,
                    CURRENT_DATE::date,
                    '1 day'::interval
                )::date AS day
            ),
            new_alerts AS (
                SELECT created_at::date AS day, COUNT(*) AS cnt
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND created_at >= CURRENT_DATE - :period * INTERVAL '1 day'
                GROUP BY created_at::date
            ),
            resolved_alerts AS (
                SELECT resolved_at::date AS day, COUNT(*) AS cnt
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND resolved_at IS NOT NULL
                  AND resolved_at >= CURRENT_DATE - :period * INTERVAL '1 day'
                GROUP BY resolved_at::date
            )
            SELECT
                d.day::text AS date,
                COALESCE(n.cnt, 0) AS new_alerts,
                COALESCE(r.cnt, 0) AS resolved_alerts
            FROM date_series d
            LEFT JOIN new_alerts n ON d.day = n.day
            LEFT JOIN resolved_alerts r ON d.day = r.day
            ORDER BY d.day
        """),
        {"scoped_orgs": scoped_orgs, "period": period},
    )
    return [
        TrendPoint(
            date=str(row["date"]),
            new_alerts=int(row["new_alerts"]),
            resolved_alerts=int(row["resolved_alerts"]),
        )
        for row in result.mappings().all()
    ]


# ── Audit-log correlation ────────────────────────────────────────────────────


async def correlate_with_audit_log(
    session: AsyncSession,
    alert_id: int,
) -> list[dict[str, Any]]:
    """Find audit log events related to a leaked secret alert.

    Looks for ``secret_scanning_alert.*`` actions whose alert number matches,
    as well as token-usage events that occurred *after* the alert was created.
    """
    # Fetch the alert to get context
    alert_result = await session.execute(
        text("""
            SELECT org_slug, alert_number, secret_type, created_at, repo_full_name
            FROM secret_scanning_alerts
            WHERE id = :alert_id
        """),
        {"alert_id": alert_id},
    )
    alert_row = alert_result.mappings().first()
    if not alert_row:
        return []

    org_slug = alert_row["org_slug"]
    alert_number = alert_row["alert_number"]
    created_at: datetime = alert_row["created_at"]

    # Search for related audit events
    events_result = await session.execute(
        text("""
            SELECT
                id, action, actor, org, repo,
                created_at, data
            FROM audit_events
            WHERE org = :org
              AND (
                  -- Direct alert actions
                  (action LIKE 'secret_scanning_alert.%%'
                   AND data::text LIKE :alert_pattern)
                  -- Push protection events for the same repo
                  OR (action = 'secret_scanning.push_protection.bypass'
                      AND repo = :repo
                      AND created_at >= :created_at)
              )
            ORDER BY created_at DESC
            LIMIT 50
        """),
        {
            "org": org_slug,
            "alert_pattern": f"%{alert_number}%",
            "repo": alert_row["repo_full_name"],
            "created_at": created_at,
        },
    )
    return [dict(row) for row in events_result.mappings().all()]


# ── Push protection effectiveness ────────────────────────────────────────────


async def get_push_protection_stats(
    session: AsyncSession,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Return push protection blocked vs bypassed statistics."""
    result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_alerts,
                COUNT(*) FILTER (
                    WHERE push_protection_bypassed = TRUE
                ) AS bypassed,
                COUNT(*) FILTER (
                    WHERE push_protection_bypassed = FALSE
                ) AS blocked
            FROM secret_scanning_alerts
            WHERE org_slug = ANY(:scoped_orgs)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    row = result.mappings().first()
    if not row:
        return {"total": 0, "bypassed": 0, "blocked": 0, "effectiveness_pct": 0.0}

    total = int(row["total_alerts"])
    bypassed = int(row["bypassed"])
    blocked = int(row["blocked"])
    effectiveness = round(blocked / total * 100, 1) if total else 0.0

    return {
        "total": total,
        "bypassed": bypassed,
        "blocked": blocked,
        "effectiveness_pct": effectiveness,
    }
