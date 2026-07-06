"""Telemetry router: Ingestion pipeline monitoring endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.services import rbac_service, telemetry_service

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs; raise 403 when user has no org access."""
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs and current_user.scope_type != "global":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


@router.get("/summary", response_model=dict[str, Any])
async def telemetry_summary(
    current_user: AuthenticatedUser = Depends(require_permission("telemetry", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate telemetry metrics for the status strip."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await telemetry_service.get_telemetry_summary(db, scoped_orgs=scoped_orgs)


@router.get("/stream-status", response_model=dict[str, Any])
async def stream_status(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_permission("telemetry", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Per-stream ingestion status across scoped orgs."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    streams = await telemetry_service.get_stream_status(
        db,
        scoped_orgs=scoped_orgs,
        limit=limit,
    )
    return {"streams": streams}


@router.get("/worker-health", response_model=dict[str, Any])
async def worker_health(
    current_user: AuthenticatedUser = Depends(require_permission("telemetry", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Worker health events and active worker rollup."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await telemetry_service.get_worker_health(db, scoped_orgs=scoped_orgs)


@router.get("/event-volume", response_model=dict[str, Any])
async def event_volume(
    bucket: str = Query(default="hour"),
    hours: int = Query(default=24, ge=1, le=168),
    current_user: AuthenticatedUser = Depends(require_permission("telemetry", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bucketed ingestion volume and top actions."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await telemetry_service.get_event_volume(
        db,
        scoped_orgs=scoped_orgs,
        bucket=bucket,
        hours=hours,
    )


@router.get("/errors", response_model=dict[str, Any])
async def ingestion_errors(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(require_permission("telemetry", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Recent ingestion failures and stale-ingestion gaps."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await telemetry_service.get_ingestion_errors(
        db,
        scoped_orgs=scoped_orgs,
        limit=limit,
    )
