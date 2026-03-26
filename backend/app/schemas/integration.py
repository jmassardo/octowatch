"""Pydantic schemas for integration endpoints (ticketing, notifications, IdP)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TicketingConfigCreate(BaseModel):
    provider: str = Field(..., pattern=r"^(jira|github_issues)$")
    display_name: str = Field(..., min_length=1, max_length=255)
    target: str = Field(..., max_length=1000)
    project_key: str | None = Field(None, max_length=50)
    default_issue_type: str = Field(default="Bug", max_length=100)
    severity_priority_map: dict[str, str] = Field(default_factory=dict)
    auto_create: bool = False
    auto_create_severities: list[str] = Field(default_factory=lambda: ["critical", "high"])
    credential_env_var: str = Field(..., max_length=255)
    enabled: bool = True


class TicketingConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    display_name: str
    target: str
    project_key: str | None
    default_issue_type: str
    auto_create: bool
    auto_create_severities: list[str]
    enabled: bool
    created_by: str
    created_at: datetime


class NotificationConfigCreate(BaseModel):
    channel_type: str = Field(..., pattern=r"^(slack|email)$")
    display_name: str = Field(..., min_length=1, max_length=255)
    target: str = Field(..., max_length=1000)
    credential_env_var: str | None = Field(None, max_length=255)
    notify_severities: list[str] = Field(default_factory=lambda: ["critical", "high"])
    cooldown_seconds: int = Field(default=3600, ge=60, le=86400)
    enabled: bool = True


class NotificationConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_type: str
    display_name: str
    target: str
    notify_severities: list[str]
    cooldown_seconds: int
    enabled: bool
    created_by: str
    created_at: datetime


class IdpConfigCreate(BaseModel):
    provider: str = Field(..., pattern=r"^(okta|entra|google_workspace)$")
    display_name: str = Field(..., min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)


class IdpEnrichmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    github_login: str
    idp_provider: str
    idp_user_id: str | None
    email: str | None
    display_name: str | None
    department: str | None
    title: str | None
    employment_status: str | None
    manager_login: str | None
    location: str | None
    timezone: str | None
    last_synced_at: datetime
    sync_error: str | None


class RoleAssignmentCreate(BaseModel):
    github_login: str = Field(..., max_length=255)
    github_team_id: int | None = None
    github_team_slug: str | None = Field(None, max_length=255)
    saml_subject: str | None = Field(None, max_length=500)
    role_name: str = Field(..., pattern=r"^(analyst|report_admin|rule_author|sys_admin)$")
    scope_type: str = Field(..., pattern=r"^(global|org|repo)$")
    scope_value: str | None = Field(None, max_length=512)
    expires_at: datetime | None = None


class RoleAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    github_login: str
    github_team_slug: str | None
    role_id: int
    scope_type: str
    scope_value: str | None
    granted_by: str
    granted_at: datetime
    expires_at: datetime | None
    active: bool


class IngestionSourceCreate(BaseModel):
    source_type: str = Field(..., pattern=r"^(s3|azure_blob|minio)$")
    source_name: str = Field(..., min_length=1, max_length=255)
    source_region: str | None = Field(None, max_length=50)
    source_prefix: str = Field(default="", max_length=500)
    poll_interval_sec: int = Field(default=300, ge=60, le=3600)


class IngestionSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_name: str
    source_region: str | None
    source_prefix: str
    last_prefix: str
    last_event_count: int
    last_processed_at: datetime | None
    status: str
    error_message: str | None
    error_count: int
    poll_interval_sec: int
    created_at: datetime
    updated_at: datetime


class RetentionConfig(BaseModel):
    events_retention_days: int = Field(default=365, ge=7, le=3650)
    raw_payloads_retention_days: int = Field(default=90, ge=1, le=3650)
    detections_retention_days: int = Field(default=730, ge=30, le=3650)
    audit_trail_retention_days: int = Field(default=730, ge=30, le=3650)
