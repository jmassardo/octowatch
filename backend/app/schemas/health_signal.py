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
