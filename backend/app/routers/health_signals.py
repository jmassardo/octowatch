"""Health signals router: Org Health tab API endpoints.

Every endpoint enforces RBAC by resolving scoped_orgs from the database
(via ``rbac_service.get_scoped_orgs``) and returning HTTP 403 when the
user has no org access.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.services import health_signal_service, rbac_service

router = APIRouter(prefix="/health-signals", tags=["health-signals"])


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty."""
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


@router.get("/summary")
async def health_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate counts across all health signal types."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_health_summary(db, scoped_orgs=scoped_orgs)


@router.get("/pat-health")
async def pat_health(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """PAT age and dormant token signals."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    summary = await health_signal_service.get_pat_health_summary(db, scoped_orgs=scoped_orgs)
    tokens = await health_signal_service.get_pat_token_age_signals(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    dormant = await health_signal_service.get_dormant_tokens(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"summary": summary, "tokens": tokens, "dormant": dormant}


@router.get("/bypass-offenders")
async def bypass_offenders(
    lookback_days: int = Query(default=90, ge=7, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Top bypass offenders."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    offenders = await health_signal_service.get_bypass_offenders(
        db, scoped_orgs=scoped_orgs, lookback_days=lookback_days, limit=limit
    )
    return {"offenders": offenders}


@router.get("/repo-health")
async def repo_health(
    stale_threshold_days: int = Query(default=90, ge=7, le=365),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Stale, archived, and abandoned fork repositories."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    stale = await health_signal_service.get_stale_repositories(
        db, scoped_orgs=scoped_orgs, stale_threshold_days=stale_threshold_days, limit=limit
    )
    archived = await health_signal_service.get_archived_repositories(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    forks = await health_signal_service.get_abandoned_forks(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"stale": stale, "archived": archived, "abandoned_forks": forks}


@router.get("/external-collaborators")
async def external_collaborators(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Active external collaborators and summary."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    summary = await health_signal_service.get_external_collaborator_summary(
        db, scoped_orgs=scoped_orgs
    )
    collaborators = await health_signal_service.get_external_collaborators(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"summary": summary, "collaborators": collaborators}


@router.get("/dormant-collaborators")
async def dormant_collaborators(
    dormancy_days: int = Query(default=60, ge=7, le=365),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """External collaborators with no activity beyond dormancy threshold."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    dormant = await health_signal_service.get_dormant_collaborators(
        db, scoped_orgs=scoped_orgs, dormancy_days=dormancy_days, limit=limit
    )
    return {"dormant": dormant}
