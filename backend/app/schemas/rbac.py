"""Pydantic schemas for RBAC role management and permissions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RolePermissionSummary(BaseModel):
    """Brief role representation for list endpoints."""

    id: int
    name: str
    display_name: str
    description: str | None = None
    permission_count: int
    is_system: bool
    is_custom: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleDetailResponse(BaseModel):
    """Full role detail with all permissions."""

    id: int
    name: str
    display_name: str
    description: str | None = None
    permissions: list[str]
    is_system: bool
    is_custom: bool
    created_at: datetime
    updated_at: datetime | None = None
    assignment_count: int = 0

    model_config = {"from_attributes": True}


class RoleCreateRequest(BaseModel):
    """Request body for creating a custom role."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Unique role identifier (lowercase, underscores allowed)",
    )
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(None, max_length=512)
    permissions: list[str] = Field(
        ...,
        min_length=1,
        description="List of permission strings in resource:action format",
    )


class RoleUpdateRequest(BaseModel):
    """Request body for updating a custom role."""

    display_name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=512)
    permissions: list[str] | None = Field(
        None,
        min_length=1,
        description="Full replacement list of permissions",
    )


class UserPermissionsResponse(BaseModel):
    """Response for /auth/me/permissions endpoint."""

    user_id: str
    roles: list[str]
    permissions: list[str]
    scopes: PermissionScopes


class PermissionScopes(BaseModel):
    """Scope information for the permissions response."""

    orgs: list[str] | None = None
    repos: list[str] | None = None


class PermissionDefinition(BaseModel):
    """A single permission definition with resource, action, and description."""

    permission: str = Field(..., description="Permission string in resource:action format")
    resource: str
    action: str
    resource_label: str
    action_label: str
    description: str
    category: str


class AvailablePermissionsResponse(BaseModel):
    """Response listing all available permissions grouped by category."""

    permissions: list[PermissionDefinition]
    categories: list[str]
