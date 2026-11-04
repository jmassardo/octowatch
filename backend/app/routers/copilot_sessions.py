"""Copilot sessions router: overview and single-session detail endpoints.

Only two of the twelve endpoints designed in #387 are implemented here, per
#508's reduced scope: an aggregated overview and a single-session detail
view (including turns). The remaining endpoints are tracked in a follow-up
issue. All queries enforce RBAC via ``rbac_service.get_scoped_orgs``.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.schemas.copilot_session import CopilotSessionDetail, CopilotSessionOverview
from app.services import rbac_service
from app.services.copilot_session_service import (
    get_copilot_session_detail,
    get_copilot_sessions_overview,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/copilot/sessions", tags=["copilot-sessions"])


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


@router.get(
    "/overview",
    response_model=CopilotSessionOverview,
    summary="Get Copilot session overview",
    description=(
        "Returns aggregated Copilot Chat session statistics: total session "
        "count, average session duration, and the top models and editors by "
        "session count over the lookback window."
    ),
)
async def get_sessions_overview(
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("copilot_sessions", "view")),
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
) -> dict[str, Any]:
    """Return aggregated Copilot session overview stats for the caller's orgs."""
    orgs = await _resolve_orgs(db, current_user)
    return await get_copilot_sessions_overview(db, orgs, days=days)


@router.get(
    "/{session_id}",
    response_model=CopilotSessionDetail,
    summary="Get a single Copilot session",
    description="Returns full detail for a single Copilot Chat session, including all turns.",
)
async def get_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("copilot_sessions", "view")),
) -> dict[str, Any]:
    """Return a single Copilot session (with turns) scoped to the caller's orgs."""
    orgs = await _resolve_orgs(db, current_user)
    session = await get_copilot_session_detail(db, orgs, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Copilot session not found",
        )
    return session
