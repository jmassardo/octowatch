"""Pydantic schemas for GitHub Enterprise Sync API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal  # noqa: TC003

from pydantic import BaseModel, Field

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
    cursors: list[CursorRow] = []

    model_config = {"from_attributes": True}


class SyncRunSummary(BaseModel):
    id: uuid.UUID
    status: str
    trigger_type: str
    triggered_by: str | None
    started_at: datetime | None
    completed_at: datetime | None

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
