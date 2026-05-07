"""Pydantic response schemas for the health signals API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# PAT Health (US-1C / US-1D)
# ---------------------------------------------------------------------------


class PATHealthSummary(BaseModel):
    """Aggregate counts for the PAT health stat pills."""

    no_expiry_count: int = 0
    expired_count: int = 0
    stale_90d_count: int = 0


class PATTokenSignal(BaseModel):
    """Individual PAT with age/expiry signal metadata."""

    github_login: str | None = None
    token_name: str | None = None
    token_id: str | None = None
    token_type: str | None = None
    created_at: str | None = None
    age_days: int | None = None
    signal_type: str | None = None


class DormantToken(BaseModel):
    """PAT created >30d ago with no usage events."""

    github_login: str | None = None
    token_id: str | None = None
    token_name: str | None = None
    token_type: str | None = None
    created_at: str | None = None
    age_days: int | None = None
    last_used_at: str | None = None


class PATHealthResponse(BaseModel):
    """Combined PAT health response envelope."""

    summary: dict[str, int] = Field(default_factory=dict)
    tokens: list[dict[str, Any]] = Field(default_factory=list)
    dormant: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Bypass Offenders (US-2C)
# ---------------------------------------------------------------------------


class BypassOffender(BaseModel):
    """Actor ranked by bypass count."""

    actor: str
    total_bypasses: int
    push_protection_bypasses: int = 0
    branch_protection_overrides: int = 0
    first_bypass_at: str | None = None
    last_bypass_at: str | None = None
    active_days: int = 0


class BypassOffendersResponse(BaseModel):
    """Bypass offenders response envelope."""

    offenders: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Repo Health (US-3A / US-3B / US-3C)
# ---------------------------------------------------------------------------


class StaleRepository(BaseModel):
    """Repository with no event activity beyond threshold."""

    org: str
    repo: str
    last_event_at: str | None = None
    days_since_activity: int | None = None


class ArchivedRepository(BaseModel):
    """Archived repo that was never deleted."""

    org: str
    repo: str
    archived_at: str | None = None
    archived_by: str | None = None
    days_since_archived: int | None = None


class AbandonedFork(BaseModel):
    """Fork with no push within 30 days of creation."""

    actor: str | None = None
    org: str
    repo: str
    forked_at: str | None = None
    days_since_fork: int | None = None


class RepoHealthResponse(BaseModel):
    """Combined repo health response envelope."""

    stale: list[dict[str, Any]] = Field(default_factory=list)
    archived: list[dict[str, Any]] = Field(default_factory=list)
    abandoned_forks: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# External Collaborators (US-5B / US-5C)
# ---------------------------------------------------------------------------


class ExternalCollaboratorSummary(BaseModel):
    """Summary counts for the external collaborator stat pills."""

    total_active: int = 0
    org_level_count: int = 0
    elevated_count: int = 0
    dormant_count: int = 0


class ExternalCollaborator(BaseModel):
    """Active outside collaborator with optional IdP enrichment."""

    github_login: str
    org: str
    repo: str | None = None
    role: str
    granted_at: str | None = None
    granted_by: str | None = None
    last_event_at: str | None = None
    days_since_last_event: int | None = None
    idp_email: str | None = None
    idp_employment_status: str | None = None


class ExternalCollaboratorsResponse(BaseModel):
    """External collaborators response envelope."""

    summary: dict[str, int] = Field(default_factory=dict)
    collaborators: list[dict[str, Any]] = Field(default_factory=list)


class DormantCollaborator(BaseModel):
    """Collaborator with no activity beyond dormancy threshold."""

    github_login: str
    org: str
    repo: str | None = None
    role: str
    granted_at: str | None = None
    last_event_at: str | None = None
    days_inactive: int | None = None


class DormantCollaboratorsResponse(BaseModel):
    """Dormant collaborators response envelope."""

    dormant: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Aggregate Health Summary
# ---------------------------------------------------------------------------


class HealthSummaryResponse(BaseModel):
    """Overview strip aggregate counts across all signal types."""

    stale_repos: int = 0
    pat_no_expiry: int = 0
    pat_stale: int = 0
    bypass_offenders: int = 0
    ext_collab_total: int = 0
    ext_collab_elevated: int = 0


# ---------------------------------------------------------------------------
# GHAS Individual Alert Schemas (Epic 5)
# ---------------------------------------------------------------------------


class SecretScanningAlertItem(BaseModel):
    """Individual secret scanning alert record."""

    id: int
    org_slug: str
    alert_number: int
    repo_full_name: str
    secret_type: str
    secret_type_display: str | None = None
    file_path: str | None = None
    commit_sha: str | None = None
    state: str
    resolution: str | None = None
    push_protection_bypassed: bool = False
    push_protection_bypassed_by: str | None = None
    created_at: str
    resolved_at: str | None = None


class SecretScanningAlertsResponse(BaseModel):
    """Paginated list of secret scanning alerts."""

    alerts: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class CodeScanningAlertItem(BaseModel):
    """Individual code scanning alert record."""

    id: int
    org_slug: str
    alert_number: int
    repo_full_name: str
    rule_id: str
    rule_description: str | None = None
    severity: str | None = None
    security_severity: str | None = None
    cwe_ids: list[str] | None = None
    tool_name: str | None = None
    file_path: str | None = None
    start_line: int | None = None
    state: str
    dismissed_by: str | None = None
    dismissed_reason: str | None = None
    dismissed_at: str | None = None
    created_at: str
    fixed_at: str | None = None


class CodeScanningAlertsResponse(BaseModel):
    """Paginated list of code scanning alerts."""

    alerts: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class DependabotAlertItem(BaseModel):
    """Individual Dependabot alert record."""

    id: int
    org_slug: str
    alert_number: int
    repo_full_name: str
    package_name: str
    package_ecosystem: str | None = None
    severity: str | None = None
    cvss_score: float | None = None
    cve_id: str | None = None
    cwe_ids: list[str] | None = None
    vulnerable_version_range: str | None = None
    patched_version: str | None = None
    state: str
    dismissed_by: str | None = None
    dismissed_reason: str | None = None
    created_at: str
    fixed_at: str | None = None
    auto_dismissed_at: str | None = None


class DependabotAlertsResponse(BaseModel):
    """Paginated list of Dependabot alerts."""

    alerts: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class AlertSeverityBreakdown(BaseModel):
    """Severity breakdown for a GHAS alert type."""

    open: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    total: int = 0


class SecretScanningSummary(BaseModel):
    """Secret scanning summary for the unified dashboard."""

    open: int = 0
    resolved: int = 0
    total: int = 0
    bypassed_open: int = 0


class DetectionsSummary(BaseModel):
    """Active OctoWatch detections summary."""

    active: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class DependabotSummary(AlertSeverityBreakdown):
    """Dependabot summary with aging signal."""

    critical_aging_gt_90d: int = 0


class TrendDay(BaseModel):
    """Single day in the 30-day trend."""

    day: str
    secret_scanning: int = 0
    code_scanning: int = 0
    dependabot: int = 0


class UnifiedSecurityResponse(BaseModel):
    """Combined security dashboard response (Issue #72)."""

    secret_scanning: SecretScanningSummary = Field(default_factory=SecretScanningSummary)
    code_scanning: AlertSeverityBreakdown = Field(default_factory=AlertSeverityBreakdown)
    dependabot: DependabotSummary = Field(default_factory=DependabotSummary)
    detections: DetectionsSummary = Field(default_factory=DetectionsSummary)
    trend_30d: list[TrendDay] = Field(default_factory=list)


class AbuseSignal(BaseModel):
    """API abuse detection signal."""

    signal_type: str
    severity: str
    actor: str
    event_count: int = 0
    time_window_start: str | None = None
    time_window_end: str | None = None
    details: str = ""
    recommended_action: str = ""


class AbuseSignalsResponse(BaseModel):
    """API abuse signals response."""

    signals: list[dict[str, Any]] = Field(default_factory=list)


class DormantUser(BaseModel):
    """Dormant user with cost estimate."""

    login: str
    last_activity_date: str | None = None
    days_inactive: int = 0
    seat_type: str = "github"
    estimated_monthly_cost: float = 21.0
    recommended_action: str = ""


class DormantUsersResponse(BaseModel):
    """Dormant users response."""

    users: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class PlatformSecurityOrg(BaseModel):
    """Per-org platform security status."""

    org: str
    sso_configured: bool = False
    two_fa_required: bool = False
    audit_log_streaming: bool = False
    ip_allowlist_configured: bool = False
    branch_protection_default: bool = False
    compliance_score: float = 0.0
    recommendations: list[str] = Field(default_factory=list)


class PlatformSecurityResponse(BaseModel):
    """Platform security response."""

    orgs: list[dict[str, Any]] = Field(default_factory=list)
    overall_compliance_score: float = 0.0


class MaintenanceSignalsResponse(BaseModel):
    """Comprehensive maintenance signals."""

    stale_repos: list[dict[str, Any]] = Field(default_factory=list)
    empty_repos: list[dict[str, Any]] = Field(default_factory=list)
    archived_candidates: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


class HealthScoreResponse(BaseModel):
    """Overall health score."""

    score: int = 100
    grade: str = "A"
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    total_signals: int = 0
    orgs_monitored: int = 0
