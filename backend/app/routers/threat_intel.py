"""Threat intelligence CRUD router: indicators and feeds."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.schemas.threat_intel import (
    AnalyticsResponse,
    BulkIndicatorCreate,
    BulkIndicatorResponse,
    FeedCreate,
    FeedListResponse,
    FeedRefreshResponse,
    FeedResponse,
    FeedUpdate,
    IndicatorCreate,
    IndicatorListResponse,
    IndicatorResponse,
    IndicatorUpdate,
    MatchListResponse,
)
from app.services import threat_intel_service

router = APIRouter(prefix="/threat-intel", tags=["threat-intel"])

# ─── Indicators ───────────────────────────────────────────────────────────────


@router.post(
    "/indicators",
    response_model=IndicatorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_indicator(
    body: IndicatorCreate,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    _csrf: None = Depends(verify_csrf),
) -> Any:
    """Create a new threat intelligence indicator."""
    result = await threat_intel_service.create_indicator(
        db,
        indicator_type=body.indicator_type,
        value=body.value,
        source=body.source,
        confidence=body.confidence,
        added_by=user.github_login,
        expires_at=body.expires_at.isoformat() if body.expires_at else None,
        notes=body.notes,
    )
    return result


@router.get("/indicators", response_model=IndicatorListResponse)
async def list_indicators(
    indicator_type: str | None = None,
    active_only: bool = True,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "view")),
) -> Any:
    """List threat intelligence indicators with filtering and pagination."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 200:
        page_size = 50

    items, total = await threat_intel_service.get_indicators(
        db,
        indicator_type=indicator_type,
        active_only=active_only,
        search=search,
        page=page,
        page_size=page_size,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/indicators/{indicator_id}", response_model=IndicatorResponse)
async def update_indicator(
    indicator_id: int,
    body: IndicatorUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    _csrf: None = Depends(verify_csrf),
) -> Any:
    """Update an existing threat intelligence indicator."""
    updates = body.model_dump(exclude_unset=True)
    if "expires_at" in updates and updates["expires_at"] is not None:
        updates["expires_at"] = updates["expires_at"].isoformat()

    result = await threat_intel_service.update_indicator(db, indicator_id, updates=updates)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Indicator not found")
    return result


@router.delete("/indicators/{indicator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_indicator(
    indicator_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    _csrf: None = Depends(verify_csrf),
) -> None:
    """Soft-delete a threat intelligence indicator (sets active=false)."""
    deleted = await threat_intel_service.soft_delete_indicator(db, indicator_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Indicator not found or already inactive",
        )


# ─── Feeds ────────────────────────────────────────────────────────────────────


@router.post(
    "/feeds",
    response_model=FeedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feed(
    body: FeedCreate,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    _csrf: None = Depends(verify_csrf),
) -> Any:
    """Configure a new threat intelligence feed for auto-import."""
    result = await threat_intel_service.create_feed(
        db,
        name=body.name,
        url=body.url,
        feed_type=body.feed_type,
        refresh_interval_minutes=body.refresh_interval_minutes,
        created_by=user.github_login,
    )
    return result


@router.get("/feeds", response_model=FeedListResponse)
async def list_feeds(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "view")),
) -> Any:
    """List all configured threat intelligence feeds."""
    items = await threat_intel_service.get_feeds(db)
    return {"items": items}


@router.patch("/feeds/{feed_id}", response_model=FeedResponse)
async def update_feed(
    feed_id: int,
    body: FeedUpdate,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    _csrf: None = Depends(verify_csrf),
) -> Any:
    """Update an existing threat intelligence feed."""
    updates = body.model_dump(exclude_unset=True)
    result = await threat_intel_service.update_feed(db, feed_id, updates=updates)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    return result


@router.delete("/feeds/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    _csrf: None = Depends(verify_csrf),
) -> None:
    """Delete a threat intelligence feed and its indicators."""
    deleted = await threat_intel_service.delete_feed(db, feed_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")


@router.post("/feeds/{feed_id}/refresh", response_model=FeedRefreshResponse)
async def refresh_feed(
    feed_id: int,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    _csrf: None = Depends(verify_csrf),
) -> Any:
    """Trigger a manual refresh of a threat intelligence feed."""
    result = await threat_intel_service.refresh_feed(db, feed_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feed not found")
    return {
        "feed_id": result["id"],
        "status": "refreshing",
        "indicator_count": result.get("last_indicator_count"),
        "message": f"Feed '{result['name']}' refresh initiated",
    }


@router.post("/indicators/bulk", response_model=BulkIndicatorResponse)
async def bulk_create_indicators(
    body: BulkIndicatorCreate,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    _csrf: None = Depends(verify_csrf),
) -> Any:
    """Bulk import threat intelligence indicators."""
    indicators = [ind.model_dump() for ind in body.indicators]
    result = await threat_intel_service.bulk_create_indicators(
        db,
        indicators=indicators,
        added_by=user.github_login,
    )
    return result


@router.get("/matches", response_model=MatchListResponse)
async def list_matches(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "view")),
) -> Any:
    """List detections that matched threat intelligence indicators."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 200:
        page_size = 50
    items, total, total_24h, unique_indicators, top_feed = await threat_intel_service.get_matches(
        db,
        page=page,
        page_size=page_size,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_24h": total_24h,
        "unique_indicators": unique_indicators,
        "top_feed": top_feed,
    }


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission("rules", "view")),
) -> Any:
    """Get aggregate threat intelligence analytics."""
    return await threat_intel_service.get_analytics(db)
