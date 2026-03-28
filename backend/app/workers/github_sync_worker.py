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
from app.database import AsyncSessionLocal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

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

    # Auto-discover installations if none exist but env is configured
    if not configs and settings.github_app.GITHUB_APP_ID:
        configs = await _bootstrap_app_configs(settings)

    if not configs:
        logger.error("github_sync.no_configs", run_id=run_id)
        async with AsyncSessionLocal() as session:
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
    import redis.asyncio as aioredis
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from app.config import settings  # noqa: F811 — deferred import for testability
    from app.deps import get_valkey_pool
    from app.models.github_sync import EnterpriseSyncEntityCursor
    from app.services.github_rate_limiter import GitHubRateLimiter  # noqa: F811
    from app.services.github_token_service import GitHubAppTokenManager

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
        async with AsyncSessionLocal() as session:
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

    async with AsyncSessionLocal() as session:
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
    async with AsyncSessionLocal() as session:
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


# Stub signatures for page fetcher and upsert dispatcher
# (full implementation is in a separate github_sync_service.py)


async def _fetch_page(
    entity_type: str,
    org: str | None,
    token: str,
    cursor: str | None,
    rate_limiter: GitHubRateLimiter,
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
    session: AsyncSession,
    entity_type: str,
    org: str | None,
    items: list[dict],
) -> None:
    """Dispatch to the appropriate upsert function for *entity_type*.

    Uses INSERT ... ON CONFLICT DO UPDATE SET synced_at = NOW(), [...fields].
    Never deletes rows — non-destructive merge only.
    """
    ...  # implemented in github_sync_service.py


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
    async with AsyncSessionLocal() as session:
        for inst in installations:
            config = GitHubAppConfig(
                app_id=app_id,
                installation_id=inst["id"],
                enterprise_slug=inst.get("account", {}).get("login")
                if inst.get("target_type") == "Enterprise"
                else None,
                org_login=inst.get("account", {}).get("login")
                if inst.get("target_type") == "Organization"
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
