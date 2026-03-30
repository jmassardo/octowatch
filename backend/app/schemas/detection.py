"""Pydantic schemas for detections and detection rules."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ─── Detection schemas ────────────────────────────────────────────────────────


class TicketSummary(BaseModel):
    id: int
    external_id: str
    external_url: str
    provider: str
    external_status: str | None


class DetectionListParams(BaseModel):
    """Query parameters for GET /detections."""

    model_config = ConfigDict(strict=True)

    status: str | None = Field(None, max_length=100)
    severity: str | None = Field(None, max_length=100)
    rule_id: int | None = None
    actor: str | None = Field(None, max_length=255)
    org: str | None = Field(None, max_length=255, pattern=r"^[a-zA-Z0-9_.-]+$")
    repo: str | None = Field(None, max_length=512)
    since: datetime | None = None
    until: datetime | None = None
    assigned_to: str | None = Field(None, max_length=255)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class DetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    rule_name: str | None = None
    rule_version: int
    severity: str
    confidence: str
    confidence_score: float
    status: str
    title: str
    description: str
    actor: str | None
    org: str | None
    repo: str | None
    source_ip: str | None
    window_start: datetime | None
    window_end: datetime | None
    event_ids: list[int]
    context_data: dict[str, Any]
    triggered_at: datetime
    assigned_to: str | None
    resolved_at: datetime | None
    resolution_note: str | None
    tickets: list[TicketSummary] = []


class DetectionListResponse(BaseModel):
    items: list[DetectionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class UpdateDetectionStatusRequest(BaseModel):
    status: str = Field(..., pattern=r"^(open|investigating|resolved|false_positive)$")
    resolution_note: str | None = Field(None, max_length=2000)


class AssignDetectionRequest(BaseModel):
    assigned_to: str = Field(..., max_length=255)


class DetectionSummary(BaseModel):
    """Aggregate counts for dashboard tiles."""

    by_severity: dict[str, int]
    by_status: dict[str, int]
    total: int


# ─── Rule schemas ─────────────────────────────────────────────────────────────


class FieldCondition(BaseModel):
    field: str = Field(..., max_length=255)
    operator: str = Field(
        ...,
        pattern=r"^(eq|ne|gt|gte|lt|lte|in|not_in|contains|not_contains|exists|not_exists|matches_glob|scope_contains)$",
    )
    value: Any = None


class SequenceStep(BaseModel):
    action: str = Field(..., max_length=255)
    min_count: int = Field(default=1, ge=1)


class RuleCreate(BaseModel):
    """Request body for POST /rules and PUT /rules/{id}."""

    name: str = Field(..., min_length=1, max_length=500)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    category: str = Field(
        ...,
        pattern=(
            r"^(access_control|data_exfiltration|defense_evasion|incident_response|"
            r"policy_violation|posture_change|posture_degradation|privilege_escalation|"
            r"supply_chain|exfiltration|account_compromise|secret_leakage|"
            r"branch_protection_bypass|pat_abuse|impossible_travel|"
            r"off_hours_anomaly|other)$"
        ),
    )
    default_severity: str = Field(..., pattern=r"^(critical|high|medium|low|info)$")
    default_confidence: str = Field(..., pattern=r"^(high|medium|low)$")
    logic_type: str = Field(
        ..., pattern=r"^(threshold|pattern|sequence|statistical|cross_namespace_sequence|posture)$"
    )
    logic_config: dict[str, Any]
    enabled: bool = True
    status: str = Field(default="draft", pattern=r"^(draft|active|deprecated)$")
    change_summary: str | None = Field(None, max_length=500)


class RuleStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(draft|active|deprecated)$")
    enabled: bool | None = None


class RuleTestRequest(BaseModel):
    lookback_hours: int = Field(default=24, ge=1, le=720)
    org: str | None = Field(None, max_length=255, pattern=r"^[a-zA-Z0-9_.-]+$")
    dry_run: bool = True


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    category: str
    default_severity: str
    default_confidence: str
    logic_type: str
    logic_config: dict[str, Any]
    enabled: bool
    status: str
    version: int
    git_commit_sha: str | None
    created_by: str
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


class RuleVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    version: int
    logic_config: dict[str, Any]
    change_summary: str | None
    changed_by: str
    git_commit_sha: str | None
    created_at: datetime


class SuppressionCreate(BaseModel):
    rule_id: int | None = None
    suppress_actor: str | None = Field(None, max_length=255)
    suppress_org: str | None = Field(None, max_length=255)
    suppress_repo: str | None = Field(None, max_length=512)
    reason: str = Field(..., min_length=1, max_length=2000)
    expires_at: datetime | None = None


class SuppressionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int | None
    suppress_actor: str | None
    suppress_org: str | None
    suppress_repo: str | None
    reason: str
    created_by: str
    expires_at: datetime | None
    active: bool
    created_at: datetime


class RuleListResponse(BaseModel):
    """Paginated list of rules."""

    items: list[RuleResponse]
    total: int
    limit: int
    offset: int


class ValidateConfigRequest(BaseModel):
    """Request body for POST /rules/validate-config."""

    logic_type: str = Field(
        ..., pattern=r"^(threshold|pattern|sequence|statistical|cross_namespace_sequence|posture)$"
    )
    logic_config: dict[str, Any]


class ValidateConfigResponse(BaseModel):
    """Response for POST /rules/validate-config."""

    valid: bool
    errors: list[str] = []
    warnings: list[str] = []


# ─── Rule test (dry-run) schemas ──────────────────────────────────────────────


class RuleTestEventRequest(BaseModel):
    """Request body for POST /rules/{rule_id}/test — dry-run a rule against a sample event."""

    event: dict[str, Any] = Field(
        ...,
        description="Sample audit event payload to evaluate the rule against.",
    )


class RuleTestEventResponse(BaseModel):
    """Response for POST /rules/{rule_id}/test — dry-run evaluation result."""

    matched: bool
    reason: str
    matched_fields: list[str] = []
