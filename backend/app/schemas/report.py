"""Pydantic schemas for reports and metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportParams(BaseModel):
    """Common query parameters for all report endpoints."""

    org: str | None = Field(None, max_length=255, pattern=r"^[a-zA-Z0-9_.-]+$")
    granularity: str = Field(
        default="daily",
        pattern=r"^(daily|weekly|monthly)$",
    )
    window: str = Field(default="30d", pattern=r"^(30d|60d|90d)$")


class ReportEnvelope(BaseModel):
    """Standard report response envelope."""

    org: str | None
    granularity: str
    window: str
    generated_at: datetime
    data: list[dict[str, Any]]


class MAUBucket(BaseModel):
    bucket: datetime
    unique_actor_count: int
    unique_bot_actor_count: int
    new_actor_count: int


class SeatUtilizationBucket(BaseModel):
    bucket: datetime
    active_seat_count: int
    provisioned_seat_count: int
    utilization_pct: float


class RepoCreationRateBucket(BaseModel):
    bucket: datetime
    repos_created: int
    repos_deleted: int
    repos_transferred: int
    repos_made_public: int


class ActionsVolumeBucket(BaseModel):
    bucket: datetime
    workflow_runs_total: int
    workflow_runs_succeeded: int
    workflow_runs_failed: int
    success_rate_pct: float
    unique_workflows: int


class CopilotSeatsBucket(BaseModel):
    bucket: datetime
    seats_assigned: int
    seats_revoked: int
    seats_net: int
    policy_change_count: int


class CodespaceHoursBucket(BaseModel):
    bucket: datetime
    codespace_create_count: int
    codespace_delete_count: int
    unique_actors: int
    unique_repos: int


class PATCountsBucket(BaseModel):
    bucket: datetime
    pats_created: int
    pats_deleted: int
    pats_expired: int
    fine_grained_pats: int
    classic_pats: int
    high_access_pats: int


class WebhookCountsBucket(BaseModel):
    bucket: datetime
    webhooks_created: int
    webhooks_deleted: int
    app_installs: int
    app_uninstalls: int
    unique_webhook_targets: int
