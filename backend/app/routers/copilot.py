"""Copilot metrics router — four GET endpoints for the frontend Copilot panes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.services import copilot_metrics_service

router = APIRouter(prefix="/copilot", tags=["copilot"])

_REQUIRED_ROLES = ["viewer", "analyst", "sys_admin"]


@router.get("/overview")
async def copilot_overview(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Overview pane: acceptance rates, language breakdown, user counts."""
    return await copilot_metrics_service.get_copilot_overview(db)


@router.get("/adoption")
async def copilot_adoption(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adoption pane: user tiers, feature adoption rates."""
    return await copilot_metrics_service.get_copilot_adoption(db)


@router.get("/models")
async def copilot_models(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Models pane: model usage, feature counts, editors."""
    return await copilot_metrics_service.get_copilot_models(db)


@router.get("/anomalies")
async def copilot_anomalies(
    current_user: AuthenticatedUser = Depends(require_role(_REQUIRED_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Anomalies pane: detected metric deviations."""
    return await copilot_metrics_service.get_copilot_anomalies(db)
