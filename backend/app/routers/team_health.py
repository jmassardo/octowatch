"""Team health router: bus factor, engagement, policy violations, and summary.

Provides aggregated team health analytics computed from the ``events`` table.
All queries enforce RBAC via ``rbac_service.get_scoped_orgs``.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.services import rbac_service
from app.services.team_health_service import (
    get_bus_factor,
    get_developer_engagement,
    get_engagement_trend,
    get_knowledge_concentration,
    get_policy_violations,
    get_team_health_summary,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/team-health", tags=["team-health"])


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty.

    Global (sys_admin) users with no orgs yet get an empty list (no data)
    rather than 403, since it means no events/orgs have been synced yet.
    """
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs and current_user.scope_type != "global":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


@router.get("/bus-factor", response_model=dict[str, Any])
async def bus_factor(
    lookback_days: int = Query(default=90, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("team_health", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return per-repo bus factor analysis."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    repos = await get_bus_factor(db, scoped_orgs, lookback_days)
    return {"repos": repos, "lookback_days": lookback_days}


@router.get("/engagement", response_model=dict[str, Any])
async def engagement(
    lookback_days: int = Query(default=30, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("team_health", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return developer engagement tier breakdown."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    engagement_data = await get_developer_engagement(db, scoped_orgs, lookback_days)
    trend = await get_engagement_trend(db, scoped_orgs)
    return {**engagement_data, "trend": trend, "lookback_days": lookback_days}


@router.get("/policy-violations", response_model=dict[str, Any])
async def policy_violations(
    lookback_days: int = Query(default=30, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("team_health", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return detected policy violations from audit log patterns."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    data = await get_policy_violations(db, scoped_orgs, lookback_days)
    return {**data, "lookback_days": lookback_days}


@router.get("/knowledge-concentration", response_model=dict[str, Any])
async def knowledge_concentration(
    lookback_days: int = Query(default=90, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("team_health", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return repos where knowledge is concentrated in few people."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    risks = await get_knowledge_concentration(db, scoped_orgs, lookback_days)
    return {"risks": risks, "lookback_days": lookback_days}


@router.get("/summary", response_model=dict[str, Any])
async def summary(
    current_user: AuthenticatedUser = Depends(require_permission("team_health", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return combined team health summary for MetricCards strip."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await get_team_health_summary(db, scoped_orgs)
