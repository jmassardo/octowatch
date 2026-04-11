"""Copilot metrics router — endpoints for the frontend Copilot panes.

Provides overview, adoption, models, anomalies, teams, blockers,
policy changes, and ROI report data.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.services import copilot_metrics_service

router = APIRouter(prefix="/copilot", tags=["copilot"])

_REQUIRED_ROLES = ["viewer", "analyst", "sys_admin"]


@router.get("/overview", response_model=dict[str, Any])
async def copilot_overview(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Overview pane: acceptance rates, language breakdown, user counts."""
    return await copilot_metrics_service.get_copilot_overview(db)


@router.get("/adoption", response_model=dict[str, Any])
async def copilot_adoption(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adoption pane: user tiers, feature adoption rates, per-user data."""
    return await copilot_metrics_service.get_copilot_adoption(db)


@router.get("/models", response_model=dict[str, Any])
async def copilot_models(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Models pane: model usage, feature counts, editors."""
    return await copilot_metrics_service.get_copilot_models(db)


@router.get("/anomalies", response_model=dict[str, Any])
async def copilot_anomalies(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Anomalies pane: detected metric deviations."""
    return await copilot_metrics_service.get_copilot_anomalies(db)


@router.get("/teams", response_model=dict[str, Any])
async def copilot_teams(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Team-level Copilot adoption breakdown."""
    return await copilot_metrics_service.get_copilot_teams(db)


@router.get("/blockers", response_model=dict[str, Any])
async def copilot_blockers(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adoption blockers analysis with recommendations."""
    return await copilot_metrics_service.get_copilot_blockers(db)


@router.get("/policy-changes", response_model=dict[str, Any])
async def copilot_policy_changes(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Copilot policy change timeline from audit events."""
    return await copilot_metrics_service.get_copilot_policy_changes(db)


@router.get("/roi", response_model=dict[str, Any])
async def copilot_roi(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Copilot ROI and cost optimization report."""
    return await copilot_metrics_service.get_copilot_roi(db)
