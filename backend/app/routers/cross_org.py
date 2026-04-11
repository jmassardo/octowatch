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

from app.deps import AuthenticatedUser, get_db, require_role
from app.services.rbac_service import get_user_scope

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/cross-org", tags=["cross-org"])


@router.get("/actors/{login}")
async def get_actor_cross_org_timeline(
    login: str,
    days: int = Query(default=30, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
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


@router.get("/correlations")
async def list_cross_org_correlations(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List actors who have performed suspicious actions across multiple orgs.

    Identifies actors active in 2+ orgs with high-privilege actions.
    """
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    scoped_orgs = scope.scoped_orgs if not scope.is_global else []

    suspicious_actions = [
        "org.update_member",
        "org.add_member",
        "repo.destroy",
        "repo.access",
        "protected_branch.destroy",
        "public_key.create",
        "deploy_key.create",
    ]

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
                WHERE action = ANY(:actions)
                  AND created_at >= NOW() - make_interval(days => :days)
                  AND actor IS NOT NULL
                GROUP BY actor
                HAVING COUNT(DISTINCT org) >= 2
                ORDER BY org_count DESC, event_count DESC
                LIMIT :limit
            """),
            {"actions": suspicious_actions, "days": days, "limit": limit},
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
                WHERE action = ANY(:actions)
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - make_interval(days => :days)
                  AND actor IS NOT NULL
                GROUP BY actor
                HAVING COUNT(DISTINCT org) >= 2
                ORDER BY org_count DESC, event_count DESC
                LIMIT :limit
            """),
            {
                "actions": suspicious_actions,
                "scoped_orgs": scoped_orgs,
                "days": days,
                "limit": limit,
            },
        )

    rows = result.fetchall()
    correlations = [
        {
            "actor": r.actor,
            "org_count": r.org_count,
            "event_count": r.event_count,
            "organizations": r.orgs,
            "actions": r.actions,
            "first_seen": str(r.first_seen),
            "last_seen": str(r.last_seen),
        }
        for r in rows
    ]

    return {
        "days": days,
        "total": len(correlations),
        "correlations": correlations,
    }
