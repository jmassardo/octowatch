"""Pydantic schemas for team management and team-based RBAC."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# ─── Team CRUD ────────────────────────────────────────────────────────────────


class TeamCreateRequest(BaseModel):
    """Request body for creating a team."""

    name: str = Field(..., min_length=2, max_length=128, description="Human-readable team name")
    description: str | None = Field(None, max_length=512)
    github_org: str | None = Field(None, max_length=128, description="GitHub org for team sync")
    github_team_slug: str | None = Field(
        None, max_length=128, description="GitHub team slug for sync"
    )
    auto_sync: bool = Field(False, description="Enable automatic membership sync from GitHub")


class TeamUpdateRequest(BaseModel):
    """Request body for updating a team."""

    name: str | None = Field(None, min_length=2, max_length=128)
    description: str | None = Field(None, max_length=512)
    github_org: str | None = Field(None, max_length=128)
    github_team_slug: str | None = Field(None, max_length=128)
    auto_sync: bool | None = None


class TeamMemberResponse(BaseModel):
    """A single team member."""

    user_login: str
    added_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamRoleResponse(BaseModel):
    """A role assigned to a team."""

    role_id: int
    role_name: str
    role_display_name: str
    org_slug: str | None = None
    repo_slugs: list[str] | None = None
    assigned_by: str
    created_at: datetime


class TeamSummaryResponse(BaseModel):
    """Brief team representation for list endpoints."""

    id: int
    name: str
    slug: str
    description: str | None = None
    member_count: int
    role_count: int
    auto_sync: bool
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamDetailResponse(BaseModel):
    """Full team detail with members and roles."""

    id: int
    name: str
    slug: str
    description: str | None = None
    github_org: str | None = None
    github_team_slug: str | None = None
    auto_sync: bool
    created_by: str
    created_at: datetime
    updated_at: datetime | None = None
    members: list[TeamMemberResponse]
    roles: list[TeamRoleResponse]

    model_config = {"from_attributes": True}


class TeamMemberAddRequest(BaseModel):
    """Request body for adding a member to a team."""

    user_login: str = Field(..., min_length=1, max_length=128)


class TeamRoleAssignRequest(BaseModel):
    """Request body for assigning a role to a team."""

    role_id: int
    org_slug: str | None = Field(None, max_length=128)
    repo_slugs: list[str] | None = None


# ─── Audit Log ────────────────────────────────────────────────────────────────


class AuditLogEntryResponse(BaseModel):
    """A single audit log entry."""

    id: int
    timestamp: datetime
    actor: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict[str, object] | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    outcome: str

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """Paginated audit log response."""

    items: list[AuditLogEntryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
