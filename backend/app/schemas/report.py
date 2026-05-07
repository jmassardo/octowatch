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


# ---------------------------------------------------------------------------
# Compliance report schemas
# ---------------------------------------------------------------------------


class ComplianceControlEvidence(BaseModel):
    """A single control section within a compliance report."""

    control_id: str | None = None
    function_id: str | None = None
    title: str
    description: str
    evidence: dict[str, Any]
    status: str = "evidence_collected"


class CompliancePeriod(BaseModel):
    """Report period metadata."""

    start: str
    end: str
    days: int


class ComplianceExecutiveSummary(BaseModel):
    """Executive summary metrics for a compliance report."""

    total_audit_events: int = 0
    total_evidence_events: int = 0
    unique_actors: int = 0
    controls_assessed: int = 0
    controls_with_evidence: int = 0
    compliance_score_pct: float | None = None
    unique_repositories: int | None = None
    functions_assessed: int | None = None
    functions_with_evidence: int | None = None
    detection_volume: int | None = None


class ComplianceReportEnvelope(BaseModel):
    """Response envelope for compliance report endpoints."""

    framework: str
    generated_at: str
    period: CompliancePeriod
    org: str | None = None
    executive_summary: ComplianceExecutiveSummary
    controls: list[ComplianceControlEvidence] | None = None
    functions: list[ComplianceControlEvidence] | None = None


# ---------------------------------------------------------------------------
# Report schedule schemas
# ---------------------------------------------------------------------------


class ReportScheduleCreate(BaseModel):
    """Create a new report schedule."""

    report_type: str = Field(..., max_length=50)
    org: str | None = None
    cron_expression: str = Field(..., max_length=100)
    export_format: str = Field(default="html", pattern=r"^(pdf|html|xlsx|csv)$")
    recipients: list[str] = Field(default_factory=list)
    enabled: bool = True


class ReportScheduleUpdate(BaseModel):
    """Update an existing report schedule (all fields optional)."""

    report_type: str | None = Field(None, max_length=50)
    org: str | None = None
    cron_expression: str | None = Field(None, max_length=100)
    export_format: str | None = Field(None, pattern=r"^(pdf|html|xlsx|csv)$")
    recipients: list[str] | None = None
    enabled: bool | None = None


class ReportScheduleResponse(BaseModel):
    """Response schema for report schedule CRUD."""

    id: int
    report_type: str
    org: str | None = None
    cron_expression: str
    export_format: str
    recipients: list[str]
    enabled: bool
    created_by: str
    last_run_at: datetime | None = None
    last_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Custom report schemas
# ---------------------------------------------------------------------------

_VALID_DATA_SOURCES = {"events", "detections", "posture", "copilot", "workflows", "users"}
_VALID_VISUALIZATIONS = {"table", "table_chart", "chart"}


class CustomReportColumnDef(BaseModel):
    """Column definition for a custom report."""

    field: str = Field(..., max_length=255)
    label: str = Field(..., max_length=255)
    visible: bool = True


class CustomReportFilterDef(BaseModel):
    """Filter definition for a custom report."""

    field: str = Field(..., max_length=255)
    operator: str = Field(..., pattern=r"^(eq|neq|gt|gte|lt|lte|contains|in)$")
    value: str | int | float | bool | list[str]


class CustomReportGrouping(BaseModel):
    """Grouping configuration for a custom report."""

    group_by: str | None = Field(None, max_length=255)
    time_bucket: str | None = Field(None, pattern=r"^(hourly|daily|weekly|monthly)$")


class CustomReportCreate(BaseModel):
    """Create a new custom report definition."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    data_sources: list[str] = Field(..., min_length=1)
    columns: list[CustomReportColumnDef] = Field(default_factory=list)
    filters: list[CustomReportFilterDef] = Field(default_factory=list)
    grouping: CustomReportGrouping = Field(default_factory=CustomReportGrouping)
    visualization: str = Field(default="table", pattern=r"^(table|table_chart|chart)$")


class CustomReportUpdate(BaseModel):
    """Update an existing custom report definition (all fields optional)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    data_sources: list[str] | None = None
    columns: list[CustomReportColumnDef] | None = None
    filters: list[CustomReportFilterDef] | None = None
    grouping: CustomReportGrouping | None = None
    visualization: str | None = Field(None, pattern=r"^(table|table_chart|chart)$")


class CustomReportResponse(BaseModel):
    """Response schema for custom report CRUD."""

    id: int
    name: str
    description: str | None = None
    owner_login: str
    data_sources: list[str]
    columns: list[CustomReportColumnDef]
    filters: list[CustomReportFilterDef]
    grouping: CustomReportGrouping
    visualization: str
    is_shared: bool
    shared_with: list[str]
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportRunParams(BaseModel):
    """Parameters for running a custom report."""

    window_days: int = Field(default=30, ge=1, le=365)
    start_date: str | None = None
    end_date: str | None = None
    org: str | None = Field(None, max_length=255)
    granularity: str = Field(default="daily", pattern=r"^(hourly|daily|weekly|monthly)$")


class ReportRunResult(BaseModel):
    """Result of running a custom report."""

    report_id: int
    report_name: str
    data_sources: list[str]
    generated_at: datetime
    window_days: int
    org: str | None = None
    data: list[dict[str, Any]]
    row_count: int


class ShareReportRequest(BaseModel):
    """Request body for sharing a custom report."""

    logins: list[str] = Field(..., min_length=1, max_length=50)
