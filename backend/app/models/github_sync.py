"""SQLAlchemy ORM models for GitHub Enterprise Sync."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base

# ─── GitHub App Configuration ─────────────────────────────────────────────────


class GitHubAppConfig(Base):
    """Per-org GitHub App installation mapping.

    Private keys are NEVER stored here — only the app_id and installation_id
    that are needed to request installation access tokens.
    """

    __tablename__ = "github_app_configs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )

    app_id: Mapped[int] = mapped_column(Integer, nullable=False)
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # enterprise_slug is set when this installation covers an entire enterprise;
    # NULL means org-level installation only.
    enterprise_slug: Mapped[str | None] = mapped_column(Text)
    org_login: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        UniqueConstraint("app_id", "installation_id", name="uq_github_app_configs_app_install"),
        Index("idx_github_app_configs_enterprise", "enterprise_slug"),
        Index("idx_github_app_configs_org", "org_login"),
    )


# ─── Sync Run Lifecycle ───────────────────────────────────────────────────────


class EnterpriseSyncRun(Base):
    """Top-level record for each full or partial enterprise sync run."""

    __tablename__ = "enterprise_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    # "pending" | "running" | "completed" | "failed" | "cancelled"
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    # "manual" | "scheduled"
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(Text)  # github_login of triggering user
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'full'"))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    # {"orgs": 3, "members": 412, "repositories": 1804, ...}
    entity_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # null | "pending" | "running" | "completed" | "failed"
    post_processing_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_enterprise_sync_runs_status", "status"),
        Index("idx_enterprise_sync_runs_created_at", "created_at"),
    )


class EnterpriseSyncEntityCursor(Base):
    """Resumable pagination state per (run, entity_type, org) triple.

    Written after every page so that a crashed worker can restart exactly
    where it left off.
    """

    __tablename__ = "enterprise_sync_entity_cursors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enterprise_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "orgs" | "enterprise_members" | "org_members" | "repositories" |
    # "teams" | "team_members" | "branch_protections" | "installations"
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    org: Mapped[str | None] = mapped_column(Text)  # NULL for enterprise-level entities

    # Opaque GitHub GraphQL / REST cursor string; NULL means start from page 1
    last_cursor: Mapped[str | None] = mapped_column(Text)
    items_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # "in_progress" | "completed" | "failed"
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'in_progress'"))

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "entity_type",
            "org",
            name="uq_sync_cursors_run_entity_org",
        ),
        Index("idx_sync_cursors_run_id", "run_id"),
    )


# ─── Enterprise-Level Entities ────────────────────────────────────────────────


class EnterpriseOrg(Base):
    """Snapshot of each GitHub organisation inside the enterprise."""

    __tablename__ = "enterprise_orgs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    enterprise_slug: Mapped[str] = mapped_column(Text, nullable=False)
    org_login: Mapped[str] = mapped_column(Text, nullable=False)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "public" | "private" | "secret"
    visibility: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str | None] = mapped_column(Text)  # "free" | "team" | "enterprise"
    member_count: Mapped[int | None] = mapped_column(Integer)

    # Security settings (enriched via REST API after org sync)
    two_factor_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # "read" | "write" | "admin" | "none"
    default_repo_permission: Mapped[str | None] = mapped_column(Text)
    members_can_fork_private_repos: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    members_can_create_public_repos: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ip_allow_list_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ip_allow_list_for_installed_apps_enabled: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("enterprise_slug", "org_login", name="uq_enterprise_orgs_slug_login"),
        Index("idx_enterprise_orgs_slug", "enterprise_slug"),
        Index("idx_enterprise_orgs_org_id", "org_id"),
    )


class EnterpriseMember(Base):
    """Enterprise-level membership snapshot (across all orgs)."""

    __tablename__ = "enterprise_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    enterprise_slug: Mapped[str] = mapped_column(Text, nullable=False)
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "owner" | "member" | "billing_manager"
    role: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "enterprise_slug",
            "github_login",
            name="uq_enterprise_members_slug_login",
        ),
        Index("idx_enterprise_members_slug", "enterprise_slug"),
        Index("idx_enterprise_members_github_id", "github_id"),
    )


# ─── Org-Level Entities ───────────────────────────────────────────────────────


class OrgMember(Base):
    """Org-level membership snapshot."""

    __tablename__ = "org_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "owner" | "member"
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # True = MFA enabled, False = MFA disabled, None = status unknown
    mfa_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "github_login", name="uq_org_members_org_login"),
        Index("idx_org_members_org", "org"),
        Index("idx_org_members_github_id", "github_id"),
    )


class OrgTeam(Base):
    """Org team snapshot including parent/child relationships."""

    __tablename__ = "org_teams"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    team_slug: Mapped[str] = mapped_column(Text, nullable=False)
    team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # "secret" | "closed"
    privacy: Mapped[str | None] = mapped_column(Text)
    # NULL if this is a top-level team
    parent_team_slug: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "team_slug", name="uq_org_teams_org_slug"),
        Index("idx_org_teams_org", "org"),
        Index("idx_org_teams_team_id", "team_id"),
    )


class OrgTeamMember(Base):
    """Team member snapshot."""

    __tablename__ = "org_team_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    team_slug: Mapped[str] = mapped_column(Text, nullable=False)
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    github_id: Mapped[int | None] = mapped_column(BigInteger)
    # "member" | "maintainer"
    role: Mapped[str] = mapped_column(Text, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "org",
            "team_slug",
            "github_login",
            name="uq_org_team_members_org_team_login",
        ),
        Index("idx_org_team_members_org_team", "org", "team_slug"),
        Index("idx_org_team_members_login", "github_login"),
    )


# ─── Repository Entities ──────────────────────────────────────────────────────


class Repository(Base):
    """Repository snapshot."""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "public" | "private" | "internal"
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fork: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "repo_name", name="uq_repositories_org_name"),
        Index("idx_repositories_org", "org"),
        Index("idx_repositories_repo_id", "repo_id"),
        Index("idx_repositories_visibility", "visibility"),
    )


class RepoBranchProtection(Base):
    """Branch protection rule snapshot per repo/branch."""

    __tablename__ = "repo_branch_protections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str] = mapped_column(Text, nullable=False)
    # Minimum number of required approving reviews (0 = not set)
    required_reviews: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # {"contexts": ["ci/tests"], "strict": true}
    required_status_checks: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    enforce_admins: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "org",
            "repo_name",
            "branch",
            name="uq_repo_branch_protections_org_repo_branch",
        ),
        Index("idx_repo_branch_protections_org_repo", "org", "repo_name"),
    )


# ─── GitHub App Installations ─────────────────────────────────────────────────


class GitHubAppInstallation(Base):
    """Snapshot of GitHub App installations visible to the configured App ID."""

    __tablename__ = "github_app_installations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    app_id: Mapped[int] = mapped_column(Integer, nullable=False)
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "Organization" | "User"
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_login: Mapped[str] = mapped_column(Text, nullable=False)
    # {"members": "read", "administration": "read", "secret_scanning_alerts": "read", ...}
    permissions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "app_id",
            "installation_id",
            name="uq_github_app_installations_app_install",
        ),
        Index("idx_github_app_installations_app_id", "app_id"),
        Index("idx_github_app_installations_target", "target_type", "target_login"),
    )


# ─── Sync Log Entries ─────────────────────────────────────────────────────────


class SyncLogEntry(Base):
    """Lightweight log entries written during an enterprise sync run.

    Each entry records a key event (task dispatched, entity sync started,
    page fetched, entity completed, pipeline step, error, etc.) and is
    immediately committed in its own transaction so the frontend can poll
    for incremental updates while the sync is still running.

    Entries are ordered within a run by their ``seq`` (sequence) number,
    which is monotonically increasing per run.
    """

    __tablename__ = "enterprise_sync_log_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("enterprise_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'info'"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    org: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (Index("idx_sync_log_entries_run_id_seq", "run_id", "seq"),)


class OrgOutsideCollaborator(Base):
    """Outside collaborators for an org, synced from the GitHub REST API.

    Endpoint: ``GET /orgs/{org}/outside_collaborators``
    """

    __tablename__ = "org_outside_collaborators"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    enterprise_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    org: Mapped[str] = mapped_column(String(100), nullable=False)
    login: Mapped[str] = mapped_column(String(100), nullable=False)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "enterprise_slug", "org", "login", name="uq_outside_collab_slug_org_login"
        ),
        Index("idx_outside_collab_org", "org"),
    )


class OrgSecretScanningAlertSummary(Base):
    """Aggregated secret-scanning alert counts for an org.

    Instead of storing every alert individually, we store summary counts
    per org per sync run so the health dashboard can quickly show a posture
    overview.

    Endpoint: ``GET /orgs/{org}/secret-scanning/alerts``
    """

    __tablename__ = "org_secret_scanning_alert_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    enterprise_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    org: Mapped[str] = mapped_column(String(100), nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    resolved_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("enterprise_slug", "org", name="uq_secret_scanning_summary_slug_org"),
        Index("idx_secret_scanning_summary_org", "org"),
    )


class OrgDependabotAlertSummary(Base):
    """Aggregated Dependabot alert counts for an org.

    Mirrors the summary approach used for secret-scanning alerts.

    Endpoint: ``GET /orgs/{org}/dependabot/alerts``
    """

    __tablename__ = "org_dependabot_alert_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    enterprise_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    org: Mapped[str] = mapped_column(String(100), nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    fixed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    dismissed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    high_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    low_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("enterprise_slug", "org", name="uq_dependabot_summary_slug_org"),
        Index("idx_dependabot_summary_org", "org"),
    )


class EnterpriseLicenseConsumption(Base):
    """GHEC license consumption data from the enterprise billing API.

    Endpoint: ``GET /enterprises/{enterprise}/consumed-licenses``

    Stores the headline seat counts (purchased vs consumed) plus a JSONB
    snapshot of up to 500 individual user seat assignments for drill-down.
    """

    __tablename__ = "enterprise_license_consumption"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    enterprise_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    total_seats_purchased: Mapped[int] = mapped_column(Integer, nullable=False)
    total_seats_consumed: Mapped[int] = mapped_column(Integer, nullable=False)
    seats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (UniqueConstraint("enterprise_slug", name="uq_license_consumption_slug"),)


class OrgCodeScanningAlertSummary(Base):
    """Aggregated code-scanning alert counts for an org.

    Mirrors the summary approach used for secret-scanning and Dependabot
    alerts.  Counts are computed by paginating all code-scanning alerts
    across repos in the org and bucketing by state and severity.

    Endpoint: ``GET /orgs/{org}/code-scanning/alerts``
    """

    __tablename__ = "org_code_scanning_alert_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    enterprise_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    org: Mapped[str] = mapped_column(String(100), nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    fixed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    dismissed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    note_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("enterprise_slug", "org", name="uq_code_scanning_summary_slug_org"),
        Index("idx_code_scanning_summary_org", "org"),
    )


class OrgActionsWorkflowSummary(Base):
    """Aggregated GitHub Actions workflow and run data for an org.

    Stores summary counts of workflow definitions and recent workflow
    runs for the OpsHealth dashboard pane.

    Endpoints:
      - ``GET /repos/{owner}/{repo}/actions/workflows`` (definitions)
      - ``GET /repos/{owner}/{repo}/actions/runs`` (recent runs)
    """

    __tablename__ = "org_actions_workflow_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    enterprise_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    org: Mapped[str] = mapped_column(String(100), nullable=False)
    total_workflows: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    active_workflows: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    successful_runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failed_runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cancelled_runs: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("enterprise_slug", "org", name="uq_actions_workflow_summary_slug_org"),
        Index("idx_actions_workflow_summary_org", "org"),
    )


# ─── GHAS Individual Alert Models ────────────────────────────────────────────


class SecretScanningAlert(Base):
    """Individual secret scanning alert record.

    Stored alongside the existing org-level summary to enable per-alert
    queries for accurate MTTR, resolution rate, and actor-timeline
    correlation.

    Source: ``GET /orgs/{org}/secret-scanning/alerts``
    """

    __tablename__ = "secret_scanning_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    alert_number: Mapped[int] = mapped_column(Integer, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(400), nullable=False)
    secret_type: Mapped[str] = mapped_column(String(200), nullable=False)
    secret_type_display: Mapped[str | None] = mapped_column(String(400), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(50), nullable=True)
    push_protection_bypassed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    push_protection_bypassed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "org_slug", "repo_full_name", "alert_number", name="uq_secret_scanning_alert"
        ),
        Index("idx_secret_scanning_alert_org_state", "org_slug", "state"),
        Index("idx_secret_scanning_alert_repo", "repo_full_name"),
    )


class CodeScanningAlert(Base):
    """Individual code scanning alert record.

    Stored alongside the existing org-level summary to enable per-alert
    queries for accurate MTTR, dismissal correlation, and severity
    breakdown.

    Source: ``GET /orgs/{org}/code-scanning/alerts``
    """

    __tablename__ = "code_scanning_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    alert_number: Mapped[int] = mapped_column(Integer, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(400), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    security_severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cwe_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    dismissed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dismissed_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "org_slug", "repo_full_name", "alert_number", name="uq_code_scanning_alert"
        ),
        Index("idx_code_scanning_alert_org_state", "org_slug", "state"),
        Index("idx_code_scanning_alert_repo", "repo_full_name"),
    )


class DependabotAlert(Base):
    """Individual Dependabot alert record.

    Stored alongside the existing org-level summary to enable per-alert
    queries for accurate vulnerability aging, CVSS breakdown, and
    90-day critical aging signal generation.

    Source: ``GET /orgs/{org}/dependabot/alerts``
    """

    __tablename__ = "dependabot_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_slug: Mapped[str] = mapped_column(String(200), nullable=False)
    alert_number: Mapped[int] = mapped_column(Integer, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(400), nullable=False)
    package_name: Mapped[str] = mapped_column(String(400), nullable=False)
    package_ecosystem: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cve_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cwe_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    vulnerable_version_range: Mapped[str | None] = mapped_column(String(200), nullable=True)
    patched_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    dismissed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dismissed_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org_slug", "repo_full_name", "alert_number", name="uq_dependabot_alert"),
        Index("idx_dependabot_alert_org_state", "org_slug", "state"),
        Index("idx_dependabot_alert_repo", "repo_full_name"),
    )


# ─── Team Repository Access ───────────────────────────────────────────────────


class OrgTeamRepo(Base):
    """Team-to-repo access mapping with permission level.

    Endpoint: ``GET /orgs/{org}/teams/{slug}/repos``
    """

    __tablename__ = "org_team_repos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    team_slug: Mapped[str] = mapped_column(Text, nullable=False)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    repo_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "pull" | "push" | "admin" | "maintain" | "triage"
    permission: Mapped[str] = mapped_column(Text, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "team_slug", "repo_name", name="uq_org_team_repos_org_team_repo"),
        Index("idx_org_team_repos_org_team", "org", "team_slug"),
        Index("idx_org_team_repos_repo", "org", "repo_name"),
    )


# ─── Repo Collaborators (Direct Access) ──────────────────────────────────────


class RepoCollaborator(Base):
    """Direct (non-team-inherited) repo collaborator.

    Endpoint: ``GET /repos/{owner}/{repo}/collaborators?affiliation=direct``
    """

    __tablename__ = "repo_collaborators"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    github_id: Mapped[int | None] = mapped_column(BigInteger)
    # "admin" | "maintain" | "write" | "triage" | "read"
    permission: Mapped[str] = mapped_column(Text, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "org", "repo_name", "github_login", name="uq_repo_collaborators_org_repo_login"
        ),
        Index("idx_repo_collaborators_org_repo", "org", "repo_name"),
        Index("idx_repo_collaborators_login", "github_login"),
    )


# ─── SAML/SSO Credential Authorizations ──────────────────────────────────────


class OrgCredentialAuthorization(Base):
    """SAML SSO credential authorizations for an org.

    Endpoint: ``GET /orgs/{org}/credential-authorizations``
    """

    __tablename__ = "org_credential_authorizations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    credential_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # "personal access token" | "SSH key" | "OAuth app" | etc.
    credential_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Token fingerprint or key title
    token_last_eight: Mapped[str | None] = mapped_column(String(8))
    credential_authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    credential_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "credential_id", name="uq_org_credential_auth_org_cred"),
        Index("idx_org_credential_auth_org", "org"),
        Index("idx_org_credential_auth_login", "github_login"),
    )


# ─── Webhooks ─────────────────────────────────────────────────────────────────


class OrgWebhook(Base):
    """Org-level webhook configuration.

    Endpoint: ``GET /orgs/{org}/hooks``
    """

    __tablename__ = "org_webhooks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    hook_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # The delivery URL (insecure_ssl flag, content_type, etc.)
    config_url: Mapped[str | None] = mapped_column(Text)
    config_content_type: Mapped[str | None] = mapped_column(Text)
    config_insecure_ssl: Mapped[str | None] = mapped_column(Text)
    events: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "hook_id", name="uq_org_webhooks_org_hook"),
        Index("idx_org_webhooks_org", "org"),
    )


class RepoWebhook(Base):
    """Repo-level webhook configuration.

    Endpoint: ``GET /repos/{owner}/{repo}/hooks``
    """

    __tablename__ = "repo_webhooks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    hook_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    config_url: Mapped[str | None] = mapped_column(Text)
    config_content_type: Mapped[str | None] = mapped_column(Text)
    config_insecure_ssl: Mapped[str | None] = mapped_column(Text)
    events: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "repo_name", "hook_id", name="uq_repo_webhooks_org_repo_hook"),
        Index("idx_repo_webhooks_org_repo", "org", "repo_name"),
    )


# ─── Actions Permissions ──────────────────────────────────────────────────────


class OrgActionsPermissions(Base):
    """Org-level GitHub Actions permissions settings.

    Endpoint: ``GET /orgs/{org}/actions/permissions``
    """

    __tablename__ = "org_actions_permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    enabled_repositories: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # "all" | "none" | "selected"
    allowed_actions: Mapped[str | None] = mapped_column(Text)  # "all" | "local_only" | "selected"
    github_owned_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    verified_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    patterns_allowed: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", name="uq_org_actions_permissions_org"),
        Index("idx_org_actions_permissions_org", "org"),
    )


# ─── Self-Hosted Runners ─────────────────────────────────────────────────────


class OrgSelfHostedRunner(Base):
    """Self-hosted runner registered at the org level.

    Endpoint: ``GET /orgs/{org}/actions/runners``
    """

    __tablename__ = "org_self_hosted_runners"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    runner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    os: Mapped[str] = mapped_column(Text, nullable=False)
    # "online" | "offline"
    status: Mapped[str] = mapped_column(Text, nullable=False)
    busy: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    labels: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    runner_group_id: Mapped[int | None] = mapped_column(BigInteger)
    runner_group_name: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "runner_id", name="uq_org_self_hosted_runners_org_runner"),
        Index("idx_org_self_hosted_runners_org", "org"),
    )


# ─── Deploy Keys ─────────────────────────────────────────────────────────────


class RepoDeployKey(Base):
    """Deploy key (SSH key) on a repository.

    Endpoint: ``GET /repos/{owner}/{repo}/keys``
    """

    __tablename__ = "repo_deploy_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    org: Mapped[str] = mapped_column(Text, nullable=False)
    repo_name: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    key_added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("org", "repo_name", "key_id", name="uq_repo_deploy_keys_org_repo_key"),
        Index("idx_repo_deploy_keys_org_repo", "org", "repo_name"),
    )
