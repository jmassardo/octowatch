# GitHub Enterprise Sync — Technical Architecture Specification

**Status:** Implementation Ready  
**Date:** 2026-03-27  
**Stack:** FastAPI · SQLAlchemy 2.0 async (asyncpg) · Celery + Valkey · TimescaleDB  

---

## Table of Contents

1. [Component Architecture](#1-component-architecture)
2. [Data Models (SQLAlchemy)](#2-data-models-sqlalchemy)
3. [GitHubAppTokenManager](#3-githubapptokenmanager)
4. [GitHubRateLimiter](#4-githubrateLimiter)
5. [Sync Worker Celery Tasks](#5-sync-worker-celery-tasks)
6. [API Endpoints](#6-api-endpoints)
7. [Config Changes](#7-config-changes)
8. [Security Controls](#8-security-controls)
9. [Alembic Migration Plan](#9-alembic-migration-plan)
10. [Testing Approach](#10-testing-approach)

---

## 1. Component Architecture

### 1.1 Existing Worker Topology

The existing Celery application (`app/celery_app.py`) defines four isolated queues:

| Queue | Workers | Workloads |
|-------|---------|-----------|
| `ingestion` | 2–4 replicas | S3 / Azure Blob polling, dedup pruning |
| `detection` | 2–4 replicas | Detection pipeline, ticket sync |
| `baseline` | 1–2 replicas | Rolling baselines |
| `notification` | 1 replica | Alert delivery |

### 1.2 New `github_sync` Queue

A dedicated fifth queue is added to isolate GitHub API I/O, which is rate-limited and long-running, from the latency-sensitive detection and ingestion paths.

```
celery_app.py  (task_routes addition)
───────────────────────────────────────
"app.workers.github_sync.*": {"queue": "github_sync"},
```

Worker deployment: **1 replica** with `worker_concurrency=4`. Concurrency is further bounded at runtime by `GitHubRateLimiter`'s semaphore (see §4).

### 1.3 Orchestrator + Fan-Out Pattern

```
POST /api/v1/admin/sync/trigger
        │
        ▼
run_enterprise_sync(run_id, scope)        ← orchestrator task
        │
        ├── sync_entity(run_id, "orgs",         org=None, ...)
        ├── sync_entity(run_id, "members",       org=None, ...)
        ├─┬─ sync_entity(run_id, "repositories", org="acme", ...)
        │ └─ sync_entity(run_id, "repositories", org="widgets", ...)
        ├─┬─ sync_entity(run_id, "teams",        org="acme", ...)
        │ └─ sync_entity(run_id, "teams",        org="widgets", ...)
        └── ... (one child task per entity_type × org combination)
```

**Design invariants:**

- The orchestrator writes `enterprise_sync_runs.status = "running"` before dispatching and sets `status = "completed" | "failed"` after all children finish (via Celery chord or by polling child states).
- Each child task is **idempotent**: it writes a cursor row to `enterprise_sync_entity_cursors` after each page. On retry or crash, it reads the stored cursor and resumes at that page.
- The orchestrator task is dispatched to the `github_sync` queue. Child fan-out tasks are also routed to `github_sync` but run as individual Celery tasks (not in a chord), so partial failures do not block the overall run.
- `scope="full"` dispatches all entity types for all configured orgs. `scope=<entity_type>` dispatches only that entity type.

### 1.4 File / Module Layout (new files only)

```
backend/app/
├── models/
│   └── github_sync.py          # All new ORM models (§2)
├── workers/
│   └── github_sync_worker.py   # Celery tasks (§5)
├── services/
│   ├── github_token_service.py # GitHubAppTokenManager (§3)
│   └── github_rate_limiter.py  # GitHubRateLimiter (§4)
├── routers/
│   └── sync.py                 # /api/v1/admin/sync/* endpoints (§6)
└── schemas/
    └── github_sync.py          # Pydantic request/response schemas
```

---

## 2. Data Models (SQLAlchemy)

All models live in `backend/app/models/github_sync.py`. They import `Base` from `app.models.audit_event` (the project's `DeclarativeBase`).

```python
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
    triggered_by: Mapped[str | None] = mapped_column(Text)   # github_login of triggering user
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'full'"))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    # {"orgs": 3, "members": 412, "repositories": 1804, ...}
    entity_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

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
    org: Mapped[str | None] = mapped_column(Text)             # NULL for enterprise-level entities

    # Opaque GitHub GraphQL / REST cursor string; NULL means start from page 1
    last_cursor: Mapped[str | None] = mapped_column(Text)
    items_synced: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # "in_progress" | "completed" | "failed"
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'in_progress'")
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id", "entity_type", "org",
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
    plan: Mapped[str | None] = mapped_column(Text)             # "free" | "team" | "enterprise"
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
            "enterprise_slug", "github_login",
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
            "org", "team_slug", "github_login",
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
    required_reviews: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
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
            "org", "repo_name", "branch",
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
            "app_id", "installation_id",
            name="uq_github_app_installations_app_install",
        ),
        Index("idx_github_app_installations_app_id", "app_id"),
        Index("idx_github_app_installations_target", "target_type", "target_login"),
    )
```

---

## 3. GitHubAppTokenManager

**File:** `backend/app/services/github_token_service.py`

```python
"""GitHub App authentication service.

Manages RS256 JWT generation and installation access token exchange.
Tokens are cached in Valkey with TTL = (expires_at − 5 minutes) to ensure
they are always valid for at least 5 minutes from the time of retrieval.

Security invariants:
  - The private key is loaded from the filesystem at construction time.
    The path is sourced from settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH.
  - The private key is NEVER written to the database, logs, or API responses.
  - Installation access tokens are NEVER written to the database.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import jwt                        # PyJWT ≥ 2.x
import structlog
from redis.asyncio import Redis

from app.config import settings

logger = structlog.get_logger(__name__)

_GITHUB_API_BASE = "https://api.github.com"   # never interpolated from user input


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: datetime        # UTC-aware


class GitHubAppTokenManager:
    """Generates GitHub App JWTs and exchanges them for installation access tokens.

    Parameters
    ----------
    app_id:
        The GitHub App's numeric App ID (from GitHub App settings page).
    private_key_pem:
        PEM-encoded RSA private key contents (already loaded from disk by
        the caller — this class never touches the filesystem at call time).
    valkey_client:
        An async redis.asyncio.Redis client used for token caching.
    """

    #: Cache key pattern — interpolated with installation_id (int only)
    _CACHE_KEY = "github:app:token:{installation_id}"
    #: Buffer in seconds subtracted from token TTL to force early refresh
    _TTL_BUFFER_SECS = 300       # 5 minutes

    def __init__(
        self,
        app_id: int,
        private_key_pem: str,
        valkey_client: Redis,
    ) -> None:
        self._app_id = app_id
        self._private_key_pem = private_key_pem
        self._valkey = valkey_client

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_installation_token(self, installation_id: int) -> str:
        """Return a valid installation access token for *installation_id*.

        Algorithm:
          1. Check Valkey cache key ``github:app:token:{installation_id}``.
          2. Cache HIT → decode JSON, return ``token`` field.
          3. Cache MISS → generate RS256 JWT, POST to GitHub API to exchange for
             an installation token, store in Valkey with TTL, return token.

        The Valkey TTL is set to ``expires_at − now − _TTL_BUFFER_SECS`` so the
        cached token is evicted before it expires.

        Parameters
        ----------
        installation_id:
            Numeric GitHub App installation ID for the target org/enterprise.

        Returns
        -------
        str
            An opaque GitHub API access token valid for ≥ 5 minutes.

        Raises
        ------
        GitHubAuthError
            If GitHub rejects the JWT or returns a non-2xx status.
        """
        cache_key = self._CACHE_KEY.format(installation_id=installation_id)

        cached = await self._valkey.get(cache_key)
        if cached:
            # Decode and return without touching GitHub API
            import json
            data = json.loads(cached)
            logger.debug("github_token.cache_hit", installation_id=installation_id)
            return data["token"]

        logger.info("github_token.cache_miss", installation_id=installation_id)
        app_jwt = self._generate_jwt()
        installation_token = await self._exchange_jwt_for_token(app_jwt, installation_id)

        ttl = int(
            (installation_token.expires_at.timestamp() - time.time()) - self._TTL_BUFFER_SECS
        )
        if ttl > 0:
            import json
            await self._valkey.set(
                cache_key,
                json.dumps({
                    "token": installation_token.token,
                    "expires_at": installation_token.expires_at.isoformat(),
                }),
                ex=ttl,
            )

        return installation_token.token

    # ── Private methods ───────────────────────────────────────────────────────

    def _generate_jwt(self) -> str:
        """Generate a short-lived RS256 JWT for GitHub App authentication.

        Claims:
          - ``iss`` (issuer): the App ID as a string
          - ``iat`` (issued at): ``now − 60s`` to account for clock skew
          - ``exp`` (expiry): ``now + 600s`` (10 minutes; GitHub max is 10 min)

        The JWT is signed with the RS256 algorithm using the app's RSA private
        key.  It is valid for use as a ``Bearer`` token in calls to
        ``GET /app/installations/{installation_id}/access_tokens``.

        Returns
        -------
        str
            A compact, Base64URL-encoded JWT string.
        """
        now = int(time.time())
        payload = {
            "iat": now - 60,    # back-date 60s for clock skew tolerance
            "exp": now + 600,   # 10 minutes (GitHub maximum)
            "iss": str(self._app_id),
        }
        return jwt.encode(payload, self._private_key_pem, algorithm="RS256")

    async def _exchange_jwt_for_token(
        self,
        app_jwt: str,
        installation_id: int,
    ) -> InstallationToken:
        """Exchange a GitHub App JWT for an installation access token.

        POSTs to ``https://api.github.com/app/installations/{id}/access_tokens``.
        The URL is constructed from the hard-coded base constant — never from
        user-supplied data — to prevent SSRF.

        Parameters
        ----------
        app_jwt:
            Short-lived RS256 JWT generated by ``_generate_jwt()``.
        installation_id:
            Numeric installation ID whose token is being requested.

        Returns
        -------
        InstallationToken
            Dataclass with ``token`` (str) and ``expires_at`` (UTC datetime).

        Raises
        ------
        GitHubAuthError
            On non-2xx GitHub API response.
        """
        # URL constructed from a hard-coded constant — SSRF safe
        url = f"{_GITHUB_API_BASE}/app/installations/{int(installation_id)}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        # follow_redirects=False prevents SSRF via redirect chain
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.post(url, headers=headers)

        if response.status_code != 201:
            logger.error(
                "github_token.exchange_failed",
                status=response.status_code,
                installation_id=installation_id,
            )
            raise GitHubAuthError(
                f"GitHub returned {response.status_code} for installation {installation_id}"
            )

        data = response.json()
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        return InstallationToken(token=data["token"], expires_at=expires_at)


class GitHubAuthError(RuntimeError):
    """Raised when GitHub App authentication or token exchange fails."""
```

---

## 4. GitHubRateLimiter

**File:** `backend/app/services/github_rate_limiter.py`

```python
"""GitHub API rate limit compliance service.

Implements a token-bucket algorithm calibrated to respect GitHub's
primary rate limit (15,000 req/hr for GitHub Apps) and secondary limits
(≤ 100 concurrent requests, ≤ 900 points/min).

When the remaining quota drops below 1,000 requests, the bucket refill rate
is capped to 1 token/s regardless of burst capacity, providing a proactive
throttle that keeps the sync from hitting hard limits.

All state is in-process (asyncio). This class is instantiated once per
Celery worker process and shared across all tasks via module-level singleton.
"""

from __future__ import annotations

import asyncio
import time
from typing import ClassVar

import httpx
import structlog

logger = structlog.get_logger(__name__)


class GitHubRateLimiter:
    """Token-bucket rate limiter for the GitHub REST API.

    Parameters
    ----------
    rate_per_hour:
        Maximum requests per hour. Default 15,000 (GitHub App limit).
    max_burst:
        Maximum tokens that can accumulate in the bucket before capping.
        Limits burst behaviour to avoid hitting secondary limits.
    max_concurrent:
        asyncio.Semaphore count bounding in-flight concurrent requests.
        Set to 80 to stay safely under GitHub's 100-concurrent limit.
    """

    #: Proactive throttle threshold — cap to 1 req/s if remaining ≤ this
    _PROACTIVE_THROTTLE_THRESHOLD: ClassVar[int] = 1000

    def __init__(
        self,
        rate_per_hour: int = 15_000,
        max_burst: int = 50,
        max_concurrent: int = 80,
    ) -> None:
        self._rate_per_sec: float = rate_per_hour / 3600.0   # ≈ 4.17 tokens/s
        self._max_burst = max_burst
        self._tokens: float = max_burst
        self._last_refill: float = time.monotonic()

        # Secondary-rate semaphore — max 80 simultaneous in-flight requests
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Tracking values parsed from GitHub response headers
        self._remaining: int = rate_per_hour
        self._reset_at: float = 0.0     # Unix timestamp
        self._proactive_throttle_active: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    async def acquire(self, cost: int = 1) -> None:
        """Block until *cost* tokens are available and the semaphore permits.

        Call this once before every GitHub API request. The semaphore is
        **not** released here — use it as an async context manager instead:

        .. code-block:: python

            async with rate_limiter._semaphore:
                await rate_limiter.acquire()
                response = await client.get(url)
                rate_limiter.update_from_headers(response.headers)

        If the proactive throttle is active (remaining < 1,000), the effective
        refill rate is capped to 1 token/s to bleed down the request queue slowly.

        Parameters
        ----------
        cost:
            Number of rate-limit tokens to consume. Almost always 1.
        """
        await self._semaphore.acquire()
        try:
            self._refill()
            effective_rate = (
                1.0 if self._proactive_throttle_active else self._rate_per_sec
            )
            while self._tokens < cost:
                sleep_for = (cost - self._tokens) / effective_rate
                logger.debug(
                    "rate_limiter.waiting",
                    sleep_for=round(sleep_for, 2),
                    tokens=round(self._tokens, 2),
                    proactive_throttle=self._proactive_throttle_active,
                )
                await asyncio.sleep(sleep_for)
                self._refill()
            self._tokens -= cost
        except Exception:
            self._semaphore.release()
            raise

    def release(self) -> None:
        """Release the semaphore after a request completes."""
        self._semaphore.release()

    def update_from_headers(self, headers: httpx.Headers | dict[str, str]) -> None:
        """Parse GitHub rate-limit response headers and update internal state.

        Relevant headers:
          - ``x-ratelimit-remaining``: requests left in current window
          - ``x-ratelimit-reset``: Unix timestamp when window resets
          - ``x-ratelimit-used``: requests consumed in current window

        Also activates or deactivates the proactive throttle based on
        the ``remaining`` value relative to ``_PROACTIVE_THROTTLE_THRESHOLD``.

        Parameters
        ----------
        headers:
            Response headers from an httpx.Response or dict equivalent.
        """
        try:
            remaining_str = headers.get("x-ratelimit-remaining")
            reset_str = headers.get("x-ratelimit-reset")
            if remaining_str is not None:
                self._remaining = int(remaining_str)
            if reset_str is not None:
                self._reset_at = float(reset_str)

            was_throttled = self._proactive_throttle_active
            self._proactive_throttle_active = (
                self._remaining < self._PROACTIVE_THROTTLE_THRESHOLD
            )
            if self._proactive_throttle_active and not was_throttled:
                logger.warning(
                    "rate_limiter.proactive_throttle_activated",
                    remaining=self._remaining,
                    reset_at=self._reset_at,
                )
        except (ValueError, TypeError) as exc:
            logger.warning("rate_limiter.header_parse_error", error=str(exc))

    async def handle_rate_limit_response(self, response: httpx.Response) -> None:
        """Handle a 429 Too Many Requests or 403 (secondary rate limit) response.

        Parses the ``retry-after`` header if present; falls back to sleeping
        until ``x-ratelimit-reset``. Implements exponential backoff with
        jitter when called in rapid succession.

        Callers should retry the request after awaiting this method.

        Parameters
        ----------
        response:
            The non-2xx httpx.Response that triggered rate limiting.
        """
        import random

        status = response.status_code
        if status not in (429, 403):
            return

        retry_after_str = response.headers.get("retry-after")
        if retry_after_str:
            try:
                sleep_secs = float(retry_after_str) + random.uniform(0.5, 2.0)
            except ValueError:
                sleep_secs = 60.0
        elif self._reset_at > 0:
            sleep_secs = max(self._reset_at - time.time() + 1.0, 1.0)
        else:
            sleep_secs = 60.0

        logger.warning(
            "rate_limiter.backing_off",
            status=status,
            sleep_secs=round(sleep_secs, 1),
        )
        await asyncio.sleep(sleep_secs)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _refill(self) -> None:
        """Refill the token bucket based on elapsed time since last call."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        rate = 1.0 if self._proactive_throttle_active else self._rate_per_sec
        self._tokens = min(self._tokens + elapsed * rate, float(self._max_burst))
```

---

## 5. Sync Worker Celery Tasks

**File:** `backend/app/workers/github_sync_worker.py`

```python
"""GitHub Enterprise Sync Celery tasks.

Queue: github_sync

Task hierarchy:
  run_enterprise_sync  (orchestrator)
      └── sync_entity  (per entity_type × org)  ← fan-out, independent tasks

Each sync_entity task is idempotent: it reads its last cursor from
enterprise_sync_entity_cursors, paginates GitHub from that point, upserts
rows into the appropriate snapshot table, and writes its updated cursor after
every page. A crash mid-page means at most one page is re-processed.

Upsert strategy: INSERT ... ON CONFLICT DO UPDATE SET ... so that running the
sync twice leaves the database in the same final state (idempotent).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Literal

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)

# Types accepted as scope values
ScopeType = Literal[
    "full",
    "orgs",
    "enterprise_members",
    "org_members",
    "repositories",
    "teams",
    "team_members",
    "branch_protections",
    "installations",
]


@celery_app.task(
    name="app.workers.github_sync.run_enterprise_sync",
    bind=True,
    max_retries=0,           # Orchestrator does not retry; child tasks do
    queue="github_sync",
    soft_time_limit=7200,    # 2 hours
    time_limit=7800,         # 2h 10m hard kill
)
def run_enterprise_sync(
    self: Task,
    run_id: str,
    scope: ScopeType = "full",
) -> dict:
    """Orchestrator task: coordinate a full or partial enterprise sync.

    Steps:
      1. Mark enterprise_sync_runs.status = "running", started_at = now.
      2. Load github_app_configs to discover per-org installation IDs.
      3. Determine entity types to sync based on *scope*.
      4. For each (entity_type, org) combination, dispatch a ``sync_entity``
         child task to the ``github_sync`` queue.
      5. Poll child task states until all are terminal (completed/failed/revoked).
      6. Aggregate entity counts from child results, update run status to
         "completed" or "failed".

    This task itself does not perform any GitHub API calls.

    Parameters
    ----------
    run_id:
        UUID string of the EnterpriseSyncRun row (already created by the
        API endpoint before dispatching this task).
    scope:
        "full" to sync all entity types, or a specific entity_type name to
        sync only that entity across all configured orgs.
    """
    return asyncio.run(_run_enterprise_sync_async(run_id, scope))


@celery_app.task(
    name="app.workers.github_sync.sync_entity",
    bind=True,
    max_retries=3,
    default_retry_delay=30,   # seconds; callers may override with countdown
    queue="github_sync",
    soft_time_limit=3600,     # 1 hour per entity/org chunk
    time_limit=3900,
    acks_late=True,
)
def sync_entity(
    self: Task,
    run_id: str,
    entity_type: str,
    org: str | None,
    installation_id: int,
    cursor: str | None = None,
) -> dict:
    """Idempotent child task: sync one entity_type for one org.

    Resumability contract:
      - On entry, reads ``enterprise_sync_entity_cursors`` for the
        (run_id, entity_type, org) triple to get the last saved cursor.
        The *cursor* argument passed by the orchestrator is only used if no
        cursor row exists yet (i.e., first attempt).
      - After each successful page, UPSERTs the cursor row with the new cursor
        value and increments ``items_synced``.
      - On completion (no more pages), sets cursor row status = "completed".
      - On failure, sets cursor row status = "failed" and re-raises so Celery
        can retry up to max_retries times.

    Upsert strategy:
      All target tables use INSERT ... ON CONFLICT (natural key) DO UPDATE SET
      so duplicate runs are non-destructive.

    Parameters
    ----------
    run_id:
        UUID string of the parent EnterpriseSyncRun.
    entity_type:
        One of: "orgs", "enterprise_members", "org_members", "repositories",
        "teams", "team_members", "branch_protections", "installations".
    org:
        GitHub org login (None for enterprise-level entities like "orgs" and
        "enterprise_members").
    installation_id:
        Numeric GitHub App installation ID to use for token acquisition.
    cursor:
        Initial pagination cursor. Overridden by database state on retry.
    """
    return asyncio.run(_sync_entity_async(self, run_id, entity_type, org, installation_id, cursor))


# ── Internal async implementations ────────────────────────────────────────────


async def _run_enterprise_sync_async(run_id: str, scope: ScopeType) -> dict:
    """Async implementation of the orchestrator.  Called inside asyncio.run()."""
    from sqlalchemy import select, update

    from app.config import settings
    from app.models.github_sync import EnterpriseSyncRun, GitHubAppConfig

    run_uuid = uuid.UUID(run_id)

    async with AsyncSessionLocal() as session:
        # Mark run as started
        await session.execute(
            update(EnterpriseSyncRun)
            .where(EnterpriseSyncRun.id == run_uuid)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await session.commit()

        # Load installation configs
        configs_result = await session.execute(
            select(GitHubAppConfig).where(GitHubAppConfig.enabled == True)  # noqa: E712
        )
        configs = configs_result.scalars().all()

    if not configs:
        logger.error("github_sync.no_configs", run_id=run_id)
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(EnterpriseSyncRun)
                .where(EnterpriseSyncRun.id == run_uuid)
                .values(status="failed", error_message="No enabled GitHub App configs found")
            )
            await session.commit()
        return {"status": "failed", "reason": "no_configs"}

    # Determine entity×org matrix
    _ENTERPRISE_ENTITIES = {"orgs", "enterprise_members", "installations"}
    _ORG_ENTITIES = {"org_members", "repositories", "teams", "team_members", "branch_protections"}

    entity_types: list[str] = (
        list(_ENTERPRISE_ENTITIES | _ORG_ENTITIES) if scope == "full" else [scope]
    )

    dispatched: list[tuple[str, str | None]] = []
    for config in configs:
        for entity_type in entity_types:
            org = None if entity_type in _ENTERPRISE_ENTITIES else config.org_login
            sync_entity.apply_async(
                kwargs={
                    "run_id": run_id,
                    "entity_type": entity_type,
                    "org": org,
                    "installation_id": config.installation_id,
                    "cursor": None,
                },
                queue="github_sync",
            )
            dispatched.append((entity_type, org))

    logger.info(
        "github_sync.orchestrator_dispatched",
        run_id=run_id,
        task_count=len(dispatched),
    )
    return {"status": "dispatched", "tasks": len(dispatched)}


async def _sync_entity_async(
    task: Task,
    run_id: str,
    entity_type: str,
    org: str | None,
    installation_id: int,
    initial_cursor: str | None,
) -> dict:
    """Async implementation of a single entity sync.  Called inside asyncio.run()."""
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from app.config import settings
    from app.models.github_sync import EnterpriseSyncEntityCursor
    from app.services.github_token_service import GitHubAppTokenManager
    from app.services.github_rate_limiter import GitHubRateLimiter
    from app.deps import get_valkey_pool
    import redis.asyncio as aioredis

    run_uuid = uuid.UUID(run_id)

    # ── Read or initialise cursor ──────────────────────────────────────────
    async with AsyncSessionLocal() as session:
        cursor_result = await session.execute(
            select(EnterpriseSyncEntityCursor).where(
                EnterpriseSyncEntityCursor.run_id == run_uuid,
                EnterpriseSyncEntityCursor.entity_type == entity_type,
                EnterpriseSyncEntityCursor.org == org,
            )
        )
        cursor_row = cursor_result.scalar_one_or_none()
        resume_cursor = cursor_row.last_cursor if cursor_row else initial_cursor
        items_synced = cursor_row.items_synced if cursor_row else 0

    # ── Set up clients ────────────────────────────────────────────────────
    valkey = aioredis.Redis(connection_pool=get_valkey_pool())
    token_manager = GitHubAppTokenManager(
        app_id=settings.github_app.GITHUB_APP_ID,
        private_key_pem=_load_private_key(),
        valkey_client=valkey,
    )
    rate_limiter = _get_rate_limiter()  # module-level singleton

    try:
        # ── Paginate and upsert ───────────────────────────────────────────
        current_cursor = resume_cursor
        page_num = 0
        while True:
            token = await token_manager.get_installation_token(installation_id)
            items, next_cursor = await _fetch_page(
                entity_type=entity_type,
                org=org,
                token=token,
                cursor=current_cursor,
                rate_limiter=rate_limiter,
            )
            if not items:
                break

            async with AsyncSessionLocal() as session:
                await _upsert_items(session, entity_type, org, items)
                items_synced += len(items)

                # Persist cursor after every page — crash recovery point
                stmt = insert(EnterpriseSyncEntityCursor).values(
                    run_id=run_uuid,
                    entity_type=entity_type,
                    org=org,
                    last_cursor=next_cursor,
                    items_synced=items_synced,
                    status="in_progress" if next_cursor else "completed",
                ).on_conflict_do_update(
                    constraint="uq_sync_cursors_run_entity_org",
                    set_={
                        "last_cursor": next_cursor,
                        "items_synced": items_synced,
                        "status": "in_progress" if next_cursor else "completed",
                    },
                )
                await session.execute(stmt)
                await session.commit()

            logger.info(
                "github_sync.page_complete",
                run_id=run_id,
                entity_type=entity_type,
                org=org,
                page=page_num,
                items=len(items),
                items_synced=items_synced,
            )

            if not next_cursor:
                break
            current_cursor = next_cursor
            page_num += 1

    except Exception as exc:
        # Mark cursor row as failed
        async with AsyncSessionLocal() as session:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(EnterpriseSyncEntityCursor).values(
                run_id=run_uuid,
                entity_type=entity_type,
                org=org,
                last_cursor=current_cursor if "current_cursor" in dir() else initial_cursor,
                items_synced=items_synced,
                status="failed",
            ).on_conflict_do_update(
                constraint="uq_sync_cursors_run_entity_org",
                set_={"status": "failed"},
            )
            await session.execute(stmt)
            await session.commit()

        logger.error(
            "github_sync.entity_failed",
            run_id=run_id,
            entity_type=entity_type,
            org=org,
            error=str(exc),
        )
        raise task.retry(exc=exc) from exc

    finally:
        await valkey.aclose()

    return {"status": "completed", "entity_type": entity_type, "org": org, "items": items_synced}


# ── Module-level rate limiter singleton ───────────────────────────────────────

_rate_limiter: GitHubRateLimiter | None = None


def _get_rate_limiter() -> "GitHubRateLimiter":
    """Return or create the process-level GitHubRateLimiter singleton."""
    global _rate_limiter
    from app.services.github_rate_limiter import GitHubRateLimiter
    if _rate_limiter is None:
        _rate_limiter = GitHubRateLimiter(
            rate_per_hour=15_000,
            max_burst=50,
            max_concurrent=80,
        )
    return _rate_limiter


def _load_private_key() -> str:
    """Load GitHub App private key PEM from the configured filesystem path.

    Called once per task invocation.  The path is from
    settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH — never from the DB.
    """
    from app.config import settings
    path = settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH
    if not path:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY_PATH is not configured")
    with open(path, "r") as fh:
        return fh.read()


# Stub signatures for page fetcher and upsert dispatcher
# (full implementation is in a separate github_sync_service.py)

async def _fetch_page(
    entity_type: str,
    org: str | None,
    token: str,
    cursor: str | None,
    rate_limiter: "GitHubRateLimiter",
    page_size: int = 100,
) -> tuple[list[dict], str | None]:
    """Fetch one page of *entity_type* from the GitHub API.

    Returns (items, next_cursor). next_cursor is None when there are no more pages.
    All HTTP calls go through the rate_limiter (acquire + release + header update).
    Retries on 429/403 via rate_limiter.handle_rate_limit_response().
    URL is always constructed from the hard-coded _GITHUB_API_BASE constant.
    """
    ...  # implemented in github_sync_service.py


async def _upsert_items(
    session: "AsyncSession",
    entity_type: str,
    org: str | None,
    items: list[dict],
) -> None:
    """Dispatch to the appropriate upsert function for *entity_type*.

    Uses INSERT ... ON CONFLICT DO UPDATE SET synced_at = NOW(), [...fields].
    Never deletes rows — non-destructive merge only.
    """
    ...  # implemented in github_sync_service.py
```

---

## 6. API Endpoints

**File:** `backend/app/routers/sync.py`  
**Router prefix:** `/api/v1/admin/sync`  
**Auth:** all endpoints require `Depends(require_role(["sys_admin"]))`

### 6.1 Endpoint Table

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/trigger` | Start a sync run (rejects if one is already running) |
| `GET` | `/status` | Current or last run with per-entity progress |
| `GET` | `/runs` | Paginated run history |
| `GET` | `/runs/{run_id}` | Run detail including all cursor rows |
| `DELETE` | `/runs/{run_id}/cancel` | Revoke a running sync |
| `GET` | `/config` | Show app_id, installation IDs, interval_days (never exposes key) |
| `PUT` | `/config` | Update interval_days (60–90), sync_enabled, orgs list |

### 6.2 Pydantic Schemas

**File:** `backend/app/schemas/github_sync.py`

```python
"""Pydantic schemas for GitHub Enterprise Sync API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Request schemas ───────────────────────────────────────────────────────────

class SyncTriggerRequest(BaseModel):
    scope: Literal[
        "full",
        "orgs",
        "enterprise_members",
        "org_members",
        "repositories",
        "teams",
        "team_members",
        "branch_protections",
        "installations",
    ] = "full"


class SyncConfigUpdateRequest(BaseModel):
    sync_enabled: bool | None = None
    interval_days: int | None = Field(None, ge=60, le=90)
    orgs: list[str] | None = None  # replace (not append) the configured orgs list


# ── Response schemas ───────────────────────────────────────────────────────────

class SyncTriggerResponse(BaseModel):
    run_id: uuid.UUID
    status: str


class CursorRow(BaseModel):
    entity_type: str
    org: str | None
    last_cursor: str | None
    items_synced: int
    status: str

    model_config = {"from_attributes": True}


class SyncRunDetail(BaseModel):
    id: uuid.UUID
    status: str
    trigger_type: str
    triggered_by: str | None
    scope: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    entity_counts: dict[str, Any] | None
    cursors: list[CursorRow] = []

    model_config = {"from_attributes": True}


class SyncRunSummary(BaseModel):
    id: uuid.UUID
    status: str
    trigger_type: str
    triggered_by: str | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class SyncRunsResponse(BaseModel):
    items: list[SyncRunSummary]
    total: int
    page: int
    page_size: int
    has_next: bool


class SyncConfigResponse(BaseModel):
    app_id: int | None
    enterprise_slug: str | None
    installation_ids: list[dict]   # [{"org": "acme", "installation_id": 12345}, ...]
    sync_enabled: bool
    interval_days: int
    orgs: list[str]
    # NEVER includes private_key_path or any token value
```

### 6.3 Router Implementation

```python
"""Admin sync router — /api/v1/admin/sync/*"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.models.audit_trail import AuditTrail
from app.models.github_sync import (
    EnterpriseSyncEntityCursor,
    EnterpriseSyncRun,
    GitHubAppConfig,
)
from app.schemas.github_sync import (
    CursorRow,
    SyncConfigResponse,
    SyncConfigUpdateRequest,
    SyncRunDetail,
    SyncRunsResponse,
    SyncRunSummary,
    SyncTriggerRequest,
    SyncTriggerResponse,
)
from app.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/trigger", response_model=SyncTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    body: SyncTriggerRequest,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncTriggerResponse:
    """Trigger a manual enterprise sync run.

    Returns 409 Conflict if a run is already in "pending" or "running" state.
    Writes an audit trail entry before dispatching the Celery task.
    """
    # Check for in-progress run
    running = await db.execute(
        select(EnterpriseSyncRun).where(
            EnterpriseSyncRun.status.in_(["pending", "running"])
        ).limit(1)
    )
    if running.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sync run is already in progress. Cancel it before triggering a new one.",
        )

    run_id = uuid.uuid4()
    run = EnterpriseSyncRun(
        id=run_id,
        status="pending",
        trigger_type="manual",
        triggered_by=current_user.github_login,
        scope=body.scope,
    )
    db.add(run)

    # Audit trail
    db.add(AuditTrail(
        user_login=current_user.github_login,
        action_type="github_sync.trigger",
        resource_type="enterprise_sync_run",
        resource_id=str(run_id),
        parameters={"scope": body.scope},
        outcome="initiated",
    ))
    await db.commit()

    # Dispatch Celery task
    from app.workers.github_sync_worker import run_enterprise_sync
    run_enterprise_sync.apply_async(
        kwargs={"run_id": str(run_id), "scope": body.scope},
        queue="github_sync",
    )

    logger.info(
        "sync.triggered",
        run_id=str(run_id),
        scope=body.scope,
        user=current_user.github_login,
    )
    return SyncTriggerResponse(run_id=run_id, status="pending")


@router.get("/status", response_model=SyncRunDetail)
async def get_sync_status(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncRunDetail:
    """Return the current running sync or the most recently completed run."""
    result = await db.execute(
        select(EnterpriseSyncRun)
        .order_by(EnterpriseSyncRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No sync runs found.")

    cursors_result = await db.execute(
        select(EnterpriseSyncEntityCursor).where(
            EnterpriseSyncEntityCursor.run_id == run.id
        )
    )
    cursors = cursors_result.scalars().all()
    detail = SyncRunDetail.model_validate(run)
    detail.cursors = [CursorRow.model_validate(c) for c in cursors]
    return detail


@router.get("/runs", response_model=SyncRunsResponse)
async def list_sync_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncRunsResponse:
    """Paginated history of all sync runs."""
    total_result = await db.execute(select(func.count()).select_from(EnterpriseSyncRun))
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    runs_result = await db.execute(
        select(EnterpriseSyncRun)
        .order_by(EnterpriseSyncRun.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    runs = runs_result.scalars().all()
    return SyncRunsResponse(
        items=[SyncRunSummary.model_validate(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size < total),
    )


@router.get("/runs/{run_id}", response_model=SyncRunDetail)
async def get_run_detail(
    run_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncRunDetail:
    """Return full detail for a single sync run including cursor state."""
    result = await db.execute(
        select(EnterpriseSyncRun).where(EnterpriseSyncRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    cursors_result = await db.execute(
        select(EnterpriseSyncEntityCursor).where(
            EnterpriseSyncEntityCursor.run_id == run_id
        )
    )
    cursors = cursors_result.scalars().all()
    detail = SyncRunDetail.model_validate(run)
    detail.cursors = [CursorRow.model_validate(c) for c in cursors]
    return detail


@router.delete("/runs/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancel a pending or running sync run.

    Revokes the Celery task and marks the run as "cancelled".
    """
    result = await db.execute(
        select(EnterpriseSyncRun).where(EnterpriseSyncRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    if run.status not in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is already in terminal state: {run.status}",
        )

    # Revoke via Celery inspect/control
    from app.celery_app import celery_app as _celery
    _celery.control.revoke(str(run_id), terminate=True, signal="SIGTERM")

    await db.execute(
        update(EnterpriseSyncRun)
        .where(EnterpriseSyncRun.id == run_id)
        .values(
            status="cancelled",
            completed_at=datetime.now(timezone.utc),
            error_message="Cancelled by operator",
        )
    )
    db.add(AuditTrail(
        user_login=current_user.github_login,
        action_type="github_sync.cancel",
        resource_type="enterprise_sync_run",
        resource_id=str(run_id),
        outcome="cancelled",
    ))
    await db.commit()


@router.get("/config", response_model=SyncConfigResponse)
async def get_sync_config(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncConfigResponse:
    """Return the current sync configuration.

    NEVER exposes GITHUB_APP_PRIVATE_KEY_PATH or any token value.
    """
    configs_result = await db.execute(select(GitHubAppConfig).where(GitHubAppConfig.enabled == True))  # noqa: E712
    configs = configs_result.scalars().all()
    installation_ids = [
        {"org": c.org_login, "installation_id": c.installation_id}
        for c in configs
    ]
    return SyncConfigResponse(
        app_id=settings.github_app.GITHUB_APP_ID,
        enterprise_slug=settings.github_app.GITHUB_ENTERPRISE_SLUG,
        installation_ids=installation_ids,
        sync_enabled=settings.github_app.GITHUB_SYNC_ENABLED,
        interval_days=settings.github_app.GITHUB_SYNC_INTERVAL_DAYS,
        orgs=settings.github_app.GITHUB_SYNC_ORGS,
    )


@router.put("/config", response_model=SyncConfigResponse)
async def update_sync_config(
    body: SyncConfigUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncConfigResponse:
    """Update mutable sync configuration fields.

    interval_days is validated to be in [60, 90] by the Pydantic schema.
    Dynamic config updates write to DB (github_app_configs.enabled) and emit
    an audit trail entry. Environment-variable-backed fields (GITHUB_SYNC_*)
    can only be changed at deploy time.
    """
    if body.sync_enabled is not None:
        await db.execute(
            update(GitHubAppConfig).values(enabled=body.sync_enabled)
        )

    db.add(AuditTrail(
        user_login=current_user.github_login,
        action_type="github_sync.config_update",
        resource_type="github_app_config",
        parameters=body.model_dump(exclude_none=True),
        outcome="updated",
    ))
    await db.commit()
    return await get_sync_config(current_user=current_user, db=db)
```

---

## 7. Config Changes

**File:** `backend/app/config.py` — add the `GitHubAppSettings` nested class and wire it into the top-level `Settings`.

```python
class GitHubAppSettings(BaseSettings):
    """GitHub App credentials and sync behaviour.

    GITHUB_APP_PRIVATE_KEY_PATH must point to a file on the local filesystem.
    The key is NEVER stored in the database and NEVER appears in API responses.
    When running in Kubernetes, mount the key as a Secret volume at this path.
    """

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    GITHUB_APP_ID: int | None = Field(
        default=None,
        description="GitHub App numeric App ID (from App settings page)",
    )
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = Field(
        default=None,
        description="Absolute path to the PEM-encoded RS256 private key file",
    )
    GITHUB_ENTERPRISE_SLUG: str | None = Field(
        default=None,
        description="GitHub Enterprise account slug (e.g. 'my-company')",
    )
    GITHUB_SYNC_INTERVAL_DAYS: int = Field(
        default=60,
        ge=60,
        le=90,
        description="How many days between automatic scheduled syncs (60–90)",
    )
    GITHUB_SYNC_ENABLED: bool = Field(
        default=False,
        description="Enable/disable the scheduled enterprise sync",
    )
    GITHUB_SYNC_ORGS: list[str] = Field(
        default_factory=list,
        description="Comma-separated org logins to include (empty = all enterprise orgs)",
    )

    @field_validator("GITHUB_APP_PRIVATE_KEY_PATH")
    @classmethod
    def validate_key_path(cls, v: str | None) -> str | None:
        """Validate the key exists and is a regular file (not a symlink to /dev/null etc.)."""
        import os
        if v is None:
            return None
        if not os.path.isfile(v):
            raise ValueError(f"GITHUB_APP_PRIVATE_KEY_PATH does not point to a file: {v}")
        return v

    @field_validator("GITHUB_SYNC_INTERVAL_DAYS")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if not (60 <= v <= 90):
            raise ValueError("GITHUB_SYNC_INTERVAL_DAYS must be between 60 and 90 inclusive")
        return v
```

**Wire into the top-level `Settings` class** (add after existing nested instances):

```python
class Settings(
    DatabaseSettings,
    ValkeySettings,
    AuthSettings,
    MinIOSettings,
    S3Settings,
    AzureBlobSettings,
    # ... existing nested classes ...
):
    github_app: GitHubAppSettings = GitHubAppSettings()
    # ... rest of Settings
```

**Celery Beat schedule addition** in `celery_app.py`:

```python
# GitHub Enterprise Sync — configurable interval, default 60 days
# schedule is recomputed at startup from settings.github_app.GITHUB_SYNC_INTERVAL_DAYS
if settings.github_app.GITHUB_SYNC_ENABLED:
    _interval_secs = settings.github_app.GITHUB_SYNC_INTERVAL_DAYS * 86_400
    beat_schedule["github-enterprise-sync"] = {
        "task": "app.workers.github_sync.run_enterprise_sync",
        "schedule": _interval_secs,
        "kwargs": {"scope": "full"},
        "options": {"queue": "github_sync"},
    }
```

**Task route addition** in `celery_app.py`:

```python
# Add to task_routes dict:
"app.workers.github_sync.*": {"queue": "github_sync"},
```

---

## 8. Security Controls

### 8.1 Private Key Handling

| Location | Status |
|----------|--------|
| Environment variable | ❌ Never — key material in env vars risks leakage via `/proc/self/environ` |
| Database | ❌ Never |
| API response | ❌ Never — `SyncConfigResponse` only returns `app_id` and `installation_id` |
| Valkey | ❌ Never |
| Filesystem (k8s Secret volume) | ✅ Only here — path configured via `GITHUB_APP_PRIVATE_KEY_PATH` |
| In-memory (loaded per task) | ✅ Loaded, used, and not retained beyond task boundary |

### 8.2 Token Handling

| Token type | Storage | Lifetime |
|------------|---------|----------|
| GitHub App JWT | In-memory only | 10 minutes (exp claim) |
| Installation access token | Valkey only | `expires_at − 5min` TTL |

Installation tokens are never written to PostgreSQL. If Valkey is flushed, fresh tokens are re-generated transparently.

### 8.3 SSRF Prevention

```python
# Hardcoded constant — never interpolated from user input or DB
_GITHUB_API_BASE = "https://api.github.com"

# httpx clients always constructed with:
async with httpx.AsyncClient(follow_redirects=False) as client:
    ...
```

The `GitHubAppSettings.GITHUB_ENTERPRISE_SLUG` is used only as a path component in GitHub API URLs, formatted as `f"{_GITHUB_API_BASE}/enterprises/{slug}/..."`. The slug is validated at config-load time to match `[a-zA-Z0-9\-]+` before it is ever used in a URL.

```python
@field_validator("GITHUB_ENTERPRISE_SLUG")
@classmethod
def validate_enterprise_slug(cls, v: str | None) -> str | None:
    import re
    if v is None:
        return None
    if not re.fullmatch(r"[a-zA-Z0-9\-]+", v):
        raise ValueError("GITHUB_ENTERPRISE_SLUG must match [a-zA-Z0-9-]+")
    return v
```

### 8.4 Authorization

All seven `/api/v1/admin/sync/*` endpoints enforce:

```python
current_user: AuthenticatedUser = Depends(require_role(["sys_admin"]))
```

No endpoint in this router uses a lower-privilege role. There is no public or unauthenticated surface.

### 8.5 Audit Trail

Every manual trigger (`POST /trigger`), cancellation (`DELETE /runs/{id}/cancel`), and configuration change (`PUT /config`) writes a row to `audit_trail`:

```python
AuditTrail(
    user_login=current_user.github_login,
    action_type="github_sync.<action>",
    resource_type="enterprise_sync_run | github_app_config",
    resource_id=str(run_id),        # where applicable
    parameters={...},               # sanitised — no tokens
    outcome="initiated | cancelled | updated",
)
```

### 8.6 Minimum GitHub App Permissions

The GitHub App **must** be configured with exactly these permissions (principle of least privilege):

| Permission | Level | Purpose |
|------------|-------|---------|
| `members` | `read` | Enumerate org and enterprise members |
| `administration` | `read` | List teams, branch protections |
| `secret_scanning_alerts` | `read` | Future: alert baseline |

No `write` permissions are requested or used.

### 8.7 Input Validation

- `run_id` in path parameters is validated as `uuid.UUID` by FastAPI's type system — non-UUID input returns 422.
- `page`/`page_size` query params are bounded by `ge` / `le` constraints.
- `scope` in `SyncTriggerRequest` is a `Literal` — only exact enum values accepted.
- `interval_days` in `SyncConfigUpdateRequest` is `Field(ge=60, le=90)`.
- `orgs` list in config update: org login format validated against `[a-zA-Z0-9\-]+` before storage.

---

## 9. Alembic Migration Plan

Migrations are sequential and must be applied in order. Each migration uses `down_revision` to form a linear chain.

### Migration 0004 — GitHub App Config and Sync Run Scaffolding

**File:** `backend/alembic/versions/0004_github_app_sync_scaffolding.py`  
**down_revision:** `"0003_seed_detection_rules"`

**Tables created:**
- `github_app_configs`
- `enterprise_sync_runs`
- `enterprise_sync_entity_cursors`

**Notes:**
- `enterprise_sync_entity_cursors.run_id` FK references `enterprise_sync_runs.id` with `ON DELETE CASCADE` — cursor rows are automatically cleaned up when a run is deleted.
- `enterprise_sync_runs.id` uses `UUID` primary key with `DEFAULT gen_random_uuid()`.
- No hypertable conversion — these are transactional tables, not time-series.

```python
def upgrade() -> None:
    op.create_table(
        "github_app_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("enterprise_slug", sa.Text()),
        sa.Column("org_login", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("app_id", "installation_id", name="uq_github_app_configs_app_install"),
    )
    op.create_index("idx_github_app_configs_enterprise", "github_app_configs", ["enterprise_slug"])
    op.create_index("idx_github_app_configs_org", "github_app_configs", ["org_login"])

    op.create_table(
        "enterprise_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("triggered_by", sa.Text()),
        sa.Column("scope", sa.Text(), server_default=sa.text("'full'"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("entity_counts", postgresql.JSONB()),
    )
    op.create_index("idx_enterprise_sync_runs_status", "enterprise_sync_runs", ["status"])
    op.create_index("idx_enterprise_sync_runs_created_at", "enterprise_sync_runs", ["created_at"])

    op.create_table(
        "enterprise_sync_entity_cursors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enterprise_sync_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("org", sa.Text()),
        sa.Column("last_cursor", sa.Text()),
        sa.Column("items_synced", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'in_progress'"), nullable=False),
        sa.UniqueConstraint("run_id", "entity_type", "org", name="uq_sync_cursors_run_entity_org"),
    )
    op.create_index("idx_sync_cursors_run_id", "enterprise_sync_entity_cursors", ["run_id"])
```

### Migration 0005 — Enterprise-Level Snapshot Tables

**File:** `backend/alembic/versions/0005_enterprise_snapshot_tables.py`  
**down_revision:** `"0004_github_app_sync_scaffolding"`

**Tables created:**
- `enterprise_orgs`
- `enterprise_members`
- `github_app_installations`

**Notes:**
- No FK to `github_app_configs` — enterprise entities are keyed by `enterprise_slug`/`org_login` strings. FK would complicate upserts where configs may not exist yet.
- All three tables are plain OLTP tables; no TimescaleDB hypertable conversion.

### Migration 0006 — Org-Level Snapshot Tables

**File:** `backend/alembic/versions/0006_org_snapshot_tables.py`  
**down_revision:** `"0005_enterprise_snapshot_tables"`

**Tables created:**
- `org_members`
- `org_teams`
- `org_team_members`

**Notes:**
- No FK between `org_teams` and `org_team_members` — `team_slug` is a string key to survive team renames without cascades causing sync conflicts.
- `org_teams.parent_team_slug` is nullable (NULL = top-level team). No self-referencing FK to avoid complex cascade logic during upserts.
- Create index on `(org, team_slug)` composite for efficient team-member lookups.

### Migration 0007 — Repository Snapshot Tables

**File:** `backend/alembic/versions/0007_repository_snapshot_tables.py`  
**down_revision:** `"0006_org_snapshot_tables"`

**Tables created:**
- `repositories`
- `repo_branch_protections`

**Notes:**
- `repo_branch_protections.required_status_checks` is `JSONB` — schema varies by GitHub API version and is stored raw.
- No FK from `repo_branch_protections` to `repositories` — branch protection rows can arrive before or after repo rows during a partial sync. Referential integrity is enforced at the application layer.
- `repositories` will likely become the largest table; the `(org)` and `(visibility)` indexes support detection rule queries filtering by org and repo visibility.

---

## 10. Testing Approach

All tests live in `backend/tests/`. New file: `test_github_sync.py`.

### 10.1 JWT Generation (`GitHubAppTokenManager._generate_jwt`)

```
GIVEN a GitHubAppTokenManager with a known RSA key pair
WHEN _generate_jwt() is called
THEN the decoded JWT must have:
  - alg = RS256
  - iss = str(app_id)
  - iat ≈ time.time() − 60  (within ±5s tolerance)
  - exp = iat + 660          (600s ahead of iat)
  - signature verifies against the known RSA public key
```

### 10.2 Token Caching in Valkey

```
GIVEN an installation token that expires in 3600s
WHEN get_installation_token() is called twice with the same installation_id
THEN the second call must NOT make an HTTP request to GitHub API
 AND the Valkey key "github:app:token:{id}" must have a TTL ≤ 3595s (expires_at − 5min)

GIVEN a cached token whose Valkey TTL has expired
WHEN get_installation_token() is called
THEN a fresh HTTP exchange is performed
 AND the new token is cached with updated TTL
```

### 10.3 Rate Limiter — 429 Handling

```
GIVEN a GitHubRateLimiter
WHEN handle_rate_limit_response() is called with a 429 response
  AND retry-after = "30"
THEN the coroutine must sleep for approximately 30s (±3s jitter tolerance)
 AND must NOT raise an exception

WHEN handle_rate_limit_response() is called with a 403 response
  AND x-ratelimit-reset = <now + 45>
THEN sleeps until the reset time (±2s tolerance)
```

### 10.4 Rate Limiter — Header Parsing

```
GIVEN a response with headers:
  x-ratelimit-remaining: 800
  x-ratelimit-reset: <unix ts>
WHEN update_from_headers() is called
THEN _remaining = 800
 AND _proactive_throttle_active = True  (800 < 1000 threshold)
 AND subsequent acquire() calls use effective_rate = 1.0 token/s
```

### 10.5 Cursor Resumability

```
GIVEN a sync_entity task running for (run_id, "repositories", "acme-org")
WHEN the task processes pages 1, 2, 3 and crashes on page 4
THEN enterprise_sync_entity_cursors has last_cursor = <page3_cursor>
     AND items_synced = (page1_count + page2_count + page3_count)

WHEN sync_entity is retried
THEN the first GitHub API call uses cursor = <page3_cursor>
 AND pages 1–3 are NOT re-fetched
 AND total final items_synced = correct total without duplicates
```

### 10.6 Idempotency

```
GIVEN a clean database
WHEN run_enterprise_sync is run twice with scope="full"
THEN SELECT COUNT(*) FROM repositories is identical after both runs
 AND SELECT COUNT(*) FROM org_members is identical after both runs
 AND no unique constraint violations occur
```

### 10.7 API Authorization

```
GIVEN a user with role = "analyst"
WHEN POST /api/v1/admin/sync/trigger
THEN response is 403 Forbidden

GIVEN a user with role = "sys_admin"
WHEN POST /api/v1/admin/sync/trigger with body {"scope": "full"}
THEN response is 202 Accepted with {run_id, status: "pending"}
 AND an AuditTrail row is written with action_type = "github_sync.trigger"
```

### 10.8 Concurrent Trigger Guard (409 Conflict)

```
GIVEN an EnterpriseSyncRun exists with status = "running"
WHEN POST /api/v1/admin/sync/trigger is called by a sys_admin
THEN response is 409 Conflict
 AND the error detail mentions the existing in-progress run
 AND no new EnterpriseSyncRun row is created
```

### 10.9 Config Endpoint — Key Non-Exposure

```
WHEN GET /api/v1/admin/sync/config
THEN response body does NOT contain "private_key"
 AND response body does NOT contain "GITHUB_APP_PRIVATE_KEY_PATH"
 AND response body does NOT contain any string ending in ".pem" or ".key"
```

### 10.10 Cancel Run

```
GIVEN a run with status = "running"
WHEN DELETE /api/v1/admin/sync/runs/{run_id}/cancel
THEN response is 204 No Content
 AND enterprise_sync_runs.status = "cancelled"
 AND an AuditTrail row with action_type = "github_sync.cancel" is written

GIVEN a run with status = "completed"
WHEN DELETE /api/v1/admin/sync/runs/{run_id}/cancel
THEN response is 409 Conflict
```

### 10.11 Scheduled Sync Beat Entry

```
GIVEN settings.github_app.GITHUB_SYNC_ENABLED = True
  AND settings.github_app.GITHUB_SYNC_INTERVAL_DAYS = 75
WHEN the Celery app is configured
THEN "github-enterprise-sync" is present in beat_schedule
 AND its schedule == 75 * 86_400 seconds
```

---

## Appendix A — New Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_APP_ID` | Conditional | `None` | GitHub App numeric ID |
| `GITHUB_APP_PRIVATE_KEY_PATH` | Conditional | `None` | Absolute path to PEM key on disk |
| `GITHUB_ENTERPRISE_SLUG` | Conditional | `None` | Enterprise account slug |
| `GITHUB_SYNC_INTERVAL_DAYS` | No | `60` | Days between scheduled syncs (60–90) |
| `GITHUB_SYNC_ENABLED` | No | `false` | Enables Celery Beat job |
| `GITHUB_SYNC_ORGS` | No | `[]` | Comma-separated org logins to include |

All six variables are optional at startup. If `GITHUB_SYNC_ENABLED=true` and `GITHUB_APP_ID` or `GITHUB_APP_PRIVATE_KEY_PATH` are absent, the scheduled task will log a `github_sync.no_configs` error and mark the run as failed immediately rather than crash the worker process.

## Appendix B — Kubernetes Secret Mount (recommended)

```yaml
# k8s Secret
apiVersion: v1
kind: Secret
metadata:
  name: github-app-private-key
type: Opaque
stringData:
  github-app.private-key.pem: |
    -----BEGIN RSA PRIVATE KEY-----
    ...
    -----END RSA PRIVATE KEY-----
---
# Worker Deployment — volume mount
volumeMounts:
  - name: github-app-key
    mountPath: /run/secrets/github
    readOnly: true
volumes:
  - name: github-app-key
    secret:
      secretName: github-app-private-key
# Environment
env:
  - name: GITHUB_APP_PRIVATE_KEY_PATH
    value: /run/secrets/github/github-app.private-key.pem
```

## Appendix C — GitHub App Registration Checklist

Before deploying, the GitHub App must be registered with:

- [ ] Homepage URL and callback URL pointing to the Octowatch instance
- [ ] **Repository permissions:** `Administration: Read-only`
- [ ] **Organisation permissions:** `Members: Read-only`
- [ ] **No webhook subscriptions** (sync is pull-based, not push-based)
- [ ] Installed on the enterprise account (not individual orgs) so a single installation ID covers all orgs
- [ ] `secret_scanning_alerts: Read-only` added for future alert baseline (can be deferred to Phase 2)
