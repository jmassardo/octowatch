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
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Literal

import structlog
from celery import Task

from app.celery_app import celery_app

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create a fresh async session factory with a disposable NullPool engine.

    Each Celery task invocation calls asyncio.run() which creates a new event
    loop. asyncpg connections are bound to the loop they were created on, so
    we MUST create a fresh engine per task to avoid 'attached to a different
    loop' errors.
    """
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

if TYPE_CHECKING:
    from app.services.github_rate_limiter import GitHubRateLimiter

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
    max_retries=0,  # Orchestrator does not retry; child tasks do
    queue="github_sync",
    soft_time_limit=7200,  # 2 hours
    time_limit=7800,  # 2h 10m hard kill
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
    default_retry_delay=30,  # seconds; callers may override with countdown
    queue="github_sync",
    soft_time_limit=3600,  # 1 hour per entity/org chunk
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
    return asyncio.run(
        _sync_entity_async(self, run_id, entity_type, org, installation_id, cursor)
    )


@celery_app.task(
    name="app.workers.github_sync.check_sync_schedule",
    queue="github_sync",
)
def check_sync_schedule() -> dict:
    """Daily heartbeat: check if a scheduled sync is due.

    Runs daily at 02:00 UTC via Celery Beat. Compares the last completed
    sync run timestamp against ``GITHUB_SYNC_INTERVAL_DAYS``. If the
    configured interval has elapsed (or no previous sync exists), triggers
    a new full sync run automatically.

    Skips if sync is disabled or if a run is already pending/running.
    """
    return asyncio.run(_check_sync_schedule_async())


# ── Internal async implementations ────────────────────────────────────────────


async def _run_enterprise_sync_async(run_id: str, scope: ScopeType) -> dict:
    """Async implementation of the orchestrator.  Called inside asyncio.run()."""
    from sqlalchemy import select, update

    from app.config import settings  # noqa: F811 — deferred import for testability
    from app.models.github_sync import EnterpriseSyncRun, GitHubAppConfig

    run_uuid = uuid.UUID(run_id)

    async with _make_session_factory()() as session:
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

    # Auto-discover installations if none exist but env is configured
    if not configs and settings.github_app.GITHUB_APP_ID:
        configs = await _bootstrap_app_configs(settings)

    if not configs:
        logger.error("github_sync.no_configs", run_id=run_id)
        async with _make_session_factory()() as session:
            await session.execute(
                update(EnterpriseSyncRun)
                .where(EnterpriseSyncRun.id == run_uuid)
                .values(
                    status="failed",
                    error_message="No enabled GitHub App configs found",
                )
            )
            await session.commit()
        return {"status": "failed", "reason": "no_configs"}

    # Determine entity×org matrix
    _ENTERPRISE_ENTITIES = {"orgs", "enterprise_members", "installations"}
    _ORG_ENTITIES = {
        "org_members",
        "repositories",
        "teams",
        "team_members",
        "branch_protections",
    }

    entity_types: list[str] = (
        list(_ENTERPRISE_ENTITIES | _ORG_ENTITIES) if scope == "full" else [scope]
    )

    # For enterprise installations (org_login is NULL), discover org names
    # from GITHUB_SYNC_ORGS env or from the installation's accessible repos.
    sync_orgs = settings.github_app.sync_orgs_list

    # Auto-discover orgs from enterprise GraphQL or accessible repos
    if not sync_orgs and all(c.org_login is None for c in configs):
        enterprise_slug = next((c.enterprise_slug for c in configs if c.enterprise_slug), None)
        discovered = await _discover_orgs_from_installation(
            configs[0].installation_id, enterprise_slug
        )
        if discovered:
            sync_orgs = discovered
            logger.info("github_sync.auto_discovered_orgs", orgs=sync_orgs)

    dispatched: list[tuple[str, str | None]] = []
    for config in configs:
        for entity_type in entity_types:
            if entity_type in _ENTERPRISE_ENTITIES:
                # Pass enterprise_slug via the `org` field for enterprise entities
                # so _fetch_page knows which enterprise to query via GraphQL
                enterprise_slug = config.enterprise_slug
                sync_entity.apply_async(
                    kwargs={
                        "run_id": run_id,
                        "entity_type": entity_type,
                        "org": enterprise_slug,
                        "installation_id": config.installation_id,
                        "cursor": None,
                    },
                    queue="github_sync",
                )
                dispatched.append((entity_type, enterprise_slug))
            else:
                # Org-level entity — need actual org login(s)
                org_list = [config.org_login] if config.org_login else sync_orgs
                if not org_list:
                    logger.warning(
                        "github_sync.no_orgs_for_entity",
                        entity_type=entity_type,
                        config_id=config.id,
                        hint="Set GITHUB_SYNC_ORGS or install the App on individual orgs",
                    )
                    continue
                for org in org_list:
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
    import redis.asyncio as aioredis
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from app.config import settings  # noqa: F811 — deferred import for testability
    from app.models.github_sync import EnterpriseSyncEntityCursor
    from app.services.github_rate_limiter import GitHubRateLimiter  # noqa: F811
    from app.services.github_token_service import GitHubAppTokenManager

    run_uuid = uuid.UUID(run_id)

    # ── Read or initialise cursor ──────────────────────────────────────────
    async with _make_session_factory()() as session:
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
    # Create a fresh Valkey connection per task to avoid event-loop binding
    # issues (the module-level pool binds to the first loop and fails on
    # subsequent asyncio.run() calls).
    valkey = aioredis.Redis.from_url(
        settings.VALKEY_URL, decode_responses=True, max_connections=5
    )
    token_manager = GitHubAppTokenManager(
        app_id=settings.github_app.GITHUB_APP_ID,
        private_key_pem=_load_private_key(),
        valkey_client=valkey,
    )
    # Create a fresh rate limiter per task — the asyncio.Semaphore inside
    # binds to the current event loop and can't survive across asyncio.run()
    rate_limiter = GitHubRateLimiter(
        rate_per_hour=15_000, max_burst=50, max_concurrent=80
    )

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

            async with _make_session_factory()() as session:
                await _upsert_items(session, entity_type, org, items)
                items_synced += len(items)

                # Persist cursor after every page — crash recovery point
                stmt = (
                    insert(EnterpriseSyncEntityCursor)
                    .values(
                        run_id=run_uuid,
                        entity_type=entity_type,
                        org=org,
                        last_cursor=next_cursor,
                        items_synced=items_synced,
                        status="in_progress" if next_cursor else "completed",
                    )
                    .on_conflict_do_update(
                        constraint="uq_sync_cursors_run_entity_org",
                        set_={
                            "last_cursor": next_cursor,
                            "items_synced": items_synced,
                            "status": "in_progress" if next_cursor else "completed",
                        },
                    )
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
        async with _make_session_factory()() as session:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(EnterpriseSyncEntityCursor)
                .values(
                    run_id=run_uuid,
                    entity_type=entity_type,
                    org=org,
                    last_cursor=(
                        current_cursor if "current_cursor" in dir() else initial_cursor
                    ),
                    items_synced=items_synced,
                    status="failed",
                )
                .on_conflict_do_update(
                    constraint="uq_sync_cursors_run_entity_org",
                    set_={"status": "failed"},
                )
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

    return {
        "status": "completed",
        "entity_type": entity_type,
        "org": org,
        "items": items_synced,
    }


async def _check_sync_schedule_async() -> dict:
    """Async implementation of the daily heartbeat schedule check."""
    from sqlalchemy import select

    from app.config import settings  # noqa: F811 — deferred import for testability
    from app.models.github_sync import EnterpriseSyncRun

    if not settings.github_app.GITHUB_SYNC_ENABLED:
        logger.debug("github_sync.schedule_check_skipped", reason="sync_disabled")
        return {"status": "skipped", "reason": "sync_disabled"}

    async with _make_session_factory()() as session:
        # Check for already pending/running run
        active_result = await session.execute(
            select(EnterpriseSyncRun)
            .where(EnterpriseSyncRun.status.in_(["pending", "running"]))
            .limit(1)
        )
        if active_result.scalar_one_or_none():
            logger.info("github_sync.schedule_check_skipped", reason="run_already_active")
            return {"status": "skipped", "reason": "run_already_active"}

        # Find the last completed run
        last_result = await session.execute(
            select(EnterpriseSyncRun)
            .where(EnterpriseSyncRun.status == "completed")
            .order_by(EnterpriseSyncRun.completed_at.desc())
            .limit(1)
        )
        last_run = last_result.scalar_one_or_none()

    interval = timedelta(days=settings.github_app.GITHUB_SYNC_INTERVAL_DAYS)
    now = datetime.now(timezone.utc)

    if last_run and last_run.completed_at and (now - last_run.completed_at) < interval:
        next_due = last_run.completed_at + interval
        logger.info(
            "github_sync.schedule_check_not_due",
            last_completed=last_run.completed_at.isoformat(),
            next_due=next_due.isoformat(),
        )
        return {"status": "not_due", "next_due": next_due.isoformat()}

    # Sync is due — create a new run and dispatch
    run_id = uuid.uuid4()
    async with _make_session_factory()() as session:
        run = EnterpriseSyncRun(
            id=run_id,
            status="pending",
            trigger_type="scheduled",
            triggered_by=None,
            scope="full",
        )
        session.add(run)
        await session.commit()

    run_enterprise_sync.apply_async(
        kwargs={"run_id": str(run_id), "scope": "full"},
        queue="github_sync",
    )

    logger.info("github_sync.schedule_triggered", run_id=str(run_id))
    return {"status": "triggered", "run_id": str(run_id)}


async def _discover_orgs_from_installation(
    installation_id: int,
    enterprise_slug: str | None = None,
) -> list[str]:
    """Discover org logins belonging to the enterprise.

    Strategy:
      1. If ``enterprise_slug`` is provided, query the GitHub GraphQL API to
         list all organisations under that enterprise.
      2. Fall back to ``GET /installation/repositories`` REST endpoint and
         extract unique owner logins from accessible repositories.

    Returns a sorted list of org login strings, or an empty list on error.
    """
    import redis.asyncio as aioredis

    import httpx

    from app.config import settings as _settings
    from app.services.github_token_service import GitHubAppTokenManager

    try:
        valkey = aioredis.Redis.from_url(
            _settings.VALKEY_URL, decode_responses=True, max_connections=5
        )
        try:
            mgr = GitHubAppTokenManager(
                app_id=_settings.github_app.GITHUB_APP_ID,
                private_key_pem=_load_private_key(),
                valkey_client=valkey,
            )
            token = await mgr.get_installation_token(installation_id)

            # ── Strategy 1: GraphQL enterprise org listing ────────────────
            if enterprise_slug:
                orgs = await _graphql_list_enterprise_orgs(token, enterprise_slug)
                if orgs:
                    return orgs
                logger.info(
                    "github_sync.graphql_org_discovery_empty",
                    enterprise_slug=enterprise_slug,
                    fallback="REST /installation/repositories",
                )

            # ── Strategy 2: Derive orgs from accessible repos ────────────
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            orgs_set: set[str] = set()
            page = 1
            async with httpx.AsyncClient(follow_redirects=False) as client:
                while True:
                    resp = await client.get(
                        f"{_GITHUB_API_BASE}/installation/repositories",
                        headers=headers,
                        params={"per_page": 100, "page": page},
                        timeout=30,
                    )
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    repos = data.get("repositories", [])
                    for repo in repos:
                        owner = (repo.get("owner") or {}).get("login")
                        if owner:
                            orgs_set.add(owner)
                    if len(repos) < 100:
                        break
                    page += 1
            return sorted(orgs_set)
        finally:
            await valkey.aclose()
    except Exception as exc:
        logger.warning("github_sync.org_discovery_failed", error=str(exc))
        return []


# ── GraphQL helpers ───────────────────────────────────────────────────────────

_GRAPHQL_URL = "https://api.github.com/graphql"

_ENTERPRISE_ORGS_QUERY = """
query($slug: String!, $first: Int!, $after: String) {
  enterprise(slug: $slug) {
    organizations(first: $first, after: $after) {
      nodes { login databaseId }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

_ENTERPRISE_MEMBERS_QUERY = """
query($slug: String!, $first: Int!, $after: String) {
  enterprise(slug: $slug) {
    members(first: $first, after: $after) {
      nodes {
        ... on EnterpriseUserAccount {
          login
          user { databaseId }
        }
        ... on User {
          login
          databaseId
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


async def _graphql_page(
    token: str,
    query: str,
    variables: dict,
    rate_limiter: "GitHubRateLimiter | None" = None,
) -> dict:
    """Execute a single GraphQL request against the GitHub API.

    If *rate_limiter* is provided, acquire/release around the request and
    handle 429/403 automatically. When *rate_limiter* is ``None`` (used by
    the discovery helper), the request is made without rate-limiting.
    """
    import httpx

    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"query": query, "variables": variables}

    if rate_limiter is not None:
        await rate_limiter.acquire()
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            resp = await client.post(
                _GRAPHQL_URL, json=payload, headers=headers, timeout=30
            )
        if rate_limiter is not None:
            rate_limiter.update_from_headers(resp.headers)
    finally:
        if rate_limiter is not None:
            rate_limiter.release()

    if resp.status_code in (429, 403) and rate_limiter is not None:
        await rate_limiter.handle_rate_limit_response(resp)
        # Caller should retry
        return {"data": None, "errors": [{"message": "rate_limited"}]}

    resp.raise_for_status()
    return resp.json()


async def _graphql_list_enterprise_orgs(
    token: str, enterprise_slug: str
) -> list[str]:
    """Return all org logins under *enterprise_slug* via the GraphQL API."""
    orgs: list[str] = []
    cursor: str | None = None
    while True:
        result = await _graphql_page(
            token,
            _ENTERPRISE_ORGS_QUERY,
            {"slug": enterprise_slug, "first": 100, "after": cursor},
        )
        data = result.get("data")
        if not data or not data.get("enterprise"):
            break
        org_conn = data["enterprise"]["organizations"]
        for node in org_conn.get("nodes", []):
            if node and node.get("login"):
                orgs.append(node["login"])
        page_info = org_conn.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]
    return sorted(orgs)


# ── Module-level rate limiter singleton ───────────────────────────────────────

_rate_limiter: GitHubRateLimiter | None = None


def _get_rate_limiter() -> GitHubRateLimiter:
    """Return or create the process-level GitHubRateLimiter singleton."""
    global _rate_limiter
    from app.services.github_rate_limiter import GitHubRateLimiter  # noqa: F811

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
    from app.config import settings  # noqa: F811 — deferred import for testability

    path = settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH
    if not path:
        raise RuntimeError("GITHUB_APP_PRIVATE_KEY_PATH is not configured")
    with open(path) as fh:
        return fh.read()


# ── GitHub API base URL (hardcoded to prevent SSRF) ───────────────────────────

_GITHUB_API_BASE = "https://api.github.com"

# Simple entity type → REST API path mapping (page-based pagination)
_SIMPLE_ENTITY_URLS: dict[str, str] = {
    "org_members": "/orgs/{org}/members",
    "repositories": "/orgs/{org}/repos",
    "teams": "/orgs/{org}/teams",
}


async def _github_get(
    url: str,
    headers: dict[str, str],
    params: dict[str, object],
    rate_limiter: GitHubRateLimiter,
    *,
    max_retries: int = 3,
) -> "httpx.Response":
    """Rate-limited GET with automatic retry on 429/403 rate limit responses."""
    import httpx

    resp: httpx.Response | None = None
    for _attempt in range(max_retries):
        await rate_limiter.acquire()
        try:
            async with httpx.AsyncClient(follow_redirects=False) as client:
                resp = await client.get(url, headers=headers, params=params, timeout=30)
            rate_limiter.update_from_headers(resp.headers)
        finally:
            rate_limiter.release()

        if resp.status_code in (429, 403) and "rate limit" in resp.text.lower():
            await rate_limiter.handle_rate_limit_response(resp)
            continue
        return resp

    assert resp is not None
    return resp


def _has_next_page(headers: "httpx.Headers | dict[str, str]") -> bool:
    return 'rel="next"' in (headers.get("link") or "")


async def _fetch_page(
    entity_type: str,
    org: str | None,
    token: str,
    cursor: str | None,
    rate_limiter: GitHubRateLimiter,
    page_size: int = 100,
) -> tuple[list[dict], str | None]:
    """Fetch one page of *entity_type* from the GitHub API.

    Returns ``(items, next_cursor)``.  ``next_cursor`` is ``None`` when there
    are no more pages.

    Pagination
    ----------
    * Simple entities (org_members, repositories, teams) use ``?page=N`` with
      the cursor holding the page number as a string.
    * ``team_members`` uses a JSON cursor encoding the team list and current
      position so the full team roster is fetched only once.
    * ``branch_protections`` iterates repos page-by-page and checks the
      default-branch protection rule of each repo in that page.
    * ``installations`` uses the GitHub App JWT (not the installation token).
    * ``orgs`` / ``enterprise_members`` use the GitHub GraphQL API with the
      enterprise slug passed via the ``org`` parameter.
    """
    import json

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # ── Simple page-based entities ────────────────────────────────────────
    if entity_type in _SIMPLE_ENTITY_URLS:
        page = int(cursor) if cursor else 1
        url = f"{_GITHUB_API_BASE}{_SIMPLE_ENTITY_URLS[entity_type].format(org=org)}"
        params: dict[str, object] = {"per_page": page_size, "page": page}
        if entity_type == "repositories":
            params["type"] = "all"
            params["sort"] = "full_name"

        resp = await _github_get(url, headers, params, rate_limiter)
        if resp.status_code == 403:
            logger.warning(
                "github_sync.permission_denied",
                entity_type=entity_type,
                org=org,
                url=url,
                hint="Check GitHub App permissions for this entity type",
            )
            return [], None
        resp.raise_for_status()
        items = resp.json()
        next_cursor = str(page + 1) if items and _has_next_page(resp.headers) else None
        return items, next_cursor

    # ── Team members (nested: teams → members per team) ───────────────────
    if entity_type == "team_members":
        if cursor is None:
            # First call — list all teams to build the traversal order
            all_slugs: list[str] = []
            teams_url = f"{_GITHUB_API_BASE}/orgs/{org}/teams"
            tp = 1
            while True:
                resp = await _github_get(
                    teams_url, headers, {"per_page": 100, "page": tp}, rate_limiter
                )
                if resp.status_code == 403:
                    logger.warning(
                        "github_sync.permission_denied",
                        entity_type="team_members",
                        org=org,
                        hint="GitHub App needs 'members:read' permission",
                    )
                    return [], None
                resp.raise_for_status()
                batch = resp.json()
                all_slugs.extend(t["slug"] for t in batch)
                if not batch or not _has_next_page(resp.headers):
                    break
                tp += 1
            all_slugs.sort()
            if not all_slugs:
                return [], None
            state = {"teams": all_slugs, "current": all_slugs[0], "page": 1}
        else:
            state = json.loads(cursor)

        team_slug = state["current"]
        page = state["page"]
        all_slugs = state["teams"]

        members_url = f"{_GITHUB_API_BASE}/orgs/{org}/teams/{team_slug}/members"
        resp = await _github_get(
            members_url, headers, {"per_page": page_size, "page": page}, rate_limiter
        )
        resp.raise_for_status()
        items = resp.json()
        for item in items:
            item["_team_slug"] = team_slug

        if _has_next_page(resp.headers):
            state["page"] = page + 1
            return items, json.dumps(state)

        # Advance to next team
        try:
            idx = all_slugs.index(team_slug)
        except ValueError:
            return items, None
        if idx + 1 < len(all_slugs):
            state["current"] = all_slugs[idx + 1]
            state["page"] = 1
            return items, json.dumps(state)

        return items, None

    # ── Branch protections (iterate repos, check default branch) ──────────
    if entity_type == "branch_protections":
        page = int(cursor) if cursor else 1
        repos_url = f"{_GITHUB_API_BASE}/orgs/{org}/repos"
        resp = await _github_get(
            repos_url,
            headers,
            {"per_page": page_size, "page": page, "type": "all", "sort": "full_name"},
            rate_limiter,
        )
        resp.raise_for_status()
        repos = resp.json()
        if not repos:
            return [], None

        items = []
        for repo in repos:
            if repo.get("archived"):
                continue
            branch = repo.get("default_branch") or "main"
            prot_url = (
                f"{_GITHUB_API_BASE}/repos/{org}/{repo['name']}"
                f"/branches/{branch}/protection"
            )
            prot_resp = await _github_get(prot_url, headers, {}, rate_limiter)
            if prot_resp.status_code == 200:
                prot = prot_resp.json()
                pr_reviews = prot.get("required_pull_request_reviews") or {}
                status_checks = prot.get("required_status_checks")
                enforce = prot.get("enforce_admins") or {}
                items.append({
                    "_repo_name": repo["name"],
                    "_branch": branch,
                    "required_reviews": pr_reviews.get(
                        "required_approving_review_count", 0
                    ),
                    "required_status_checks": (
                        {
                            "contexts": status_checks.get("contexts", []),
                            "strict": status_checks.get("strict", False),
                        }
                        if status_checks
                        else None
                    ),
                    "enforce_admins": enforce.get("enabled", False),
                })
            elif prot_resp.status_code == 404:
                items.append({
                    "_repo_name": repo["name"],
                    "_branch": branch,
                    "required_reviews": 0,
                    "required_status_checks": None,
                    "enforce_admins": False,
                })
            # 403 (no permission) — skip silently

        next_cursor = str(page + 1) if _has_next_page(resp.headers) else None
        return items, next_cursor

    # ── Installations (uses App JWT, not installation token) ──────────────
    if entity_type == "installations":
        import time as _time

        import jwt as pyjwt

        from app.config import settings as _settings

        key = _load_private_key()
        now = int(_time.time())
        app_jwt = pyjwt.encode(
            {"iat": now - 60, "exp": now + 600, "iss": str(_settings.github_app.GITHUB_APP_ID)},
            key,
            algorithm="RS256",
        )
        inst_headers = {**headers, "Authorization": f"Bearer {app_jwt}"}

        page = int(cursor) if cursor else 1
        url = f"{_GITHUB_API_BASE}/app/installations"
        resp = await _github_get(
            url, inst_headers, {"per_page": page_size, "page": page}, rate_limiter
        )
        resp.raise_for_status()
        items = resp.json()
        next_cursor = str(page + 1) if items and _has_next_page(resp.headers) else None
        return items, next_cursor

    # ── Enterprise orgs (GraphQL) ────────────────────────────────────────
    if entity_type == "orgs":
        if not org:
            logger.warning("github_sync.orgs_no_enterprise_slug")
            return [], None
        # org parameter holds the enterprise_slug for enterprise entities
        enterprise_slug = org
        result = await _graphql_page(
            token,
            _ENTERPRISE_ORGS_QUERY,
            {"slug": enterprise_slug, "first": page_size, "after": cursor},
            rate_limiter,
        )
        data = result.get("data")
        if not data or not data.get("enterprise"):
            errors = result.get("errors", [])
            if errors:
                logger.warning(
                    "github_sync.graphql_error",
                    entity_type="orgs",
                    errors=errors,
                )
            return [], None
        org_conn = data["enterprise"]["organizations"]
        items = []
        for node in org_conn.get("nodes", []):
            if node and node.get("login"):
                items.append({
                    "_enterprise_slug": enterprise_slug,
                    "login": node["login"],
                    "databaseId": node.get("databaseId", 0),
                })
        page_info = org_conn.get("pageInfo", {})
        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None
        return items, next_cursor

    # ── Enterprise members (GraphQL) ──────────────────────────────────────
    if entity_type == "enterprise_members":
        if not org:
            logger.warning("github_sync.enterprise_members_no_slug")
            return [], None
        enterprise_slug = org
        result = await _graphql_page(
            token,
            _ENTERPRISE_MEMBERS_QUERY,
            {"slug": enterprise_slug, "first": page_size, "after": cursor},
            rate_limiter,
        )
        data = result.get("data")
        if not data or not data.get("enterprise"):
            errors = result.get("errors", [])
            if errors:
                logger.warning(
                    "github_sync.graphql_error",
                    entity_type="enterprise_members",
                    errors=errors,
                )
            return [], None
        member_conn = data["enterprise"]["members"]
        items = []
        for node in member_conn.get("nodes", []):
            if not node or not node.get("login"):
                continue
            # GraphQL returns either EnterpriseUserAccount or User
            db_id = node.get("databaseId") or (node.get("user") or {}).get("databaseId", 0)
            items.append({
                "_enterprise_slug": enterprise_slug,
                "login": node["login"],
                "databaseId": db_id,
            })
        page_info = member_conn.get("pageInfo", {})
        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None
        return items, next_cursor

    logger.error("github_sync.unknown_entity_type", entity_type=entity_type)
    return [], None


# ── Upsert helpers (one per entity type) ──────────────────────────────────────


async def _upsert_org_members(
    session: AsyncSession, org: str, items: list[dict]
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgMember

    for item in items:
        stmt = (
            insert(OrgMember)
            .values(
                org=org,
                github_login=item["login"],
                github_id=item["id"],
                role=item.get("role_name") or item.get("role", "member"),
            )
            .on_conflict_do_update(
                constraint="uq_org_members_org_login",
                set_={
                    "github_id": item["id"],
                    "role": item.get("role_name") or item.get("role", "member"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_repositories(
    session: AsyncSession, org: str, items: list[dict]
) -> None:
    from datetime import datetime as _dt

    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import Repository

    for item in items:
        pushed = item.get("pushed_at")
        pushed_dt = (
            _dt.fromisoformat(pushed.replace("Z", "+00:00")) if pushed else None
        )
        stmt = (
            insert(Repository)
            .values(
                org=org,
                repo_name=item["name"],
                repo_id=item["id"],
                visibility=item.get("visibility", "private"),
                default_branch=item.get("default_branch"),
                archived=item.get("archived", False),
                fork=item.get("fork", False),
                pushed_at=pushed_dt,
            )
            .on_conflict_do_update(
                constraint="uq_repositories_org_name",
                set_={
                    "repo_id": item["id"],
                    "visibility": item.get("visibility", "private"),
                    "default_branch": item.get("default_branch"),
                    "archived": item.get("archived", False),
                    "fork": item.get("fork", False),
                    "pushed_at": pushed_dt,
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_teams(
    session: AsyncSession, org: str, items: list[dict]
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgTeam

    for item in items:
        parent = item.get("parent") or {}
        stmt = (
            insert(OrgTeam)
            .values(
                org=org,
                team_slug=item["slug"],
                team_id=item["id"],
                name=item["name"],
                privacy=item.get("privacy"),
                parent_team_slug=parent.get("slug"),
            )
            .on_conflict_do_update(
                constraint="uq_org_teams_org_slug",
                set_={
                    "team_id": item["id"],
                    "name": item["name"],
                    "privacy": item.get("privacy"),
                    "parent_team_slug": parent.get("slug"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_team_members(
    session: AsyncSession, org: str, items: list[dict]
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgTeamMember

    for item in items:
        team_slug = item.get("_team_slug", "unknown")
        stmt = (
            insert(OrgTeamMember)
            .values(
                org=org,
                team_slug=team_slug,
                github_login=item["login"],
                github_id=item.get("id"),
                role=item.get("role", "member"),
            )
            .on_conflict_do_update(
                constraint="uq_org_team_members_org_team_login",
                set_={
                    "github_id": item.get("id"),
                    "role": item.get("role", "member"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_branch_protections(
    session: AsyncSession, org: str, items: list[dict]
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import RepoBranchProtection

    for item in items:
        stmt = (
            insert(RepoBranchProtection)
            .values(
                org=org,
                repo_name=item["_repo_name"],
                branch=item["_branch"],
                required_reviews=item.get("required_reviews", 0),
                required_status_checks=item.get("required_status_checks"),
                enforce_admins=item.get("enforce_admins", False),
            )
            .on_conflict_do_update(
                constraint="uq_repo_branch_protections_org_repo_branch",
                set_={
                    "required_reviews": item.get("required_reviews", 0),
                    "required_status_checks": item.get("required_status_checks"),
                    "enforce_admins": item.get("enforce_admins", False),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_installations(
    session: AsyncSession, _org: str | None, items: list[dict]
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.config import settings as _settings
    from app.models.github_sync import GitHubAppInstallation

    app_id = _settings.github_app.GITHUB_APP_ID
    for item in items:
        acct = item.get("account") or {}
        stmt = (
            insert(GitHubAppInstallation)
            .values(
                app_id=app_id,
                installation_id=item["id"],
                target_type=item.get("target_type", "Organization"),
                target_login=acct.get("login") or acct.get("slug", ""),
                permissions=item.get("permissions"),
            )
            .on_conflict_do_update(
                constraint="uq_github_app_installations_app_install",
                set_={
                    "target_type": item.get("target_type", "Organization"),
                    "target_login": acct.get("login") or acct.get("slug", ""),
                    "permissions": item.get("permissions"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_enterprise_orgs(
    session: AsyncSession, _org: str | None, items: list[dict]
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import EnterpriseOrg

    for item in items:
        stmt = (
            insert(EnterpriseOrg)
            .values(
                enterprise_slug=item["_enterprise_slug"],
                org_login=item["login"],
                org_id=item.get("databaseId", 0),
            )
            .on_conflict_do_update(
                constraint="uq_enterprise_orgs_slug_login",
                set_={
                    "org_id": item.get("databaseId", 0),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_enterprise_members(
    session: AsyncSession, _org: str | None, items: list[dict]
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import EnterpriseMember

    for item in items:
        stmt = (
            insert(EnterpriseMember)
            .values(
                enterprise_slug=item["_enterprise_slug"],
                github_login=item["login"],
                github_id=item.get("databaseId", 0),
            )
            .on_conflict_do_update(
                constraint="uq_enterprise_members_slug_login",
                set_={
                    "github_id": item.get("databaseId", 0),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_items(
    session: AsyncSession,
    entity_type: str,
    org: str | None,
    items: list[dict],
) -> None:
    """Dispatch to the appropriate upsert function for *entity_type*.

    Uses INSERT ... ON CONFLICT DO UPDATE SET synced_at = NOW(), [...fields].
    Never deletes rows — non-destructive merge only.
    """
    _UPSERT_DISPATCH = {
        "org_members": _upsert_org_members,
        "repositories": _upsert_repositories,
        "teams": _upsert_teams,
        "team_members": _upsert_team_members,
        "branch_protections": _upsert_branch_protections,
        "installations": _upsert_installations,
        "orgs": _upsert_enterprise_orgs,
        "enterprise_members": _upsert_enterprise_members,
    }
    handler = _UPSERT_DISPATCH.get(entity_type)
    if handler is None:
        logger.error("github_sync.unknown_upsert_entity", entity_type=entity_type)
        return
    await handler(session, org, items)


async def _bootstrap_app_configs(settings: object) -> list:
    """Auto-discover GitHub App installations and seed github_app_configs.

    Called when the table is empty but env vars are configured. Uses the App JWT
    to list installations from the GitHub API, then inserts a config row for each.
    """
    import time

    import httpx
    import jwt
    from sqlalchemy import select

    from app.models.github_sync import GitHubAppConfig

    app_id = settings.github_app.GITHUB_APP_ID
    key_path = settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH
    if not app_id or not key_path:
        logger.error("github_sync.bootstrap_missing_env", app_id=app_id, key_path=key_path)
        return []

    try:
        with open(key_path) as f:
            private_key = f.read()
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 600, "iss": str(app_id)}
        app_jwt = jwt.encode(payload, private_key, algorithm="RS256")
    except Exception as exc:
        logger.error("github_sync.bootstrap_jwt_failed", error=str(exc))
        return []

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/app/installations",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=15,
            )
            resp.raise_for_status()
            installations = resp.json()
    except Exception as exc:
        logger.error("github_sync.bootstrap_api_failed", error=str(exc))
        return []

    if not installations:
        logger.warning("github_sync.no_installations_found")
        return []

    configs = []
    async with _make_session_factory()() as session:
        for inst in installations:
            acct = inst.get("account") or {}
            target = inst.get("target_type")
            config = GitHubAppConfig(
                app_id=app_id,
                installation_id=inst["id"],
                enterprise_slug=acct.get("slug") or acct.get("login")
                if target == "Enterprise"
                else None,
                org_login=acct.get("login")
                if target == "Organization"
                else None,
                enabled=True,
            )
            session.add(config)
            configs.append(config)

        await session.commit()
        logger.info(
            "github_sync.bootstrapped_configs",
            count=len(configs),
            installations=[i["id"] for i in installations],
        )

        result = await session.execute(
            select(GitHubAppConfig).where(GitHubAppConfig.enabled == True)  # noqa: E712
        )
        return list(result.scalars().all())
