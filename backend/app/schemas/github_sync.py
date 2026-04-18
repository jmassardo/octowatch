"""Pydantic schemas for GitHub Enterprise Sync API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal  # noqa: TC003

from pydantic import BaseModel, Field, field_validator

# ── Request schemas ───────────────────────────────────────────────────────────


class SyncTriggerRequest(BaseModel):
    scope: Literal[
        "full",
        "orgs",
        "enterprise_members",
        "org_members",
        "repositories",
        "teams",
        "team_members",
        "branch_protections",
        "installations",
        "outside_collaborators",
        "secret_scanning_alerts",
        "dependabot_alerts",
        "license_consumption",
        "code_scanning_alerts",
        "actions_workflows",
        "mfa_status",
        "audit_log",
        "repo_commits",
        "pull_requests",
        "workflow_runs",
        "issues",
        "deployments",
    ] = "full"


class SyncConfigUpdateRequest(BaseModel):
    sync_enabled: bool | None = None
    interval_days: int | None = Field(None, ge=60, le=90)
    orgs: list[str] | None = None  # replace (not append) the configured orgs list


# ── Response schemas ───────────────────────────────────────────────────────────


class SyncTriggerResponse(BaseModel):
    run_id: uuid.UUID
    status: str


class CursorRow(BaseModel):
    entity_type: str
    org: str | None
    last_cursor: str | None
    items_synced: int
    status: str

    model_config = {"from_attributes": True}


class SyncRunDetail(BaseModel):
    id: uuid.UUID
    status: str
    trigger_type: str
    triggered_by: str | None
    scope: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    entity_counts: dict[str, Any] | None
    post_processing_status: str | None = None
    cursors: list[CursorRow] = []

    model_config = {"from_attributes": True}


class SyncRunSummary(BaseModel):
    id: uuid.UUID
    status: str
    trigger_type: str
    triggered_by: str | None
    started_at: datetime | None
    completed_at: datetime | None
    post_processing_status: str | None = None

    model_config = {"from_attributes": True}


class SyncRunsResponse(BaseModel):
    items: list[SyncRunSummary]
    total: int
    page: int
    page_size: int
    has_next: bool


class SyncConfigResponse(BaseModel):
    app_id: int | None
    enterprise_slug: str | None
    installation_ids: list[dict]  # [{"org": "acme", "installation_id": 12345}, ...]
    sync_enabled: bool
    interval_days: int
    orgs: list[str]
    # NEVER includes private_key_path or any token value


# ── Schedule schemas ───────────────────────────────────────────────────────────

VALID_INTERVAL_HOURS = frozenset({6, 12, 24, 48, 72, 168})


class SyncScheduleResponse(BaseModel):
    """Current sync schedule configuration."""

    enabled: bool = False
    interval_hours: int = 24
    scope: str = "full"
    next_run_at: datetime | None = None
    last_completed_at: datetime | None = None


class SyncScheduleUpdateRequest(BaseModel):
    """Update request for sync schedule configuration."""

    enabled: bool | None = None
    interval_hours: int | None = None
    scope: str | None = None

    @field_validator("interval_hours")
    @classmethod
    def validate_interval_hours(cls, v: int | None) -> int | None:
        if v is not None and v not in VALID_INTERVAL_HOURS:
            msg = f"interval_hours must be one of {sorted(VALID_INTERVAL_HOURS)}"
            raise ValueError(msg)
        return v

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str | None) -> str | None:
        valid_scopes = {
            "full",
            "orgs",
            "enterprise_members",
            "org_members",
            "repositories",
            "teams",
            "team_members",
            "branch_protections",
            "installations",
            "outside_collaborators",
            "secret_scanning_alerts",
            "dependabot_alerts",
            "license_consumption",
            "code_scanning_alerts",
            "actions_workflows",
            "mfa_status",
            "repo_commits",
            "pull_requests",
            "workflow_runs",
            "issues",
            "deployments",
        }
        if v is not None and v not in valid_scopes:
            msg = f"scope must be one of {sorted(valid_scopes)}"
            raise ValueError(msg)
        return v


# ── Sync log schemas ───────────────────────────────────────────────────────────


class SyncLogEntryResponse(BaseModel):
    """Single log entry emitted during a sync run."""

    seq: int
    timestamp: datetime
    level: str
    message: str
    entity_type: str | None = None
    org: str | None = None
    details: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class SyncLogsResponse(BaseModel):
    """Paginated log entries for a sync run."""

    entries: list[SyncLogEntryResponse]
    last_seq: int
