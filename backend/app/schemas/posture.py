"""Pydantic schemas for the security posture endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PostureCheckResult(BaseModel):
    rule_id: int
    rule_name: str
    category: str
    severity: str
    status: str  # pass | fail | open | investigating | resolved | false_positive | unknown
    title: str
    description: str
    detection_id: int | None = None
    context_data: dict[str, Any] = {}
    triggered_at: datetime | None = None


class RepoSummary(BaseModel):
    total: int
    passing: int
    warning: int
    failing: int


class RepoPosture(BaseModel):
    repo_name: str
    org: str
    visibility: str | None = None
    default_branch: str | None = None
    archived: bool = False
    fork: bool = False
    language: str | None = None
    pushed_at: datetime | None = None
    score: float
    checks: list[PostureCheckResult]
    detection_count: int = 0


class OrgPosture(BaseModel):
    org_login: str
    score: float
    two_factor_required: bool | None = None
    default_repo_permission: str | None = None
    members_can_fork_private_repos: bool | None = None
    members_can_create_public_repos: bool | None = None
    ip_allow_list_enabled: bool | None = None
    checks: list[PostureCheckResult]
    repos: list[RepoPosture] | None = None
    repo_summary: RepoSummary | None = None
    detection_count: int = 0


class BreadcrumbItem(BaseModel):
    label: str
    href: str | None = None


class PostureResponse(BaseModel):
    level: str  # enterprise | org | repo
    score: float
    orgs: list[OrgPosture] | None = None
    org: OrgPosture | None = None
    repo: RepoPosture | None = None
    breadcrumb: list[BreadcrumbItem]
    last_sync_at: datetime | None = None
    page: int = 1
    page_size: int = 25
    total: int = 0
    has_next: bool = False
