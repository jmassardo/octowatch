"""Pydantic schemas for user profile and preferences endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserProfileResponse(BaseModel):
    """Response for GET /user/profile."""

    model_config = ConfigDict(from_attributes=True)

    github_login: str
    github_id: int
    display_name: str
    email: str | None = None
    avatar_url: str | None = None
    roles: list[str]
    scoped_orgs: list[str]
    scoped_repos: list[str]
    scope_type: str
    login_history: list[LoginHistoryEntry]
    session_expires_at: str


class LoginHistoryEntry(BaseModel):
    """A single login history entry."""

    model_config = ConfigDict(from_attributes=True)

    timestamp: str
    ip_address: str | None = None


class UserPreferences(BaseModel):
    """User preferences — both request and response body."""

    model_config = ConfigDict(from_attributes=True)

    theme: str = Field(default="system", pattern=r"^(system|light|dark)$")
    default_dashboard_view: str = Field(
        default="operations",
        pattern=r"^(operations|executive|security|cicd)$",
    )
    default_org: str = ""
    timezone: str = "UTC"
    date_format: str = Field(default="relative", pattern=r"^(relative|absolute)$")
    items_per_page: int = Field(default=25, ge=10, le=200)


class SessionInfo(BaseModel):
    """A single active session entry."""

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    is_current: bool = False


class SessionListResponse(BaseModel):
    """Response for GET /user/sessions."""

    sessions: list[SessionInfo]


class SessionRevokeResponse(BaseModel):
    """Response for DELETE /user/sessions/{id}."""

    status: str = "revoked"


# Rebuild UserProfileResponse now that LoginHistoryEntry is defined
UserProfileResponse.model_rebuild()
