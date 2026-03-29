"""SQLAlchemy ORM models for GitHub Enterprise Sync."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
