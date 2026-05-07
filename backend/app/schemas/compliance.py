"""Pydantic schemas for the Compliance Center endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Compliance Summary
# ---------------------------------------------------------------------------


class FrameworkScore(BaseModel):
    """Score and metadata for a single compliance framework."""

    name: str
    display_name: str
    score: float = Field(ge=0, le=100)
    controls_passing: int
    controls_total: int
    last_generated: str | None = None


class ComplianceSummary(BaseModel):
    """Aggregate compliance posture across all frameworks."""

    overall_score: float = Field(ge=0, le=100)
    frameworks_tracked: int
    controls_passing: int
    controls_total: int
    critical_gaps: int
    last_assessment_date: str | None = None
    frameworks: list[FrameworkScore]


# ---------------------------------------------------------------------------
# Framework Controls
# ---------------------------------------------------------------------------


class ControlItem(BaseModel):
    """A single compliance control within a framework."""

    control_id: str
    title: str
    description: str
    status: str = Field(
        pattern=r"^(pass|fail|partial|not_assessed)$",
        default="not_assessed",
    )
    evidence_summary: str = ""
    last_checked: str | None = None
    category: str = ""


class FrameworkDetail(BaseModel):
    """Detailed controls for a specific compliance framework."""

    name: str
    display_name: str
    score: float = Field(ge=0, le=100)
    controls: list[ControlItem]
    last_generated: str | None = None


# ---------------------------------------------------------------------------
# Policy Checks
# ---------------------------------------------------------------------------


class PolicyCheckResult(BaseModel):
    """Result of a single automated policy check."""

    check_name: str
    display_name: str
    status: str = Field(pattern=r"^(pass|fail)$")
    scope: str = Field(pattern=r"^(org|repo)$")
    last_checked: str
    details: str = ""


class PolicyCheckResults(BaseModel):
    """Collection of policy check results."""

    checks: list[PolicyCheckResult]
    last_run: str | None = None
    checks_passing: int
    checks_total: int


# ---------------------------------------------------------------------------
# GDPR Summary
# ---------------------------------------------------------------------------


class DataProcessingActivity(BaseModel):
    """A data processing activity record for GDPR."""

    activity_name: str
    purpose: str
    legal_basis: str
    data_categories: list[str]
    retention_period: str
    status: str = "active"


class GDPRSummary(BaseModel):
    """GDPR compliance dashboard summary."""

    data_processing_activities: list[DataProcessingActivity]
    consent_tracking_enabled: bool = False
    dsr_requests_total: int = 0
    dsr_requests_completed: int = 0
    dsr_requests_pending: int = 0
    breach_notification_readiness: list[dict[str, Any]] = Field(default_factory=list)
    data_retention_compliant: bool = False
    erasure_requests_processed: int = 0
    last_updated: str | None = None
