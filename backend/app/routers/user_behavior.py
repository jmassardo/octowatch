"""User behavior security analytics router.

Provides endpoints for security-focused behavioral analysis:
- Risk scoring and risk-tier breakdowns
- Anomaly detection (users deviating from their baseline)
- Permission drift analysis (excessive permissions vs actual activity)
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.services import rbac_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/user-behavior", tags=["user-behavior"])


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty."""
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs and current_user.scope_type != "global":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


@router.get("/risk-summary", response_model=dict[str, Any])
async def risk_summary(
    lookback_days: int = Query(default=30, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("user_behavior", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return aggregate risk metrics across all users in scope."""
    from app.services.user_behavior_service import get_risk_summary

    scoped_orgs = await _resolve_orgs(db, current_user)
    return await get_risk_summary(db, scoped_orgs, lookback_days)


@router.get("/risky-users", response_model=dict[str, Any])
async def risky_users(
    lookback_days: int = Query(default=30, ge=1, le=365),
    risk_level: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_permission("user_behavior", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return paginated list of users with risk scores and signal breakdowns."""
    from app.services.user_behavior_service import get_risky_users

    scoped_orgs = await _resolve_orgs(db, current_user)
    return await get_risky_users(
        db, scoped_orgs, lookback_days, risk_level=risk_level, page=page, page_size=page_size
    )


@router.get("/anomalies", response_model=dict[str, Any])
async def anomalies(
    lookback_days: int = Query(default=30, ge=1, le=365),
    threshold: float = Query(default=2.0, ge=1.5, le=10.0),
    current_user: AuthenticatedUser = Depends(require_permission("user_behavior", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return users whose recent activity deviates significantly from baseline."""
    from app.services.user_behavior_service import get_anomalous_users

    scoped_orgs = await _resolve_orgs(db, current_user)
    return await get_anomalous_users(db, scoped_orgs, lookback_days, threshold_multiplier=threshold)


@router.get("/permission-drift", response_model=dict[str, Any])
async def permission_drift(
    lookback_days: int = Query(default=90, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("user_behavior", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return users with excessive permissions relative to their actual activity."""
    from app.services.user_behavior_service import get_permission_drift

    scoped_orgs = await _resolve_orgs(db, current_user)
    return await get_permission_drift(db, scoped_orgs, lookback_days)
