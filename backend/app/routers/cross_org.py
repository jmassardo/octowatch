"""Cross-organization correlation router.

Provides endpoints for viewing actor activity across multiple organizations
and listing detected cross-org correlation patterns.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.services.rbac_service import get_user_scope

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/cross-org", tags=["cross-org"])


@router.get("/actors/{login}")
async def get_actor_cross_org_timeline(
    login: str,
    days: int = Query(default=30, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("cross_org", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return an actor's activity timeline spanning all organizations.

    Shows events grouped by org with timestamps, enabling analysts to see
    lateral movement patterns.
    """
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    scoped_orgs = scope.scoped_orgs if not scope.is_global else []

    if scope.is_global:
        result = await db.execute(
            text("""
                SELECT id, created_at, action, org, repo, source_ip,
                       geo_country_code, data
                FROM events
                WHERE actor = :login
                  AND created_at >= NOW() - make_interval(days => :days)
                ORDER BY created_at DESC
                LIMIT 500
            """),
            {"login": login, "days": days},
        )
    else:
        result = await db.execute(
            text("""
                SELECT id, created_at, action, org, repo, source_ip,
                       geo_country_code, data
                FROM events
                WHERE actor = :login
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - make_interval(days => :days)
                ORDER BY created_at DESC
                LIMIT 500
            """),
            {"login": login, "scoped_orgs": scoped_orgs, "days": days},
        )

    rows = result.fetchall()
    events = [dict(r._mapping) for r in rows]

    # Group by org
    by_org: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        org_name = ev.get("org") or "unknown"
        by_org.setdefault(org_name, []).append(
            {
                "id": ev["id"],
                "created_at": str(ev["created_at"]),
                "action": ev["action"],
                "repo": ev.get("repo"),
                "source_ip": str(ev["source_ip"]) if ev.get("source_ip") else None,
                "geo_country_code": ev.get("geo_country_code"),
            }
        )

    return {
        "actor": login,
        "days": days,
        "organizations": list(by_org.keys()),
        "org_count": len(by_org),
        "total_events": len(events),
        "timeline_by_org": by_org,
    }


@router.get("/timeline")
async def get_cross_org_timeline_flat(
    actor: str | None = Query(None, description="Filter to a specific actor"),
    hours: int = Query(default=168, ge=1, le=8760),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(require_permission("cross_org", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return a flat timeline of cross-org events.

    If *actor* is provided, shows that actor's events.  Otherwise returns
    events from actors active in 2+ organisations.
    """
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    scoped_orgs = scope.scoped_orgs if not scope.is_global else []
    offset = (page - 1) * page_size

    if actor:
        # Events for a specific actor
        scope_clause = "" if scope.is_global else "AND org = ANY(:scoped_orgs)"
        result = await db.execute(
            # SECURITY: static clause fragments only, not user input
            text(f"""
                SELECT id, created_at, action, actor, org, repo,
                       source_ip, geo_country_code
                FROM events
                WHERE actor = :actor
                  AND created_at >= NOW() - make_interval(hours => :hours)
                  {scope_clause}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {
                "actor": actor,
                "hours": hours,
                "scoped_orgs": scoped_orgs,
                "limit": page_size,
                "offset": offset,
            },
        )
        count_result = await db.execute(
            # SECURITY: static clause fragments only, not user input
            text(f"""
                SELECT COUNT(*) FROM events
                WHERE actor = :actor
                  AND created_at >= NOW() - make_interval(hours => :hours)
                  {scope_clause}
            """),
            {"actor": actor, "hours": hours, "scoped_orgs": scoped_orgs},
        )
    else:
        # Events from actors active in 2+ orgs
        scope_clause = "" if scope.is_global else "AND e.org = ANY(:scoped_orgs)"
        result = await db.execute(
            # SECURITY: static clause fragments only, not user input
            text(f"""
                SELECT e.id, e.created_at, e.action, e.actor, e.org, e.repo,
                       e.source_ip, e.geo_country_code
                FROM events e
                INNER JOIN (
                    SELECT actor FROM events
                    WHERE created_at >= NOW() - make_interval(hours => :hours)
                      AND actor IS NOT NULL
                    GROUP BY actor
                    HAVING COUNT(DISTINCT org) >= 2
                ) multi ON e.actor = multi.actor
                WHERE e.created_at >= NOW() - make_interval(hours => :hours)
                  {scope_clause}
                ORDER BY e.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {
                "hours": hours,
                "scoped_orgs": scoped_orgs,
                "limit": page_size,
                "offset": offset,
            },
        )
        count_result = await db.execute(
            # SECURITY: static clause fragments only, not user input
            text(f"""
                SELECT COUNT(*) FROM events e
                INNER JOIN (
                    SELECT actor FROM events
                    WHERE created_at >= NOW() - make_interval(hours => :hours)
                      AND actor IS NOT NULL
                    GROUP BY actor
                    HAVING COUNT(DISTINCT org) >= 2
                ) multi ON e.actor = multi.actor
                WHERE e.created_at >= NOW() - make_interval(hours => :hours)
                  {scope_clause}
            """),
            {"hours": hours, "scoped_orgs": scoped_orgs},
        )

    rows = result.fetchall()
    total = count_result.scalar_one()

    events = [
        {
            "id": r.id,
            "created_at": str(r.created_at),
            "action": r.action,
            "actor": r.actor,
            "org": r.org,
            "repo": r.repo,
            "source_ip": str(r.source_ip) if r.source_ip else None,
            "country": r.geo_country_code,
        }
        for r in rows
    ]

    return {
        "events": events,
        "total": total,
    }


@router.get("/correlations")
async def list_cross_org_correlations(
    hours: int = Query(default=168, ge=1, le=2160),
    min_orgs: int = Query(default=2, ge=2, le=50),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_permission("cross_org", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List actors who have performed actions across multiple orgs.

    Identifies actors active in *min_orgs*+ orgs within the given time window.
    """
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    scoped_orgs = scope.scoped_orgs if not scope.is_global else []

    if scope.is_global:
        result = await db.execute(
            text("""
                SELECT actor,
                       COUNT(DISTINCT org) AS org_count,
                       COUNT(*) AS event_count,
                       array_agg(DISTINCT org) AS orgs,
                       array_agg(DISTINCT action) AS actions,
                       MIN(created_at) AS first_seen,
                       MAX(created_at) AS last_seen
                FROM events
                WHERE created_at >= NOW() - make_interval(hours => :hours)
                  AND actor IS NOT NULL
                GROUP BY actor
                HAVING COUNT(DISTINCT org) >= :min_orgs
                ORDER BY org_count DESC, event_count DESC
                LIMIT :limit
            """),
            {"hours": hours, "min_orgs": min_orgs, "limit": limit},
        )
    else:
        result = await db.execute(
            text("""
                SELECT actor,
                       COUNT(DISTINCT org) AS org_count,
                       COUNT(*) AS event_count,
                       array_agg(DISTINCT org) AS orgs,
                       array_agg(DISTINCT action) AS actions,
                       MIN(created_at) AS first_seen,
                       MAX(created_at) AS last_seen
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - make_interval(hours => :hours)
                  AND actor IS NOT NULL
                GROUP BY actor
                HAVING COUNT(DISTINCT org) >= :min_orgs
                ORDER BY org_count DESC, event_count DESC
                LIMIT :limit
            """),
            {
                "scoped_orgs": scoped_orgs,
                "hours": hours,
                "min_orgs": min_orgs,
                "limit": limit,
            },
        )

    rows = result.fetchall()
    correlations = [
        {
            "actor": r.actor,
            "org_count": r.org_count,
            "event_count": r.event_count,
            "orgs": r.orgs,
            "distinct_actions": len(r.actions) if r.actions else 0,
            "first_seen": str(r.first_seen),
            "last_seen": str(r.last_seen),
            "risk_score": min(r.org_count * 20 + r.event_count, 100),
        }
        for r in rows
    ]

    return {
        "hours": hours,
        "total": len(correlations),
        "correlations": correlations,
    }
