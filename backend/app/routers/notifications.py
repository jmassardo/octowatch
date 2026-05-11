"""Notifications router: in-app notifications and user preferences."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.models.notification import Notification, NotificationPreference
from app.schemas.notification import (
    MarkReadResponse,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── In-App Notifications ─────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity: str | None = Query(None, pattern=r"^(info|warning|critical)$"),
    read: bool | None = Query(None),
    source: str | None = Query(None, pattern=r"^(detection|sync|system)$"),
    current_user: AuthenticatedUser = Depends(require_permission("notifications", "view")),
    db: AsyncSession = Depends(get_db),
) -> NotificationListResponse:
    """List notifications for the authenticated user with optional filters."""
    base_filter = Notification.user_id == current_user.github_login

    stmt = select(Notification).where(base_filter).order_by(Notification.created_at.desc())

    if severity is not None:
        stmt = stmt.where(Notification.severity == severity)
    if read is not None:
        stmt = stmt.where(Notification.read == read)
    if source is not None:
        stmt = stmt.where(Notification.source == source)

    # Total count (with filters)
    count_stmt = select(func.count()).select_from(
        stmt.with_only_columns(Notification.id).subquery()
    )
    total = (await db.execute(count_stmt)).scalar_one()

    # Unread count (no filters — always shows total unread)
    unread_stmt = select(func.count()).where(base_filter, Notification.read.is_(False))
    unread_count = (await db.execute(unread_stmt)).scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    items = [NotificationResponse.model_validate(n) for n in result.scalars().all()]

    logger.info(
        "notifications.listed",
        user=current_user.github_login,
        total=total,
        page=page,
    )

    return NotificationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
        unread_count=unread_count,
    )


@router.put(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    dependencies=[Depends(verify_csrf)],
)
async def mark_notification_read(
    notification_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("notifications", "view")),
    db: AsyncSession = Depends(get_db),
) -> NotificationResponse:
    """Mark a single notification as read."""
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == current_user.github_login,
    )
    result = await db.execute(stmt)
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.read = True
    await db.flush()

    logger.info(
        "notification.marked_read",
        user=current_user.github_login,
        notification_id=notification_id,
    )

    return NotificationResponse.model_validate(notification)


@router.post(
    "/read-all",
    response_model=MarkReadResponse,
    dependencies=[Depends(verify_csrf)],
)
async def mark_all_read(
    current_user: AuthenticatedUser = Depends(require_permission("notifications", "view")),
    db: AsyncSession = Depends(get_db),
) -> MarkReadResponse:
    """Mark all unread notifications as read for the authenticated user."""
    stmt = (
        update(Notification)
        .where(
            Notification.user_id == current_user.github_login,
            Notification.read.is_(False),
        )
        .values(read=True)
    )
    result = await db.execute(stmt)
    updated = int(getattr(result, "rowcount", 0) or 0)

    logger.info(
        "notifications.marked_all_read",
        user=current_user.github_login,
        updated=updated,
    )

    return MarkReadResponse(updated=updated)


# ── Notification Preferences ─────────────────────────────────────────────────


@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_preferences(
    current_user: AuthenticatedUser = Depends(require_permission("notifications", "view")),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferencesResponse:
    """Get notification preferences for the authenticated user."""
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == current_user.github_login
    )
    result = await db.execute(stmt)
    prefs = result.scalar_one_or_none()

    if prefs is None:
        # Return defaults when no preferences record exists
        return NotificationPreferencesResponse(
            in_app_enabled=True,
            email_enabled=False,
            slack_enabled=False,
            severity_filter="info",
            detection_alerts=True,
            sync_alerts=True,
            system_alerts=True,
            updated_at=datetime.now(UTC),
        )

    return NotificationPreferencesResponse.model_validate(prefs)


@router.put(
    "/preferences",
    response_model=NotificationPreferencesResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_preferences(
    body: NotificationPreferencesUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("notifications", "view")),
    db: AsyncSession = Depends(get_db),
) -> NotificationPreferencesResponse:
    """Create or update notification preferences for the authenticated user."""
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == current_user.github_login
    )
    result = await db.execute(stmt)
    prefs = result.scalar_one_or_none()

    update_data = body.model_dump(exclude_unset=True)

    if prefs is None:
        prefs = NotificationPreference(
            user_id=current_user.github_login,
            **update_data,
        )
        db.add(prefs)
    else:
        for field, value in update_data.items():
            setattr(prefs, field, value)

    await db.flush()
    await db.refresh(prefs)

    logger.info(
        "notification_preferences.updated",
        user=current_user.github_login,
        fields=list(update_data.keys()),
    )

    return NotificationPreferencesResponse.model_validate(prefs)
