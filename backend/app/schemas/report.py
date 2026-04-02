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

    report_type: str
    org: str | None = None
    granularity: str
    window_days: int
    data_source: str = "Audit Events"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    data: list[dict[str, Any]]


class MAUBucket(BaseModel):
    """Monthly Active Users bucket — matches report_service output."""

    bucket: datetime
    unique_actors: int
    total_events: int


class SeatUtilizationBucket(BaseModel):
    """Platform seat utilization based on GHEC audit event actor counts."""

    bucket: datetime
    active_seat_count: int
    provisioned_seat_count: int
    utilization_pct: float


class RepoCreationRateBucket(BaseModel):
    """Repository creation rate bucket — matches report_service output."""

    bucket: datetime
    org: str | None = None
    repos_created: int
    unique_creators: int


class ActionsVolumeBucket(BaseModel):
    """GitHub Actions workflow volume bucket — matches report_service output."""

    bucket: datetime
    org: str | None = None
    workflow_runs: int
    unique_actors: int
    unique_repos: int


class CopilotSeatsBucket(BaseModel):
    """Copilot seat assignment/removal bucket from Copilot audit events."""

    bucket: datetime
    seats_assigned: int
    seats_revoked: int
    seats_net: int
    policy_change_count: int


class CodespaceHoursBucket(BaseModel):
    """Codespace usage bucket — matches report_service output."""

    bucket: datetime
    org: str | None = None
    codespace_events: int
    unique_users: int
    total_billable_hours: float


class PATCountsBucket(BaseModel):
    """Personal Access Token event bucket — matches report_service output."""

    bucket: datetime
    org: str | None = None
    actions: dict[str, int] = Field(default_factory=dict)


class WebhookCountsBucket(BaseModel):
    """Webhook event bucket — matches report_service output."""

    bucket: datetime
    org: str | None = None
    actions: dict[str, int] = Field(default_factory=dict)
