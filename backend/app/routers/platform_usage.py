"""Platform usage analytics API endpoints."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_permission
from app.services import platform_usage_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/platform-usage", tags=["platform-usage"])


@router.get("/summary")
async def get_usage_summary(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("platform_usage", "read")),
    org: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Get aggregated usage summary across all feature areas."""
    return await platform_usage_service.get_usage_summary(db, org=org, days=days)


@router.get("/top-consumers")
async def get_top_consumers(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("platform_usage", "read")),
    org: str | None = Query(None),
    feature_area: str = Query("actions"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Get top consumers for a specific feature area."""
    return await platform_usage_service.get_top_consumers(
        db, org=org, feature_area=feature_area, days=days, limit=limit
    )


@router.get("/trends")
async def get_usage_trends(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("platform_usage", "read")),
    org: str | None = Query(None),
    feature_area: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Get daily usage trends for charting."""
    return await platform_usage_service.get_usage_trends(
        db, org=org, feature_area=feature_area, days=days
    )


@router.get("/anomalies")
async def get_anomalies(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("platform_usage", "read")),
    org: str | None = Query(None),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Get recent utilization anomaly detections."""
    return await platform_usage_service.get_anomalies(db, org=org, days=days, limit=limit)


@router.get("/user/{login}")
async def get_user_usage(
    login: str,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("platform_usage", "read")),
    org: str | None = Query(None),
    days: int = Query(90, ge=1, le=365),
) -> dict[str, Any]:
    """Get usage profile for a specific user."""
    return await platform_usage_service.get_user_usage(db, login=login, org=org, days=days)
