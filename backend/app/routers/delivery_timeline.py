"""Delivery timeline router: enriched PR delivery metrics.

Provides aggregated delivery timeline statistics showing how long PRs take
to move through backlog → development → review → deployment phases.
All queries enforce RBAC via ``rbac_service.get_scoped_orgs``.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.schemas.delivery_timeline import DeliveryTimelineStats
from app.services import rbac_service
from app.services.enrichment_service import get_delivery_timeline_stats

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/metrics/delivery-timeline", tags=["metrics"])


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
    "",
    response_model=DeliveryTimelineStats,
    summary="Get delivery timeline metrics",
    description=(
        "Returns aggregated delivery timeline statistics showing average phase "
        "durations for merged PRs. Supports filtering by repo and time window."
    ),
)
async def get_delivery_timeline(
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
    repo: str | None = Query(default=None, description="Filter by repository name"),
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
) -> dict[str, Any]:
    """Return aggregated delivery timeline metrics for the authenticated user's orgs."""
    orgs = await _resolve_orgs(db, current_user)

    stats = await get_delivery_timeline_stats(
        db,
        orgs=orgs,
        repo=repo,
        days=days,
    )
    return stats
