"""Pydantic schemas for in-app notification endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── Notification Schemas ─────────────────────────────────────────────────────


class NotificationResponse(BaseModel):
    """Single in-app notification returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    title: str
    message: str
    severity: str
    read: bool
    source: str
    link: str | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated list of notifications."""

    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    unread_count: int


class MarkReadResponse(BaseModel):
    """Response after marking notification(s) as read."""

    updated: int


# ── Notification Preferences Schemas ─────────────────────────────────────────


class NotificationPreferencesResponse(BaseModel):
    """Current notification preferences for the authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    in_app_enabled: bool
    email_enabled: bool
    slack_enabled: bool
    severity_filter: str
    detection_alerts: bool
    sync_alerts: bool
    system_alerts: bool
    updated_at: datetime


class NotificationPreferencesUpdate(BaseModel):
    """Request body for updating notification preferences."""

    in_app_enabled: bool | None = None
    email_enabled: bool | None = None
    slack_enabled: bool | None = None
    severity_filter: str | None = Field(None, pattern=r"^(info|warning|critical)$")
    detection_alerts: bool | None = None
    sync_alerts: bool | None = None
    system_alerts: bool | None = None
