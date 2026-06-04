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
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.services.github_etag_cache import GitHubETagCache
    from app.services.github_token_service import GitHubAppTokenManager
    from app.services.sync_api_metrics import SyncAPICallCounter

import httpx
import structlog
from celery import Task
from celery.result import AsyncResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.celery_app import celery_app


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


def _parse_gh_dt(value: object) -> datetime | None:
    """Parse a GitHub ISO-8601 timestamp string into a timezone-aware datetime.

    GitHub returns strings like ``"2025-09-08T13:59:42Z"``.  asyncpg requires
    actual ``datetime`` objects for TIMESTAMPTZ columns — passing the raw string
    raises ``DataError: expected a datetime.date or datetime.datetime instance``.

    Returns ``None`` when *value* is falsy so callers can use it directly in
    optional timestamp columns.
    """
    if not value:
        return None
    s = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


async def _write_sync_log(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    message: str,
    level: str = "info",
    entity_type: str | None = None,
    org: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Write a log entry for a sync run in its own transaction.

    This helper is resilient — it catches and logs exceptions so that a
    failed log write never crashes the sync itself.
    """
    try:
        from sqlalchemy import func, select

        from app.models.github_sync import SyncLogEntry

        run_uuid = uuid.UUID(run_id)
        async with session_factory() as session:
            # PostgreSQL forbids FOR UPDATE with aggregate functions.
            # A plain max() is sufficient here — concurrent log writes for
            # the same run_id are unlikely and a duplicate seq is harmless.
            result = await session.execute(
                select(func.coalesce(func.max(SyncLogEntry.seq), 0) + 1).where(
                    SyncLogEntry.run_id == run_uuid
                )
            )
            seq = result.scalar_one()
            entry = SyncLogEntry(
                run_id=run_uuid,
                seq=seq,
                level=level,
                message=message,
                entity_type=entity_type,
                org=org,
                details=details,
            )
            session.add(entry)
            await session.commit()
    except Exception as exc:
        logger.warning(
            "github_sync.log_write_failed",
            run_id=run_id,
            message=message,
            error=str(exc),
        )


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
    "outside_collaborators",
    "secret_scanning_alerts",
    "dependabot_alerts",
    "license_consumption",
    "code_scanning_alerts",
    "actions_workflows",
    "mfa_status",
    "audit_log",
    "repo_commits",
    "pull_requests",
    "workflow_runs",
    "issues",
    "deployments",
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
    return asyncio.run(_sync_entity_async(self, run_id, entity_type, org, installation_id, cursor))


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


@celery_app.task(
    name="app.workers.github_sync.run_post_sync_pipeline",
    bind=True,
    max_retries=0,
    queue="github_sync",
    soft_time_limit=3600,  # 1 hour
    time_limit=3900,
)
def run_post_sync_pipeline(self: Task, run_id: str) -> dict[str, object]:
    """Post-sync pipeline: dispatch detection rules + baseline computation.

    Fires automatically after a successful enterprise sync. Queries events
    from the last 30 days, batches them into groups of 500 event IDs, and
    dispatches ``run_detection_pipeline_task`` for each batch. After all
    detection batches are dispatched, triggers a rolling baseline
    recomputation.

    This task is fire-and-forget — it does not wait for detection or
    baseline tasks to complete.
    """
    return asyncio.run(_run_post_sync_pipeline_async(run_id))


# ── Internal async implementations ────────────────────────────────────────────


async def _cleanup_stale_runs(sf: async_sessionmaker[AsyncSession]) -> None:
    """Recover from worker restarts by finalizing runs stuck in 'running' for >3 hours.

    When the Celery container is SIGTERM'd, in-flight tasks are killed without
    cleanup. Cursor rows stay ``in_progress`` and the run stays ``running``
    forever. This helper detects those stale runs on orchestrator startup, marks
    their stuck cursors as ``failed``, then calls ``_maybe_finalize_run`` so the
    run transitions to ``failed`` (rather than staying ``running`` indefinitely).

    The 3-hour threshold is safe because entity tasks have a 1-hour soft limit
    and a 3 900-second hard limit, so no legitimate task should take >3 hours.
    """
    from sqlalchemy import select
    from sqlalchemy import update as sa_update

    from app.models.github_sync import EnterpriseSyncEntityCursor, EnterpriseSyncRun

    stale_threshold = datetime.now(UTC) - timedelta(hours=3)
    async with sf() as session:
        stale_result = await session.execute(
            select(EnterpriseSyncRun.id).where(
                EnterpriseSyncRun.status == "running",
                EnterpriseSyncRun.started_at < stale_threshold,
            )
        )
        stale_ids = [row[0] for row in stale_result.fetchall()]

    for run_uuid in stale_ids:
        run_id_str = str(run_uuid)
        async with sf() as session:
            await session.execute(
                sa_update(EnterpriseSyncEntityCursor)
                .where(
                    EnterpriseSyncEntityCursor.run_id == run_uuid,
                    EnterpriseSyncEntityCursor.status == "in_progress",
                )
                .values(status="failed")
            )
            await session.commit()
        await _write_sync_log(
            sf,
            run_id_str,
            "Marked stale in_progress cursors as failed (worker restart recovery)",
            level="error",
        )
        await _maybe_finalize_run(sf, run_id_str)


async def _run_enterprise_sync_async(run_id: str, scope: ScopeType) -> dict:
    """Async implementation of the orchestrator.  Called inside asyncio.run()."""
    from sqlalchemy import select, update

    from app.config import settings  # noqa: F811 — deferred import for testability
    from app.models.github_sync import EnterpriseSyncRun, GitHubAppConfig

    run_uuid = uuid.UUID(run_id)

    sf = _make_session_factory()

    # Recover any runs that were left stuck by a previous worker restart before
    # touching this run's state.
    await _cleanup_stale_runs(sf)

    async with sf() as session:
        # Refresh in-memory settings from DB (setup wizard stores credentials
        # in app_settings, not env vars).
        from app.services.config_overlay import refresh_settings

        await refresh_settings(session)

        # Mark run as started
        await session.execute(
            update(EnterpriseSyncRun)
            .where(EnterpriseSyncRun.id == run_uuid)
            .values(status="running", started_at=datetime.now(UTC))
        )
        await session.commit()

        # Load installation configs
        configs_result = await session.execute(
            select(GitHubAppConfig).where(GitHubAppConfig.enabled == True)  # noqa: E712
        )
        configs = configs_result.scalars().all()

    await _write_sync_log(sf, run_id, f"Starting enterprise sync (scope={scope})")

    # Auto-discover installations if none exist but env is configured
    if not configs and settings.github_app.GITHUB_APP_ID:
        configs = await _bootstrap_app_configs(settings)

    # Promote org-level installations discovered by a previous sync into
    # github_app_configs so the orchestrator uses the correct (org-scoped)
    # installation token for org-level API calls.
    if configs and settings.github_app.GITHUB_APP_ID:
        configs = await _sync_installation_configs(configs, settings)

    if not configs:
        logger.error("github_sync.no_configs", run_id=run_id)
        await _write_sync_log(sf, run_id, "No enabled GitHub App configs found", level="error")
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
    _ENTERPRISE_ENTITIES = {
        "orgs",
        "enterprise_members",
        "installations",
        "license_consumption",
        "audit_log",
    }
    _ORG_ENTITIES = {
        "org_members",
        "repositories",
        "teams",
        "team_members",
        "branch_protections",
        "outside_collaborators",
        "secret_scanning_alerts",
        "dependabot_alerts",
        "code_scanning_alerts",
        "actions_workflows",
        "mfa_status",
        "repo_commits",
        "pull_requests",
        "workflow_runs",
        "team_repos",
        "repo_collaborators",
        "credential_authorizations",
        "org_webhooks",
        "repo_webhooks",
        "actions_permissions",
        "self_hosted_runners",
        "deploy_keys",
        "issues",
        "deployments",
    }

    entity_types: list[str] = (
        list(_ENTERPRISE_ENTITIES | _ORG_ENTITIES) if scope == "full" else [scope]
    )

    # For enterprise installations (org_login is NULL), discover org names
    # from GITHUB_SYNC_ORGS env or from the installation's accessible repos.
    sync_orgs = settings.github_app.sync_orgs_list

    # Auto-discover orgs from enterprise GraphQL when an enterprise config exists.
    # This ensures all enterprise orgs are synced, not just those with explicit
    # org-level app installations.
    enterprise_slug = next((c.enterprise_slug for c in configs if c.enterprise_slug), None)
    if not sync_orgs and enterprise_slug:
        enterprise_config = next(c for c in configs if c.enterprise_slug)
        discovered = await _discover_orgs_from_installation(
            enterprise_config.installation_id, enterprise_slug
        )
        if discovered:
            sync_orgs = discovered
            logger.info("github_sync.auto_discovered_orgs", orgs=sync_orgs)

    # Separate enterprise and org configs for correct dispatch
    enterprise_configs = [c for c in configs if c.enterprise_slug and not c.org_login]
    org_configs = [c for c in configs if c.org_login]

    dispatched: list[tuple[str, str | None]] = []
    child_results: list[AsyncResult[dict[str, object]]] = []

    # Enterprise-level entities: use enterprise installation
    for config in enterprise_configs:
        for entity_type in entity_types:
            if entity_type not in _ENTERPRISE_ENTITIES:
                continue
            result = sync_entity.apply_async(
                kwargs={
                    "run_id": run_id,
                    "entity_type": entity_type,
                    "org": config.enterprise_slug,
                    "installation_id": config.installation_id,
                    "cursor": None,
                },
                queue="github_sync",
            )
            child_results.append(result)
            dispatched.append((entity_type, config.enterprise_slug))

    # Org-level entities: prefer org-specific installations (broader access),
    # fall back to enterprise installation + discovered orgs
    org_entity_types = [e for e in entity_types if e in _ORG_ENTITIES]
    dispatched_orgs: set[str] = set()

    for config in org_configs:
        for entity_type in org_entity_types:
            result = sync_entity.apply_async(
                kwargs={
                    "run_id": run_id,
                    "entity_type": entity_type,
                    "org": config.org_login,
                    "installation_id": config.installation_id,
                    "cursor": None,
                },
                queue="github_sync",
            )
            child_results.append(result)
            dispatched.append((entity_type, config.org_login))
        dispatched_orgs.add(config.org_login)

    # Log orgs that exist in the enterprise but don't have the app installed.
    # These orgs won't be synced — the user needs to install the app on them.
    if enterprise_configs and sync_orgs:
        uninstalled_orgs = [o for o in sync_orgs if o not in dispatched_orgs]
        if uninstalled_orgs:
            logger.info(
                "github_sync.orgs_missing_installation",
                count=len(uninstalled_orgs),
                orgs=uninstalled_orgs[:20],
                hint="Install the GitHub App on these orgs to enable sync",
            )
            msg = (
                f"{len(uninstalled_orgs)} org(s) skipped — app not installed: "
                f"{', '.join(uninstalled_orgs[:10])}"
            )
            if len(uninstalled_orgs) > 10:
                msg += f" (and {len(uninstalled_orgs) - 10} more)"
            await _write_sync_log(
                sf,
                run_id,
                msg,
                entity_type="orgs",
            )

    logger.info(
        "github_sync.orchestrator_dispatched",
        run_id=run_id,
        task_count=len(dispatched),
    )
    await _write_sync_log(
        sf,
        run_id,
        f"Dispatched {len(dispatched)} entity sync tasks",
        details={"tasks": [f"{et}:{o}" for et, o in dispatched]},
    )

    # Record the expected number of tasks so _maybe_finalize_run won't
    # finalize early (before every task has written its first cursor row).
    async with sf() as session:
        await session.execute(
            update(EnterpriseSyncRun)
            .where(EnterpriseSyncRun.id == run_uuid)
            .values(expected_entity_count=len(dispatched))
        )
        await session.commit()

    # If zero tasks were dispatched (no installed orgs), finalize the run now.
    if not dispatched:
        logger.info("github_sync.zero_dispatch", run_id=run_id)
        async with sf() as session:
            await session.execute(
                update(EnterpriseSyncRun)
                .where(EnterpriseSyncRun.id == run_uuid)
                .values(
                    status="completed",
                    completed_at=datetime.now(UTC),
                )
            )
            await session.commit()
        await _write_sync_log(
            sf,
            run_id,
            "No entity tasks dispatched — install the GitHub App on orgs to enable sync",
        )
        return {"status": "completed", "tasks": 0}

    # NOTE: The orchestrator does NOT wait for child tasks to complete.
    # With --pool=solo, waiting would deadlock (one thread, children queued behind us).
    # Instead, each sync_entity task checks if it's the last to finish and, if so,
    # marks the run as completed and triggers the post-sync pipeline.

    return {
        "status": "dispatched",
        "tasks": len(dispatched),
    }


async def _run_post_sync_pipeline_async(run_id: str) -> dict[str, object]:
    """Async implementation of the post-sync detection + baseline pipeline."""
    from sqlalchemy import select, update

    from app.models.audit_event import AuditEvent
    from app.models.github_sync import EnterpriseSyncRun

    run_uuid = uuid.UUID(run_id)
    sf = _make_session_factory()

    try:
        # Mark post-processing as running
        async with sf() as session:
            await session.execute(
                update(EnterpriseSyncRun)
                .where(EnterpriseSyncRun.id == run_uuid)
                .values(post_processing_status="running")
            )
            await session.commit()

        await _write_sync_log(sf, run_id, "Starting post-sync pipeline")

        # Query event IDs from the last 30 days
        cutoff = datetime.now(UTC) - timedelta(days=30)
        async with sf() as session:
            result = await session.execute(
                select(AuditEvent.id).where(AuditEvent.created_at >= cutoff).order_by(AuditEvent.id)
            )
            event_ids: list[int] = [row[0] for row in result.fetchall()]

        # Batch event IDs and dispatch detection pipeline tasks
        from app.workers.detection_worker import run_detection_pipeline_task

        batch_size = 500
        detection_batches = 0
        for i in range(0, len(event_ids), batch_size):
            batch = event_ids[i : i + batch_size]
            run_detection_pipeline_task.apply_async(
                args=[batch],
                queue="detection",
            )
            detection_batches += 1

        await _write_sync_log(
            sf,
            run_id,
            f"Dispatched {detection_batches} detection batches for {len(event_ids)} events",
        )

        # Dispatch rolling baseline computation
        from app.workers.baseline_worker import compute_rolling_baselines_task

        compute_rolling_baselines_task.apply_async(queue="baseline")

        await _write_sync_log(sf, run_id, "Baseline computation triggered")

        # Run posture assessment against synced metadata
        await _write_sync_log(sf, run_id, "Running posture assessment...")
        from app.services.detection_service import run_posture_assessment

        async with sf() as session:
            posture_count = await run_posture_assessment(session, run_id=run_id)
            await session.commit()

        await _write_sync_log(
            sf,
            run_id,
            f"Posture assessment complete: {posture_count} finding(s)",
        )

        # Mark post-processing as completed
        async with sf() as session:
            await session.execute(
                update(EnterpriseSyncRun)
                .where(EnterpriseSyncRun.id == run_uuid)
                .values(post_processing_status="completed")
            )
            await session.commit()

        logger.info(
            "github_sync.post_sync_pipeline_completed",
            run_id=run_id,
            event_count=len(event_ids),
            detection_batches=detection_batches,
        )
        await _write_sync_log(
            sf,
            run_id,
            "Post-sync pipeline completed — detections and baselines updated",
        )

        return {
            "status": "completed",
            "event_count": len(event_ids),
            "detection_batches": detection_batches,
            "posture_findings": posture_count,
        }

    except Exception as exc:
        logger.error(
            "github_sync.post_sync_pipeline_failed",
            run_id=run_id,
            error=str(exc),
        )
        await _write_sync_log(
            sf,
            run_id,
            f"Post-sync pipeline failed: {exc}",
            level="error",
        )
        # Attempt to mark status as failed
        try:
            async with sf() as session:
                await session.execute(
                    update(EnterpriseSyncRun)
                    .where(EnterpriseSyncRun.id == run_uuid)
                    .values(post_processing_status="failed")
                )
                await session.commit()
        except Exception as update_exc:
            logger.error(
                "github_sync.post_sync_status_update_failed",
                run_id=run_id,
                error=str(update_exc),
            )
        return {
            "status": "failed",
            "error": str(exc),
        }


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
    sf = _make_session_factory()

    await _write_sync_log(
        sf,
        run_id,
        f"Starting sync for {entity_type}",
        entity_type=entity_type,
        org=org,
    )

    # ── Read or initialise cursor ──────────────────────────────────────────
    async with sf() as session:
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

    # ── Delta sync: determine cutoff for scheduled runs ───────────────
    delta_since: datetime | None = None
    async with sf() as session:
        from app.models.github_sync import EnterpriseSyncRun

        run_row = await session.get(EnterpriseSyncRun, run_uuid)
        if run_row and run_row.trigger_type == "scheduled":
            # Find the most recent *completed* run before this one
            prev = await session.execute(
                select(EnterpriseSyncRun.completed_at)
                .where(
                    EnterpriseSyncRun.id != run_uuid,
                    EnterpriseSyncRun.status == "completed",
                    EnterpriseSyncRun.completed_at.isnot(None),
                )
                .order_by(EnterpriseSyncRun.completed_at.desc())
                .limit(1)
            )
            prev_completed = prev.scalar_one_or_none()
            if prev_completed is not None:
                delta_since = prev_completed

    # ── Set up clients ────────────────────────────────────────────────────
    # Create a fresh Valkey connection per task to avoid event-loop binding
    # issues (the module-level pool binds to the first loop and fails on
    # subsequent asyncio.run() calls).
    valkey = aioredis.Redis.from_url(settings.VALKEY_URL, decode_responses=True, max_connections=5)
    token_manager = GitHubAppTokenManager(
        app_id=settings.github_app.GITHUB_APP_ID,
        private_key_pem=_load_private_key(),
        valkey_client=valkey,
    )
    # Create a fresh rate limiter per task — the asyncio.Semaphore inside
    # binds to the current event loop and can't survive across asyncio.run()
    rate_limiter = GitHubRateLimiter(rate_per_hour=15_000, max_burst=50, max_concurrent=80)

    # ETag cache for conditional requests — reduces rate-limit consumption
    from app.services.github_etag_cache import GitHubETagCache

    etag_cache = GitHubETagCache(valkey_client=valkey)

    # API call counter for metrics/observability
    from app.services.sync_api_metrics import SyncAPICallCounter

    api_counter = SyncAPICallCounter(run_id=run_id, entity_type=entity_type)

    # ── Resolve enterprise PAT for audit_log entity ───────────────────────
    # The audit log API requires a classic PAT with admin:enterprise scope;
    # GitHub App installation tokens get 403.  Retrieve the stored PAT from
    # app_settings and use it instead of the installation token.
    enterprise_pat: str | None = None
    if entity_type == "audit_log":
        from app.services.settings_service import get_setting as _get_setting

        async with _make_session_factory()() as pat_session:
            enterprise_pat = await _get_setting(pat_session, "enterprise_pat")
        if enterprise_pat:
            logger.info(
                "github_sync.audit_log_using_enterprise_pat",
                entity_type=entity_type,
                org=org,
            )
        else:
            logger.warning(
                "github_sync.audit_log_no_enterprise_pat",
                entity_type=entity_type,
                org=org,
                hint="Configure a classic PAT with admin:enterprise scope "
                "in Settings → GitHub → Classic PAT to sync audit logs.",
            )

    try:
        # ── Paginate and upsert ───────────────────────────────────────────
        current_cursor = resume_cursor
        page_num = 0
        while True:
            # Use enterprise PAT for audit_log, installation token otherwise
            if entity_type == "audit_log" and enterprise_pat:
                token = enterprise_pat
            else:
                token = await token_manager.get_installation_token(installation_id)
            items, next_cursor = await _fetch_page(
                entity_type=entity_type,
                org=org,
                token=token,
                cursor=current_cursor,
                rate_limiter=rate_limiter,
                delta_since=delta_since,
                etag_cache=etag_cache,
                api_counter=api_counter,
            )
            if not items:
                break

            async with _make_session_factory()() as session:
                await _upsert_items(session, entity_type, org, items, delta_since=delta_since)
                # Aggregate entities (code_scanning, secret_scanning, dependabot) wrap all
                # individual alerts in a single summary dict with a "_raw_alerts" key.
                # Use the actual alert count so the cursor reflects reality, not just "1".
                raw_alert_count = sum(
                    len(item.get("_raw_alerts") or [])
                    for item in items
                    if isinstance(item, dict) and "_raw_alerts" in item
                )
                items_synced += raw_alert_count if raw_alert_count else len(items)

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
            await _write_sync_log(
                sf,
                run_id,
                f"Fetched page {page_num + 1} ({len(items)} items, {items_synced} total)",
                entity_type=entity_type,
                org=org,
            )

            if not next_cursor:
                break
            current_cursor = next_cursor
            page_num += 1

        # Mark cursor as completed after the pagination loop finishes
        async with _make_session_factory()() as session:
            stmt = (
                insert(EnterpriseSyncEntityCursor)
                .values(
                    run_id=run_uuid,
                    entity_type=entity_type,
                    org=org,
                    last_cursor=current_cursor,
                    items_synced=items_synced,
                    status="completed",
                )
                .on_conflict_do_update(
                    constraint="uq_sync_cursors_run_entity_org",
                    set_={
                        "last_cursor": current_cursor,
                        "items_synced": items_synced,
                        "status": "completed",
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()

        # Clean up stale branch protection rows for repos that lost protection
        if entity_type == "branch_protections" and items_synced == 0 and org:
            from sqlalchemy import delete as sa_delete

            from app.models.github_sync import RepoBranchProtection

            async with _make_session_factory()() as session:
                result = await session.execute(
                    sa_delete(RepoBranchProtection).where(RepoBranchProtection.org == org)
                )
                if result.rowcount:
                    await _write_sync_log(
                        sf,
                        run_id,
                        f"Removed {result.rowcount} stale branch protection record(s)",
                        entity_type=entity_type,
                        org=org,
                    )
                await session.commit()

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
                    last_cursor=(current_cursor if "current_cursor" in dir() else initial_cursor),
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
        await _write_sync_log(
            sf,
            run_id,
            f"Failed to sync {entity_type}: {exc}",
            level="error",
            entity_type=entity_type,
            org=org,
        )
        try:
            backoff = min(30 * (2**task.request.retries), 600)
            jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
            raise task.retry(exc=exc, countdown=backoff + jitter) from exc
        except task.MaxRetriesExceededError:
            # Retries exhausted — check if this was the last entity
            await _maybe_finalize_run(sf, run_id)
            raise

    else:
        # No exception — enrich org settings while valkey is still open
        if entity_type == "orgs":
            try:
                # Find org-level installations that have administration:read
                from sqlalchemy import select as sa_select

                from app.models.github_sync import GitHubAppInstallation

                org_inst_map: dict[str, int] = {}
                async with sf() as session:
                    inst_result = await session.execute(
                        sa_select(GitHubAppInstallation).where(
                            GitHubAppInstallation.target_type == "Organization",
                        )
                    )
                    for inst in inst_result.scalars().all():
                        perms = inst.permissions or {}
                        if perms.get("administration") in ("read", "write"):
                            org_inst_map[inst.target_login] = inst.installation_id

                enriched = await _enrich_org_settings(
                    sf,
                    run_id,
                    token_manager,
                    rate_limiter,
                    org_inst_map,
                    fallback_installation_id=installation_id,
                )
                await _write_sync_log(
                    sf,
                    run_id,
                    f"Enriched security settings for {enriched} org(s)",
                    entity_type="orgs",
                )
            except Exception as enrich_exc:
                logger.warning(
                    "github_sync.org_enrich_error",
                    error=str(enrich_exc),
                )

    finally:
        await valkey.aclose()

    # Log API call metrics for this entity sync
    api_counter.log_summary()
    metrics = api_counter.summary()

    await _write_sync_log(
        sf,
        run_id,
        (
            f"Completed {entity_type}: {items_synced} items synced"
            f" ({metrics['total_api_calls']} API calls,"
            f" {metrics['cache_hits_304']} cache hits,"
            f" {metrics['cache_hit_rate_pct']}% hit rate)"
        ),
        entity_type=entity_type,
        org=org,
        details={"api_metrics": metrics},
    )

    # ── Check if this is the last entity to finish; if so, finalize the run ──
    await _maybe_finalize_run(sf, run_id)

    return {
        "status": "completed",
        "entity_type": entity_type,
        "org": org,
        "items": items_synced,
    }


async def _maybe_finalize_run(sf: async_sessionmaker[AsyncSession], run_id: str) -> None:
    """Check if all entity cursors for this run are terminal. If so, mark run completed.

    Finalization requires BOTH conditions to be true:
    1. The number of existing cursor rows is >= ``expected_entity_count`` (so we
       know every dispatched task has registered itself by writing its first page).
    2. Every one of those cursor rows is in a terminal state (``completed`` or
       ``failed``).

    When ``expected_entity_count`` is NULL (runs created before the column was
    added), we fall back to the original behavior: finalize as soon as all
    *existing* cursors are terminal — preserving backward compatibility.
    """
    from sqlalchemy import select
    from sqlalchemy import update as sa_update

    from app.models.github_sync import EnterpriseSyncEntityCursor, EnterpriseSyncRun

    run_uuid = uuid.UUID(run_id)

    async with sf() as session:
        # Load the run to read expected_entity_count
        run_result = await session.execute(
            select(EnterpriseSyncRun).where(EnterpriseSyncRun.id == run_uuid)
        )
        run = run_result.scalar_one_or_none()
        if run is None or run.status != "running":
            return

        expected_count: int | None = run.expected_entity_count

        # Count total cursors and completed/failed cursors for this run
        all_cursors = await session.execute(
            select(EnterpriseSyncEntityCursor).where(EnterpriseSyncEntityCursor.run_id == run_uuid)
        )
        cursors = all_cursors.scalars().all()
        if not cursors:
            return  # No cursors yet — orchestrator hasn't finished dispatching

        # Guard 1 (new behavior): wait until all dispatched tasks have shown up.
        if expected_count is not None and len(cursors) < expected_count:
            return  # Some tasks haven't created their cursor rows yet

        terminal = [c for c in cursors if c.status in ("completed", "failed")]
        if len(terminal) < len(cursors):
            return  # Still in-progress entities

        # All entities are done — finalize the run
        entity_counts: dict[str, int] = {}
        failed_entities: list[str] = []
        for c in cursors:
            if c.status == "completed":
                entity_counts[c.entity_type] = entity_counts.get(c.entity_type, 0) + c.items_synced
            else:
                failed_entities.append(f"{c.entity_type}:{c.org or 'global'}")

        has_failures = len(failed_entities) > 0
        final_status = "failed" if has_failures else "completed"
        error_msg = f"Failed entities: {', '.join(failed_entities)}" if has_failures else None

        # Atomic claim: only the first caller to finalize succeeds
        result = await session.execute(
            sa_update(EnterpriseSyncRun)
            .where(
                EnterpriseSyncRun.id == run_uuid,
                EnterpriseSyncRun.status == "running",
            )
            .values(
                status=final_status,
                completed_at=datetime.now(UTC),
                entity_counts=entity_counts or None,
                error_message=error_msg,
                post_processing_status=("pending" if final_status == "completed" else None),
            )
        )
        await session.commit()

    # If no row was updated, another task already finalized — bail out
    if result.rowcount == 0:
        return

    if has_failures:
        await _write_sync_log(
            sf,
            run_id,
            f"Sync completed with failures: {', '.join(failed_entities)}",
            level="error",
            details={"failed_entities": failed_entities, "entity_counts": entity_counts},
        )
    else:
        total_items = sum(entity_counts.values()) if entity_counts else 0
        await _write_sync_log(
            sf,
            run_id,
            f"All entity tasks completed — {total_items} total items synced",
            details={"entity_counts": entity_counts},
        )

    # Dispatch post-sync pipeline if successful
    if final_status == "completed":
        run_post_sync_pipeline.apply_async(
            kwargs={"run_id": run_id},
            queue="github_sync",
        )
        logger.info("github_sync.post_sync_pipeline_dispatched", run_id=run_id)
        await _write_sync_log(sf, run_id, "Post-sync pipeline dispatched")


async def _check_sync_schedule_async() -> dict:
    """Async implementation of the daily heartbeat schedule check.

    Reads schedule configuration from the ``app_settings`` table (keys
    ``sync_schedule_enabled``, ``sync_schedule_interval_hours``,
    ``sync_schedule_scope``).  Falls back to the legacy env-var-based
    ``GITHUB_SYNC_ENABLED`` / ``GITHUB_SYNC_INTERVAL_DAYS`` when no DB
    settings exist.
    """
    from sqlalchemy import select

    from app.config import settings  # noqa: F811 — deferred import for testability
    from app.models.github_sync import EnterpriseSyncRun
    from app.services.settings_service import get_setting

    # --- Read schedule config from DB, with env-var fallback ----------------
    async with _make_session_factory()() as session:
        db_enabled = await get_setting(session, "sync_schedule_enabled")
        db_interval = await get_setting(session, "sync_schedule_interval_hours")
        db_scope = await get_setting(session, "sync_schedule_scope")

    if db_enabled is not None:
        schedule_enabled = db_enabled.lower() == "true"
    else:
        schedule_enabled = settings.github_app.GITHUB_SYNC_ENABLED

    if not schedule_enabled:
        logger.debug("github_sync.schedule_check_skipped", reason="sync_disabled")
        return {"status": "skipped", "reason": "sync_disabled"}

    if db_interval is not None:
        interval = timedelta(hours=int(db_interval))
    else:
        interval = timedelta(days=settings.github_app.GITHUB_SYNC_INTERVAL_DAYS)

    scope: str = db_scope if db_scope is not None else "full"

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

    now = datetime.now(UTC)

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
            scope=scope,
        )
        session.add(run)
        await session.commit()

    run_enterprise_sync.apply_async(
        kwargs={"run_id": str(run_id), "scope": scope},
        queue="github_sync",
    )

    logger.info("github_sync.schedule_triggered", run_id=str(run_id), scope=scope)
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
    import httpx
    import redis.asyncio as aioredis

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
            async with httpx.AsyncClient(follow_redirects=True) as client:
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
    rate_limiter: GitHubRateLimiter | None = None,
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
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(_GRAPHQL_URL, json=payload, headers=headers, timeout=30)
        if rate_limiter is not None:
            rate_limiter.update_from_headers(resp.headers)
    finally:
        if rate_limiter is not None:
            rate_limiter.release()

    _is_rate_limited = resp.status_code == 429 or (
        resp.status_code == 403
        and (
            "rate limit" in resp.text.lower()
            or "abuse" in resp.text.lower()
            or resp.headers.get("retry-after")
        )
    )
    if _is_rate_limited and rate_limiter is not None:
        await rate_limiter.handle_rate_limit_response(resp)
        # Caller should retry
        return {"data": None, "errors": [{"message": "rate_limited"}]}

    resp.raise_for_status()
    return resp.json()


async def _graphql_list_enterprise_orgs(token: str, enterprise_slug: str) -> list[str]:
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
    """Load GitHub App private key PEM from the vault or filesystem.

    Prefers inline PEM from the config overlay (vault), falls back to
    the filesystem path.
    """
    from app.config import settings  # noqa: F811 — deferred import for testability

    key = settings.github_app.resolve_private_key()
    if not key:
        raise RuntimeError("GitHub App private key is not configured (neither PEM nor PATH)")
    return key


# ── GitHub API base URL (hardcoded to prevent SSRF) ───────────────────────────

_GITHUB_API_BASE = "https://api.github.com"

# Simple entity type → REST API path mapping (page-based pagination)
_SIMPLE_ENTITY_URLS: dict[str, str] = {
    "org_members": "/orgs/{org}/members",
    "repositories": "/orgs/{org}/repos",
    "teams": "/orgs/{org}/teams",
    "outside_collaborators": "/orgs/{org}/outside_collaborators",
    "credential_authorizations": "/orgs/{org}/credential-authorizations",
    "org_webhooks": "/orgs/{org}/hooks",
}


async def _github_get(
    url: str,
    headers: dict[str, str],
    params: dict[str, object],
    rate_limiter: GitHubRateLimiter,
    *,
    max_retries: int = 3,
    etag_cache: GitHubETagCache | None = None,
    api_counter: SyncAPICallCounter | None = None,
    entity_type: str | None = None,
) -> httpx.Response:
    """Rate-limited GET with automatic retry on 429/403 rate limit responses.

    When *etag_cache* is provided, the function:
    1. Sends ``If-None-Match`` with any cached ETag for the URL.
    2. Sends ``If-Modified-Since`` with any cached Last-Modified value.
    3. On ``304 Not Modified``, returns a synthetic 200 response with cached body.
    4. On ``200 OK`` with an ETag/Last-Modified header, stores for next time.

    When *api_counter* is provided, each API call and cache hit is recorded
    for metrics/observability.
    """
    from app.services.github_etag_cache import CachedResponse

    # Build the full URL with params for cache-key purposes
    request_url = (
        str(httpx.URL(url, params={k: str(v) for k, v in params.items()})) if params else url
    )

    # Inject conditional request headers when we have cached values
    req_headers = dict(headers)
    cached_etag: str | None = None
    cached_last_modified: str | None = None
    if etag_cache is not None:
        cached_etag = await etag_cache.get_etag(request_url)
        if cached_etag is not None:
            req_headers["If-None-Match"] = cached_etag
        # Also try If-Modified-Since for endpoints that support it
        cached_last_modified = await etag_cache.get_last_modified(request_url)
        if cached_last_modified is not None and cached_etag is None:
            req_headers["If-Modified-Since"] = cached_last_modified

    resp: httpx.Response | None = None
    for _attempt in range(max_retries):
        await rate_limiter.acquire()
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, headers=req_headers, params=params, timeout=30)
            rate_limiter.update_from_headers(resp.headers)
        finally:
            rate_limiter.release()

        # Handle 304 Not Modified — return cached body as a synthetic response
        if resp.status_code == 304 and etag_cache is not None:
            etag_for_lookup = cached_etag or cached_last_modified or ""
            cached: CachedResponse | None = await etag_cache.handle_304(
                request_url, etag_for_lookup
            )
            if cached is not None:
                import json as _json

                if api_counter is not None:
                    api_counter.record_api_call(cache_hit=True)
                return httpx.Response(
                    status_code=200,
                    headers=resp.headers,
                    content=_json.dumps(cached.body).encode(),
                    request=resp.request,
                )
            # Cache body missing — fall through to a normal request without conditionals
            req_headers.pop("If-None-Match", None)
            req_headers.pop("If-Modified-Since", None)
            continue

        _is_rate_limited = resp.status_code == 429 or (
            resp.status_code == 403
            and (
                "rate limit" in resp.text.lower()
                or "abuse" in resp.text.lower()
                or resp.headers.get("retry-after")
            )
        )
        if _is_rate_limited:
            await rate_limiter.handle_rate_limit_response(resp)
            continue

        # Record a non-cached API call
        if api_counter is not None:
            api_counter.record_api_call(cache_hit=False)

        # On success, cache the ETag/Last-Modified and response body
        if resp.status_code == 200 and etag_cache is not None:
            response_etag = resp.headers.get("etag")
            if response_etag:
                await etag_cache.store(
                    request_url, response_etag, resp.json(), entity_type=entity_type
                )
            else:
                # Fall back to Last-Modified caching for endpoints without ETags
                last_modified = resp.headers.get("last-modified")
                if last_modified:
                    await etag_cache.store_last_modified(
                        request_url, last_modified, resp.json(), entity_type=entity_type
                    )

        return resp

    assert resp is not None
    return resp


def _has_next_page(headers: httpx.Headers | dict[str, str]) -> bool:
    return 'rel="next"' in (headers.get("link") or "")


async def _enrich_prs_with_linked_issues(
    items: list[dict],
    token: str,
    rate_limiter: GitHubRateLimiter,
) -> None:
    """Best-effort: enrich merged PR items with linked issue data via GraphQL.

    Mutates *items* in-place — updates the ``data`` JSON string to include
    a ``linked_issues`` array.  On any GraphQL error the items retain their
    empty ``linked_issues`` lists and the sync is not interrupted.
    """
    import json as _json

    BATCH_SIZE = 25

    # Group items by (org, repo_name) and pr number for query building
    merged_items = [i for i in items if i.get("action") == "pull_request.merged"]
    if not merged_items:
        return

    for batch_start in range(0, len(merged_items), BATCH_SIZE):
        batch = merged_items[batch_start : batch_start + BATCH_SIZE]

        # Build aliased GraphQL query
        fragments = []
        alias_map: dict[str, dict] = {}  # alias -> item
        for idx, item in enumerate(batch):
            repo_full = item.get("repo", "")
            parts = repo_full.split("/", 1)
            if len(parts) != 2:
                continue
            owner, repo_name = parts
            data_dict = _json.loads(item["data"])
            pr_num = data_dict.get("number")
            if not pr_num:
                continue

            alias = f"pr{idx}"
            alias_map[alias] = item
            fragments.append(
                f'{alias}: repository(owner: "{owner}", name: "{repo_name}") {{\n'
                f"  pullRequest(number: {pr_num}) {{\n"
                f"    closingIssuesReferences(first: 10) {{\n"
                f"      nodes {{ number createdAt repository {{ nameWithOwner }} }}\n"
                f"    }}\n"
                f"  }}\n"
                f"}}"
            )

        if not fragments:
            continue

        query = "query LinkedIssues {\n" + "\n".join(fragments) + "\n}"

        try:
            result = await _graphql_page(
                token,
                query,
                {},
                rate_limiter=rate_limiter,
            )
        except Exception:
            logger.warning("github_sync.linked_issues_graphql_failed", batch_size=len(batch))
            continue

        if not result or not result.get("data"):
            continue

        data = result["data"]
        for alias, item in alias_map.items():
            pr_data = (data.get(alias) or {}).get("pullRequest")
            if not pr_data:
                continue
            refs = (pr_data.get("closingIssuesReferences") or {}).get("nodes") or []
            linked = []
            for node in refs:
                linked.append(
                    {
                        "number": node.get("number"),
                        "created_at": node.get("createdAt"),
                        "repo": ((node.get("repository") or {}).get("nameWithOwner", "")),
                    }
                )
            if linked:
                item_data = _json.loads(item["data"])
                item_data["linked_issues"] = linked
                item["data"] = _json.dumps(item_data)


async def _fetch_page(
    entity_type: str,
    org: str | None,
    token: str,
    cursor: str | None,
    rate_limiter: GitHubRateLimiter,
    page_size: int = 100,
    delta_since: datetime | None = None,
    etag_cache: GitHubETagCache | None = None,
    api_counter: SyncAPICallCounter | None = None,
) -> tuple[list[dict], str | None]:
    """Fetch one page of *entity_type* from the GitHub API.

    Returns ``(items, next_cursor)``.  ``next_cursor`` is ``None`` when there
    are no more pages.

    Parameters
    ----------
    delta_since
        When set (for scheduled delta syncs), fetch_page handlers may apply
        time-based filters to skip data that hasn't changed since the given
        timestamp.

    api_counter
        Optional :class:`SyncAPICallCounter` for tracking API call metrics.

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
            if delta_since is not None:
                # Delta mode: sort by push date descending so we can stop early
                params["type"] = "all"
                params["sort"] = "pushed"
                params["direction"] = "desc"
            else:
                params["type"] = "all"
                params["sort"] = "full_name"

        resp = await _github_get(
            url,
            headers,
            params,
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
        )
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

        # Delta optimization for repos: stop when items are older than cutoff
        if entity_type == "repositories" and delta_since is not None and items:
            cutoff_iso = delta_since.isoformat()
            filtered: list[dict] = []
            stop = False
            for item in items:
                pushed_at = item.get("pushed_at") or ""
                if pushed_at < cutoff_iso:
                    stop = True
                    break
                filtered.append(item)
            if stop or not _has_next_page(resp.headers):
                return filtered, None
            return filtered, str(page + 1)

        next_cursor = str(page + 1) if items and _has_next_page(resp.headers) else None
        return items, next_cursor

    # ── Team members (nested: teams → members per team) ───────────────────
    if entity_type == "team_members":
        if cursor is None:
            # Optimization: try to read team slugs from the database (populated
            # by the "teams" entity sync) to eliminate redundant API calls.
            all_slugs: list[str] = []
            try:
                from sqlalchemy import select as sa_select

                from app.models.github_sync import Team

                sf = _make_session_factory()
                async with sf() as db_session:
                    result = await db_session.execute(sa_select(Team.slug).where(Team.org == org))
                    all_slugs = sorted(row[0] for row in result.fetchall() if row[0])
            except Exception:
                all_slugs = []

            # Fall back to API if no teams in DB (first sync, or teams not synced yet)
            if not all_slugs:
                teams_url = f"{_GITHUB_API_BASE}/orgs/{org}/teams"
                tp = 1
                while True:
                    resp = await _github_get(
                        teams_url,
                        headers,
                        {"per_page": 100, "page": tp},
                        rate_limiter,
                        etag_cache=etag_cache,
                        api_counter=api_counter,
                        entity_type=entity_type,
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
            members_url,
            headers,
            {"per_page": page_size, "page": page},
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
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
        repo_params: dict[str, object] = {
            "per_page": page_size,
            "page": page,
            "type": "all",
        }
        if delta_since is not None:
            # Delta mode: sort by push date descending so we can focus on
            # recently-updated repos only.  Protection changes typically
            # coincide with repo activity (pushes, settings changes).
            repo_params["sort"] = "pushed"
            repo_params["direction"] = "desc"
        else:
            repo_params["sort"] = "full_name"
        resp = await _github_get(
            repos_url,
            headers,
            repo_params,
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
        )
        resp.raise_for_status()
        repos = resp.json()
        if not repos:
            return [], None

        items = []
        for repo in repos:
            if repo.get("archived"):
                continue
            # Delta optimisation: skip repos not pushed since the cutoff
            if delta_since is not None:
                pushed_at = repo.get("pushed_at") or ""
                if pushed_at < delta_since.isoformat():
                    # All remaining repos are older — stop early
                    return items, None
            branch = repo.get("default_branch") or "main"
            prot_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo['name']}/branches/{branch}/protection"
            prot_resp = await _github_get(
                prot_url,
                headers,
                {},
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if prot_resp.status_code == 200:
                prot = prot_resp.json()
                pr_reviews = prot.get("required_pull_request_reviews") or {}
                status_checks = prot.get("required_status_checks")
                enforce = prot.get("enforce_admins") or {}
                items.append(
                    {
                        "_repo_name": repo["name"],
                        "_branch": branch,
                        "required_reviews": pr_reviews.get("required_approving_review_count", 0),
                        "required_status_checks": (
                            {
                                "contexts": status_checks.get("contexts", []),
                                "strict": status_checks.get("strict", False),
                            }
                            if status_checks
                            else None
                        ),
                        "enforce_admins": enforce.get("enabled", False),
                    }
                )
            elif prot_resp.status_code == 404:
                # No branch protection — don't create a record.
                # The posture rule "missing_protection" detects repos
                # that have no corresponding row in repo_branch_protections.
                pass
            # 403 (no permission) — skip silently

        next_cursor = str(page + 1) if _has_next_page(resp.headers) else None
        return items, next_cursor

    # ── Repo commits (iterate repos, fetch recent commits per repo) ───────
    if entity_type == "repo_commits":
        cursor_data = json.loads(cursor) if cursor else {"repo_idx": 0, "page": 1}
        repo_idx: int = cursor_data["repo_idx"]
        page = cursor_data["page"]

        # Load all non-archived repos for the org from the database
        from sqlalchemy import select as sa_select

        from app.models.github_sync import Repository

        sf = _make_session_factory()
        async with sf() as db_session:
            result = await db_session.execute(
                sa_select(Repository.repo_name).where(
                    Repository.org == org,
                    Repository.archived == False,  # noqa: E712
                )
            )
            repo_names: list[str] = [row[0] for row in result.fetchall()]

        if not repo_names or repo_idx >= len(repo_names):
            return [], None

        items: list[dict] = []
        default_since = datetime.now(UTC) - timedelta(days=90)
        since_dt = delta_since or default_since

        while repo_idx < len(repo_names):
            repo_name = repo_names[repo_idx]
            commits_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/commits"
            params = {
                "per_page": page_size,
                "page": page,
                "since": since_dt.isoformat(),
            }

            resp = await _github_get(
                commits_url,
                headers,
                params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )

            if resp.status_code == 404:
                # Repo may have been deleted or made inaccessible — skip
                logger.debug("github_sync.repo_commits_404", org=org, repo=repo_name)
                repo_idx += 1
                page = 1
                continue
            if resp.status_code == 409:
                # Empty repository (no commits) — skip
                logger.debug("github_sync.repo_commits_empty", org=org, repo=repo_name)
                repo_idx += 1
                page = 1
                continue
            if resp.status_code == 403:
                logger.warning(
                    "github_sync.repo_commits_forbidden",
                    org=org,
                    repo=repo_name,
                )
                repo_idx += 1
                page = 1
                continue
            resp.raise_for_status()
            commits = resp.json()

            for c in commits:
                author_login = None
                author_id = None
                if c.get("author"):
                    author_login = c["author"].get("login")
                    author_id = c["author"].get("id")
                elif c.get("committer"):
                    author_login = c["committer"].get("login")
                    author_id = c["committer"].get("id")
                if not author_login:
                    author_login = (c.get("commit") or {}).get("author", {}).get("name")

                commit_date_str = (c.get("commit") or {}).get("author", {}).get(
                    "date"
                ) or datetime.now(UTC).isoformat()
                try:
                    commit_date = datetime.fromisoformat(commit_date_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    commit_date = datetime.now(UTC)

                sha = c.get("sha", "")
                message = ((c.get("commit") or {}).get("message") or "")[:500]

                items.append(
                    {
                        "action": "git.push",
                        "actor": author_login,
                        "actor_id": author_id,
                        "actor_is_bot": bool(author_login and str(author_login).endswith("[bot]")),
                        "org": org,
                        "repo": f"{org}/{repo_name}",
                        "created_at": commit_date,
                        "document_id": f"commit-{sha}",
                        "data": json.dumps(
                            {
                                "sha": sha,
                                "message": message,
                                "url": c.get("html_url", ""),
                            }
                        ),
                        "ingestion_source": "github_api_sync",
                        "source_file_path": f"api/{org}/{repo_name}/commits",
                    }
                )

            has_more = _has_next_page(resp.headers) and bool(commits)
            if has_more:
                # More pages for this repo — return current batch and continue
                next_cursor_data = {"repo_idx": repo_idx, "page": page + 1}
                return items, json.dumps(next_cursor_data)

            # Move to the next repo
            repo_idx += 1
            page = 1

        # All repos processed
        return items, None

    # ── Pull requests (iterate repos, fetch recent PRs per repo) ──────────
    if entity_type == "pull_requests":
        cursor_data = json.loads(cursor) if cursor else {"repo_idx": 0, "page": 1}
        repo_idx = cursor_data["repo_idx"]
        page = cursor_data["page"]

        from sqlalchemy import select as sa_select

        from app.models.github_sync import Repository

        sf = _make_session_factory()
        async with sf() as db_session:
            result = await db_session.execute(
                sa_select(Repository.repo_name).where(
                    Repository.org == org,
                    Repository.archived == False,  # noqa: E712
                )
            )
            repo_names = [row[0] for row in result.fetchall()]

        if not repo_names or repo_idx >= len(repo_names):
            return [], None

        items = []

        while repo_idx < len(repo_names):
            repo_name = repo_names[repo_idx]
            prs_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/pulls"
            params = {
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": page_size,
                "page": page,
            }

            resp = await _github_get(
                prs_url,
                headers,
                params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )

            if resp.status_code == 404:
                logger.debug("github_sync.pull_requests_404", org=org, repo=repo_name)
                repo_idx += 1
                page = 1
                continue
            if resp.status_code == 403:
                logger.warning(
                    "github_sync.pull_requests_forbidden",
                    org=org,
                    repo=repo_name,
                )
                repo_idx += 1
                page = 1
                continue
            resp.raise_for_status()
            prs = resp.json()

            # For initial sync (no delta_since), limit to 90 days of data
            default_cutoff = datetime.now(UTC) - timedelta(days=90)
            cutoff = delta_since or default_cutoff

            stop_early = False
            for pr in prs:
                # Delta sync: stop when PRs are older than the cutoff
                updated_at_str = pr.get("updated_at", "")
                if delta_since and updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                        if updated_at < cutoff:
                            stop_early = True
                            break
                    except (ValueError, AttributeError) as exc:
                        logger.debug(
                            "github_sync.pr_updated_at_parse_failed",
                            value=updated_at_str,
                            error=str(exc),
                        )

                # For initial sync, skip PRs with created_at older than 90 days
                if not delta_since:
                    created_at_str = pr.get("created_at", "")
                    if created_at_str:
                        try:
                            pr_created = datetime.fromisoformat(
                                created_at_str.replace("Z", "+00:00")
                            )
                            if pr_created < cutoff:
                                stop_early = True
                                break
                        except (ValueError, AttributeError) as exc:
                            logger.debug(
                                "github_sync.pr_created_at_parse_failed",
                                value=created_at_str,
                                error=str(exc),
                            )

                # Determine action from PR state
                merged = pr.get("merged_at") is not None or pr.get("merged", False)
                state = pr.get("state", "open")
                if merged:
                    action = "pull_request.merged"
                    action_suffix = "merged"
                elif state == "closed":
                    action = "pull_request.closed"
                    action_suffix = "closed"
                else:
                    action = "pull_request.opened"
                    action_suffix = "opened"

                # Pick the most relevant timestamp
                if merged and pr.get("merged_at"):
                    ts_str = pr["merged_at"]
                elif state == "closed" and pr.get("closed_at"):
                    ts_str = pr["closed_at"]
                else:
                    ts_str = pr.get("created_at", datetime.now(UTC).isoformat())

                try:
                    created_at = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    created_at = datetime.now(UTC)

                actor_login = (pr.get("user") or {}).get("login")
                actor_id = (pr.get("user") or {}).get("id")
                pr_number = pr.get("number", 0)

                items.append(
                    {
                        "action": action,
                        "actor": actor_login,
                        "actor_id": actor_id,
                        "actor_is_bot": bool(actor_login and str(actor_login).endswith("[bot]")),
                        "org": org,
                        "repo": f"{org}/{repo_name}",
                        "created_at": created_at,
                        "document_id": (f"pr-{org}/{repo_name}#{pr_number}-{action_suffix}"),
                        "data": json.dumps(
                            {
                                "number": pr_number,
                                "title": pr.get("title", ""),
                                "state": state,
                                "merged": merged,
                                "url": pr.get("html_url", ""),
                                "additions": pr.get("additions", 0),
                                "deletions": pr.get("deletions", 0),
                                "changed_files": pr.get("changed_files", 0),
                                "merge_commit_sha": pr.get("merge_commit_sha"),
                                "head_sha": (pr.get("head") or {}).get("sha"),
                                "head_ref": (pr.get("head") or {}).get("ref"),
                                "pr_created_at": pr.get("created_at"),
                                "linked_issues": [],
                            }
                        ),
                        "ingestion_source": "github_api_sync",
                        "source_file_path": f"api/{org}/{repo_name}/pulls",
                    }
                )

            if stop_early:
                # This repo's PRs are older than the cutoff — move to next repo
                repo_idx += 1
                page = 1
                if items:
                    try:
                        await _enrich_prs_with_linked_issues(items, token, rate_limiter)
                    except Exception:
                        logger.warning("github_sync.pr_enrichment_failed")
                    next_cursor = (
                        json.dumps({"repo_idx": repo_idx, "page": 1})
                        if repo_idx < len(repo_names)
                        else None
                    )
                    return items, next_cursor
                continue

            has_more = _has_next_page(resp.headers) and bool(prs)
            if has_more:
                next_cursor_data = {"repo_idx": repo_idx, "page": page + 1}
                if items:
                    try:
                        await _enrich_prs_with_linked_issues(items, token, rate_limiter)
                    except Exception:
                        logger.warning("github_sync.pr_enrichment_failed")
                return items, json.dumps(next_cursor_data)

            # Move to the next repo
            repo_idx += 1
            page = 1
            if items:
                try:
                    await _enrich_prs_with_linked_issues(items, token, rate_limiter)
                except Exception:
                    logger.warning("github_sync.pr_enrichment_failed")
                next_cursor = (
                    json.dumps({"repo_idx": repo_idx, "page": 1})
                    if repo_idx < len(repo_names)
                    else None
                )
                return items, next_cursor

        # Enrich merged PRs with linked issues (best-effort GraphQL)
        if items:
            try:
                await _enrich_prs_with_linked_issues(items, token, rate_limiter)
            except Exception:
                logger.warning("github_sync.pr_enrichment_failed")
        return items, None

    # ── Issues (iterate repos, fetch open & closed issues) ────────────────
    if entity_type == "issues":
        cursor_data = json.loads(cursor) if cursor else {"repo_idx": 0, "page": 1}
        repo_idx = cursor_data["repo_idx"]
        page = cursor_data["page"]

        from sqlalchemy import select as sa_select

        from app.models.github_sync import Repository

        sf = _make_session_factory()
        async with sf() as db_session:
            result = await db_session.execute(
                sa_select(Repository.repo_name).where(
                    Repository.org == org,
                    Repository.archived == False,  # noqa: E712
                )
            )
            repo_names = [row[0] for row in result.fetchall()]

        if not repo_names or repo_idx >= len(repo_names):
            return [], None

        items: list[dict] = []
        default_cutoff = datetime.now(UTC) - timedelta(days=90)
        cutoff = delta_since or default_cutoff

        while repo_idx < len(repo_names):
            repo_name = repo_names[repo_idx]
            issues_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/issues"
            params: dict[str, object] = {
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": page_size,
                "page": page,
            }
            if delta_since:
                params["since"] = delta_since.strftime("%Y-%m-%dT%H:%M:%SZ")

            resp = await _github_get(
                issues_url,
                headers,
                params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )

            if resp.status_code in (404, 403):
                logger.debug(
                    "github_sync.issues_skip",
                    org=org,
                    repo=repo_name,
                    status=resp.status_code,
                )
                repo_idx += 1
                page = 1
                continue
            resp.raise_for_status()
            issues_list = resp.json()

            stop_early = False
            for issue in issues_list:
                # Skip pull requests (GitHub issues endpoint includes them)
                if issue.get("pull_request"):
                    continue

                updated_at_str = issue.get("updated_at", "")
                if updated_at_str:
                    try:
                        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                        if updated_at < cutoff:
                            stop_early = True
                            break
                    except (ValueError, AttributeError):
                        pass

                state = issue.get("state", "open")
                if state == "closed":
                    action = "issue.closed"
                    ts_str = (
                        issue.get("closed_at") or issue.get("updated_at") or issue.get("created_at")
                    )
                else:
                    action = "issue.opened"
                    ts_str = issue.get("created_at")

                try:
                    created_at = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    created_at = datetime.now(UTC)

                actor = issue.get("user") or {}
                actor_login = actor.get("login")
                issue_number = issue.get("number", 0)

                items.append(
                    {
                        "action": action,
                        "actor": actor_login,
                        "actor_id": actor.get("id"),
                        "actor_is_bot": bool(actor_login and str(actor_login).endswith("[bot]")),
                        "org": org,
                        "repo": f"{org}/{repo_name}",
                        "created_at": created_at,
                        "document_id": f"issue-{org}/{repo_name}#{issue_number}-{state}",
                        "data": json.dumps(
                            {
                                "number": issue_number,
                                "title": issue.get("title", ""),
                                "state": state,
                                "state_reason": issue.get("state_reason"),
                                "url": issue.get("html_url", ""),
                                "labels": [lbl["name"] for lbl in (issue.get("labels") or [])],
                                "milestone": (issue.get("milestone") or {}).get("title"),
                                "assignees": [a["login"] for a in (issue.get("assignees") or [])],
                                "issue_created_at": issue.get("created_at"),
                                "closed_at": issue.get("closed_at"),
                                "user": {"login": actor_login, "id": actor.get("id")},
                            }
                        ),
                        "ingestion_source": "github_api_sync",
                        "source_file_path": f"api/{org}/{repo_name}/issues",
                    }
                )

            if stop_early:
                repo_idx += 1
                page = 1
                if items:
                    next_cursor = (
                        json.dumps({"repo_idx": repo_idx, "page": 1})
                        if repo_idx < len(repo_names)
                        else None
                    )
                    return items, next_cursor
                continue

            has_more = _has_next_page(resp.headers) and bool(issues_list)
            if has_more:
                return items, json.dumps({"repo_idx": repo_idx, "page": page + 1})

            repo_idx += 1
            page = 1
            if items:
                next_cursor = (
                    json.dumps({"repo_idx": repo_idx, "page": 1})
                    if repo_idx < len(repo_names)
                    else None
                )
                return items, next_cursor

        return items, None

    # ── Deployments + deployment statuses (iterate repos) ─────────────────
    if entity_type == "deployments":
        cursor_data = json.loads(cursor) if cursor else {"repo_idx": 0, "page": 1}
        repo_idx = cursor_data["repo_idx"]
        page = cursor_data["page"]

        from sqlalchemy import select as sa_select

        from app.models.github_sync import Repository

        sf = _make_session_factory()
        async with sf() as db_session:
            result = await db_session.execute(
                sa_select(Repository.repo_name).where(
                    Repository.org == org,
                    Repository.archived == False,  # noqa: E712
                )
            )
            repo_names = [row[0] for row in result.fetchall()]

        if not repo_names or repo_idx >= len(repo_names):
            return [], None

        items: list[dict] = []
        default_cutoff = datetime.now(UTC) - timedelta(days=90)
        cutoff = delta_since or default_cutoff

        while repo_idx < len(repo_names):
            repo_name = repo_names[repo_idx]
            deploys_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/deployments"
            params: dict[str, object] = {
                "per_page": page_size,
                "page": page,
            }

            resp = await _github_get(
                deploys_url,
                headers,
                params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )

            if resp.status_code in (404, 403):
                logger.debug(
                    "github_sync.deployments_skip",
                    org=org,
                    repo=repo_name,
                    status=resp.status_code,
                )
                repo_idx += 1
                page = 1
                continue
            resp.raise_for_status()
            deployments = resp.json()

            stop_early = False
            for deploy in deployments:
                deploy_created_str = deploy.get("created_at", "")
                try:
                    deploy_created = datetime.fromisoformat(
                        deploy_created_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    deploy_created = datetime.now(UTC)

                if deploy_created < cutoff:
                    stop_early = True
                    break

                creator = deploy.get("creator") or {}
                deploy_id = deploy.get("id", 0)
                repo_full = f"{org}/{repo_name}"

                items.append(
                    {
                        "action": "deployment.created",
                        "actor": creator.get("login"),
                        "actor_id": creator.get("id"),
                        "actor_is_bot": bool(
                            creator.get("login") and str(creator.get("login")).endswith("[bot]")
                        ),
                        "org": org,
                        "repo": repo_full,
                        "created_at": deploy_created,
                        "document_id": f"deployment-{repo_full}-{deploy_id}",
                        "data": json.dumps(
                            {
                                "deployment_id": deploy_id,
                                "environment": deploy.get("environment", ""),
                                "ref": deploy.get("ref", ""),
                                "sha": deploy.get("sha", ""),
                                "task": deploy.get("task", "deploy"),
                                "description": deploy.get("description"),
                                "url": deploy.get("html_url") or deploy.get("url", ""),
                                "creator": {
                                    "login": creator.get("login"),
                                    "id": creator.get("id"),
                                },
                            }
                        ),
                        "ingestion_source": "github_api_sync",
                        "source_file_path": f"api/{org}/{repo_name}/deployments",
                    }
                )

                # Fetch deployment statuses (nested, max 3 pages)
                for status_page in range(1, 4):
                    statuses_url = (
                        f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}"
                        f"/deployments/{deploy_id}/statuses"
                    )
                    status_params: dict[str, object] = {"per_page": 100, "page": status_page}
                    try:
                        status_resp = await _github_get(
                            statuses_url,
                            headers,
                            status_params,
                            rate_limiter,
                            etag_cache=etag_cache,
                            api_counter=api_counter,
                            entity_type=entity_type,
                        )
                    except Exception:
                        logger.debug("github_sync.deploy_status_fetch_failed", deploy_id=deploy_id)
                        break

                    if status_resp.status_code in (404, 403):
                        break
                    status_resp.raise_for_status()
                    statuses = status_resp.json()
                    if not statuses:
                        break

                    for dep_status in statuses:
                        status_creator = dep_status.get("creator") or {}
                        status_state = dep_status.get("state", "unknown")
                        status_ts_str = dep_status.get("created_at", "")
                        try:
                            status_ts = datetime.fromisoformat(status_ts_str.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            status_ts = datetime.now(UTC)

                        items.append(
                            {
                                "action": f"deployment_status.{status_state}",
                                "actor": status_creator.get("login"),
                                "actor_id": status_creator.get("id"),
                                "actor_is_bot": bool(
                                    status_creator.get("login")
                                    and str(status_creator.get("login")).endswith("[bot]")
                                ),
                                "org": org,
                                "repo": repo_full,
                                "created_at": status_ts,
                                "document_id": (
                                    f"deploy-status-{repo_full}"
                                    f"-{deploy_id}-{dep_status.get('id', 0)}"
                                ),
                                "data": json.dumps(
                                    {
                                        "deployment_id": deploy_id,
                                        "status_id": dep_status.get("id", 0),
                                        "environment": deploy.get("environment", ""),
                                        "state": status_state,
                                        "sha": deploy.get("sha", ""),
                                        "description": dep_status.get("description"),
                                        "environment_url": dep_status.get("environment_url"),
                                        "url": dep_status.get("url", ""),
                                        "creator": {
                                            "login": status_creator.get("login"),
                                            "id": status_creator.get("id"),
                                        },
                                    }
                                ),
                                "ingestion_source": "github_api_sync",
                                "source_file_path": (
                                    f"api/{org}/{repo_name}/deployments/{deploy_id}/statuses"
                                ),
                            }
                        )

                    if not _has_next_page(status_resp.headers):
                        break

            if stop_early:
                repo_idx += 1
                page = 1
                if items:
                    next_cursor = (
                        json.dumps({"repo_idx": repo_idx, "page": 1})
                        if repo_idx < len(repo_names)
                        else None
                    )
                    return items, next_cursor
                continue

            has_more = _has_next_page(resp.headers) and bool(deployments)
            if has_more:
                return items, json.dumps({"repo_idx": repo_idx, "page": page + 1})

            repo_idx += 1
            page = 1
            if items:
                next_cursor = (
                    json.dumps({"repo_idx": repo_idx, "page": 1})
                    if repo_idx < len(repo_names)
                    else None
                )
                return items, next_cursor

        return items, None

    # ── Workflow runs (iterate repos, fetch completed Actions runs) ────────
    if entity_type == "workflow_runs":
        cursor_data = json.loads(cursor) if cursor else {"repo_idx": 0, "page": 1}
        repo_idx = cursor_data["repo_idx"]
        page = cursor_data["page"]

        from sqlalchemy import select as sa_select

        from app.models.github_sync import Repository

        sf = _make_session_factory()
        async with sf() as db_session:
            result = await db_session.execute(
                sa_select(Repository.repo_name).where(
                    Repository.org == org,
                    Repository.archived == False,  # noqa: E712
                )
            )
            repo_names = [row[0] for row in result.fetchall()]

        if not repo_names or repo_idx >= len(repo_names):
            return [], None

        items: list[dict] = []
        default_since = datetime.now(UTC) - timedelta(days=90)
        since_dt = delta_since or default_since

        while repo_idx < len(repo_names):
            repo_name = repo_names[repo_idx]
            runs_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/actions/runs"
            params = {
                "per_page": page_size,
                "page": page,
                "status": "completed",
                "created": f">{since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            }

            resp = await _github_get(
                runs_url,
                headers,
                params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )

            if resp.status_code == 404:
                logger.debug("github_sync.workflow_runs_404", org=org, repo=repo_name)
                repo_idx += 1
                page = 1
                continue
            if resp.status_code == 403:
                logger.warning(
                    "github_sync.workflow_runs_forbidden",
                    org=org,
                    repo=repo_name,
                )
                repo_idx += 1
                page = 1
                continue
            resp.raise_for_status()
            runs_data = resp.json()
            runs = runs_data.get("workflow_runs", []) if isinstance(runs_data, dict) else []

            for run in runs:
                conclusion = run.get("conclusion") or "unknown"
                run_status = run.get("status", "")

                if run_status != "completed":
                    continue

                actor_login = None
                actor_id = None
                triggering_actor = run.get("triggering_actor") or run.get("actor")
                if triggering_actor:
                    actor_login = triggering_actor.get("login")
                    actor_id = triggering_actor.get("id")

                run_id = run.get("id", 0)
                run_created_str = run.get("created_at", "")
                run_started_str = run.get("run_started_at", "")
                updated_str = run.get("updated_at", "")

                try:
                    created_at = datetime.fromisoformat(run_created_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    created_at = datetime.now(UTC)

                duration_seconds = None
                if run_started_str and updated_str:
                    try:
                        started_dt = datetime.fromisoformat(run_started_str.replace("Z", "+00:00"))
                        updated_dt = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                        duration_seconds = (updated_dt - started_dt).total_seconds()
                    except (ValueError, AttributeError) as exc:
                        logger.debug(
                            "github_sync.workflow_run_duration_parse_failed",
                            run_started=run_started_str,
                            updated=updated_str,
                            error=str(exc),
                        )

                repo_full = f"{org}/{repo_name}"
                items.append(
                    {
                        "action": f"workflow_run.{conclusion}",
                        "actor": actor_login,
                        "actor_id": actor_id,
                        "actor_is_bot": bool(actor_login and str(actor_login).endswith("[bot]")),
                        "org": org,
                        "repo": repo_full,
                        "created_at": created_at,
                        "document_id": f"workflow-run-{repo_full}-{run_id}",
                        "data": json.dumps(
                            {
                                "workflow_name": run.get("name", ""),
                                "workflow_id": run.get("workflow_id", 0),
                                "run_number": run.get("run_number", 0),
                                "run_id": run_id,
                                "head_branch": run.get("head_branch", ""),
                                "event": run.get("event", ""),
                                "conclusion": conclusion,
                                "status": run_status,
                                "run_started_at": run_started_str,
                                "updated_at": updated_str,
                                "html_url": run.get("html_url", ""),
                                "duration_seconds": duration_seconds,
                                "head_sha": run.get("head_sha"),
                            }
                        ),
                        "ingestion_source": "github_api_sync",
                        "source_file_path": f"api/{org}/{repo_name}/actions/runs",
                    }
                )

            has_more = _has_next_page(resp.headers) and bool(runs)
            if has_more:
                next_cursor_data = {"repo_idx": repo_idx, "page": page + 1}
                return items, json.dumps(next_cursor_data)

            repo_idx += 1
            page = 1

        return items, None

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
            url,
            inst_headers,
            {"per_page": page_size, "page": page},
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
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
                error_msg = errors[0].get("message", "unknown")
                if error_msg == "rate_limited":
                    raise RuntimeError("GraphQL rate limited while fetching orgs — will retry")
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
                items.append(
                    {
                        "_enterprise_slug": enterprise_slug,
                        "login": node["login"],
                        "databaseId": node.get("databaseId", 0),
                    }
                )
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
                error_msg = errors[0].get("message", "unknown")
                if error_msg == "rate_limited":
                    raise RuntimeError(
                        "GraphQL rate limited while fetching enterprise_members — will retry"
                    )
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
            items.append(
                {
                    "_enterprise_slug": enterprise_slug,
                    "login": node["login"],
                    "databaseId": db_id,
                }
            )
        page_info = member_conn.get("pageInfo", {})
        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None
        return items, next_cursor

    # ── Secret scanning alerts (aggregated summary) ───────────────────────
    if entity_type == "secret_scanning_alerts":
        if cursor == "_done":
            return [], None
        url = f"{_GITHUB_API_BASE}/orgs/{org}/secret-scanning/alerts"
        alert_params: dict[str, object] = {"per_page": page_size, "state": "open"}
        if delta_since is not None:
            alert_params["sort"] = "updated"
            alert_params["direction"] = "desc"
        open_count = 0
        resolved_count = 0
        total_count = 0
        raw_alerts: list[dict] = []
        page = 1
        while True:
            alert_params["page"] = page
            resp = await _github_get(
                url,
                headers,
                alert_params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code in (403, 404):
                logger.warning(
                    "github_sync.secret_scanning_unavailable",
                    org=org,
                    status=resp.status_code,
                )
                return [], None
            resp.raise_for_status()
            alerts = resp.json()
            if not alerts:
                break
            for a in alerts:
                total_count += 1
                if a.get("state") == "open":
                    open_count += 1
                else:
                    resolved_count += 1
                raw_alerts.append(a)
            if not _has_next_page(resp.headers):
                break
            page += 1
        # Also count resolved alerts
        resolved_params: dict[str, object] = {"per_page": page_size, "state": "resolved"}
        rpage = 1
        while True:
            resolved_params["page"] = rpage
            resp = await _github_get(
                url,
                headers,
                resolved_params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code in (403, 404):
                break
            resp.raise_for_status()
            alerts = resp.json()
            if not alerts:
                break
            for _a in alerts:
                total_count += 1
                resolved_count += 1
                raw_alerts.append(_a)
            if not _has_next_page(resp.headers):
                break
            rpage += 1

        summary_item = {
            "_enterprise_slug": org,
            "_org": org,
            "open_count": open_count,
            "resolved_count": resolved_count,
            "total_count": total_count,
            "_raw_alerts": raw_alerts,
        }
        return [summary_item], "_done"

    # ── Dependabot alerts (aggregated summary) ────────────────────────────
    if entity_type == "dependabot_alerts":
        if cursor == "_done":
            return [], None
        url = f"{_GITHUB_API_BASE}/orgs/{org}/dependabot/alerts"
        dep_params: dict[str, object] = {"per_page": page_size}
        if delta_since is not None:
            dep_params["sort"] = "updated"
            dep_params["direction"] = "desc"
        open_count = 0
        fixed_count = 0
        dismissed_count = 0
        total_count = 0
        critical_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0
        raw_dep_alerts: list[dict] = []
        page = 1
        while True:
            dep_params["page"] = page
            resp = await _github_get(
                url,
                headers,
                dep_params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code in (400, 403, 404):
                logger.warning(
                    "github_sync.dependabot_unavailable",
                    org=org,
                    status=resp.status_code,
                )
                return [], None
            resp.raise_for_status()
            alerts = resp.json()
            if not alerts:
                break
            for a in alerts:
                total_count += 1
                state = a.get("state", "")
                if state == "open":
                    open_count += 1
                elif state == "fixed":
                    fixed_count += 1
                elif state == "dismissed":
                    dismissed_count += 1
                severity = (a.get("security_vulnerability") or {}).get("severity", "").lower()
                if severity == "critical":
                    critical_count += 1
                elif severity == "high":
                    high_count += 1
                elif severity == "medium":
                    medium_count += 1
                elif severity == "low":
                    low_count += 1
                raw_dep_alerts.append(a)
            if not _has_next_page(resp.headers):
                break
            page += 1
        summary_item = {
            "_enterprise_slug": org,
            "_org": org,
            "open_count": open_count,
            "fixed_count": fixed_count,
            "dismissed_count": dismissed_count,
            "total_count": total_count,
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "_raw_alerts": raw_dep_alerts,
        }
        return [summary_item], "_done"

    # ── License consumption (enterprise-level) ────────────────────────────
    if entity_type == "license_consumption":
        if cursor == "_done":
            return [], None
        # org param actually holds the enterprise slug for enterprise entities
        enterprise_slug = org
        if not enterprise_slug:
            logger.warning("github_sync.license_consumption_no_slug")
            return [], None
        url = f"{_GITHUB_API_BASE}/enterprises/{enterprise_slug}/consumed-licenses"
        lic_params: dict[str, object] = {"per_page": page_size}
        resp = await _github_get(
            url,
            headers,
            lic_params,
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
        )
        if resp.status_code in (403, 404):
            logger.warning(
                "github_sync.license_consumption_unavailable",
                enterprise=enterprise_slug,
                status=resp.status_code,
            )
            return [], None
        resp.raise_for_status()
        data = resp.json()
        license_item = {
            "_enterprise_slug": enterprise_slug,
            "total_seats_purchased": data.get("total_seats_purchased", 0),
            "total_seats_consumed": data.get("total_seats_consumed", 0),
            "seats": data.get("users", [])[:500],
        }
        return [license_item], "_done"

    # ── Code scanning alerts (aggregated summary) ─────────────────────────
    if entity_type == "code_scanning_alerts":
        if cursor == "_done":
            return [], None
        url = f"{_GITHUB_API_BASE}/orgs/{org}/code-scanning/alerts"
        cs_params: dict[str, object] = {"per_page": page_size}
        if delta_since is not None:
            cs_params["sort"] = "updated"
            cs_params["direction"] = "desc"
        open_count = 0
        fixed_count = 0
        dismissed_count = 0
        total_count = 0
        error_count = 0
        warning_count = 0
        note_count = 0
        raw_cs_alerts: list[dict] = []
        page = 1
        while True:
            cs_params["page"] = page
            resp = await _github_get(
                url,
                headers,
                cs_params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code in (403, 404):
                logger.warning(
                    "github_sync.code_scanning_unavailable",
                    org=org,
                    status=resp.status_code,
                )
                return [], None
            resp.raise_for_status()
            alerts = resp.json()
            if not alerts:
                break
            for a in alerts:
                total_count += 1
                state = a.get("state", "")
                if state == "open":
                    open_count += 1
                elif state == "fixed":
                    fixed_count += 1
                elif state == "dismissed":
                    dismissed_count += 1
                rule = a.get("rule") or {}
                severity = rule.get("security_severity_level") or rule.get("severity", "")
                severity = severity.lower()
                if severity == "error":
                    error_count += 1
                elif severity == "warning":
                    warning_count += 1
                elif severity == "note":
                    note_count += 1
                raw_cs_alerts.append(a)
            if not _has_next_page(resp.headers):
                break
            page += 1
        summary_item = {
            "_enterprise_slug": org,
            "_org": org,
            "open_count": open_count,
            "fixed_count": fixed_count,
            "dismissed_count": dismissed_count,
            "total_count": total_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "note_count": note_count,
            "_raw_alerts": raw_cs_alerts,
        }
        return [summary_item], "_done"
    if entity_type == "actions_workflows":
        if cursor == "_done":
            return [], None
        # Fetch repositories, then aggregate workflow definitions and runs
        repos_url = f"{_GITHUB_API_BASE}/orgs/{org}/repos"
        repos_page = 1
        total_workflows = 0
        active_workflows = 0
        total_runs = 0
        successful_runs = 0
        failed_runs = 0
        cancelled_runs = 0
        while True:
            repos_resp = await _github_get(
                repos_url,
                headers,
                {"per_page": page_size, "page": repos_page, "type": "all"},
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if repos_resp.status_code in (403, 404):
                logger.warning(
                    "github_sync.actions_repos_unavailable",
                    org=org,
                    status=repos_resp.status_code,
                )
                return [], None
            repos_resp.raise_for_status()
            repos = repos_resp.json()
            if not repos:
                break
            for repo in repos:
                if repo.get("archived"):
                    continue
                repo_name = repo["name"]
                # Fetch workflow definitions
                wf_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/actions/workflows"
                wf_resp = await _github_get(
                    wf_url,
                    headers,
                    {"per_page": 100},
                    rate_limiter,
                    etag_cache=etag_cache,
                    api_counter=api_counter,
                    entity_type=entity_type,
                )
                if wf_resp.status_code == 200:
                    wf_data = wf_resp.json()
                    workflows = wf_data.get("workflows", [])
                    total_workflows += len(workflows)
                    active_workflows += sum(1 for w in workflows if w.get("state") == "active")

                # Fetch recent runs (last 30 days or since delta_since)
                runs_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/actions/runs"
                runs_params: dict[str, object] = {"per_page": 100}
                if delta_since is not None:
                    runs_params["created"] = f">{delta_since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                else:
                    # Default to last 30 days
                    from datetime import timedelta as _td

                    cutoff = datetime.now(UTC) - _td(days=30)
                    runs_params["created"] = f">{cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}"

                runs_resp = await _github_get(
                    runs_url,
                    headers,
                    runs_params,
                    rate_limiter,
                    etag_cache=etag_cache,
                    api_counter=api_counter,
                    entity_type=entity_type,
                )
                if runs_resp.status_code == 200:
                    runs_data = runs_resp.json()
                    for run in runs_data.get("workflow_runs", []):
                        total_runs += 1
                        conclusion = run.get("conclusion") or ""
                        if conclusion == "success":
                            successful_runs += 1
                        elif conclusion == "failure":
                            failed_runs += 1
                        elif conclusion == "cancelled":
                            cancelled_runs += 1

            if not _has_next_page(repos_resp.headers):
                break
            repos_page += 1

        summary_item = {
            "_enterprise_slug": org,
            "_org": org,
            "total_workflows": total_workflows,
            "active_workflows": active_workflows,
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "cancelled_runs": cancelled_runs,
        }
        return [summary_item], "_done"

    # ── MFA status (identify members without MFA) ─────────────────────────
    if entity_type == "mfa_status":
        if cursor == "_done":
            return [], None
        # Fetch members with 2FA disabled
        url = f"{_GITHUB_API_BASE}/orgs/{org}/members"
        no_mfa_params: dict[str, object] = {
            "per_page": page_size,
            "filter": "2fa_disabled",
        }
        no_mfa_logins: set[str] = set()
        page = 1
        while True:
            no_mfa_params["page"] = page
            resp = await _github_get(
                url,
                headers,
                no_mfa_params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code in (403, 404):
                logger.warning(
                    "github_sync.mfa_status_unavailable",
                    org=org,
                    status=resp.status_code,
                )
                return [], None
            resp.raise_for_status()
            members = resp.json()
            if not members:
                break
            for m in members:
                no_mfa_logins.add(m["login"])
            if not _has_next_page(resp.headers):
                break
            page += 1

        # Return a single item with the set of members who have MFA disabled
        mfa_item = {
            "_org": org,
            "no_mfa_logins": sorted(no_mfa_logins),
        }
        return [mfa_item], "_done"

    # ── Audit log (enterprise-level, cursor-based pagination) ─────────────
    if entity_type == "audit_log":
        import json as _json

        enterprise_slug = org
        if not enterprise_slug:
            logger.warning("github_sync.audit_log_no_enterprise_slug")
            return [], None

        url = f"{_GITHUB_API_BASE}/enterprises/{enterprise_slug}/audit-log"
        audit_params: dict[str, object] = {
            "include": "all",
            "per_page": page_size,
        }

        # Delta sync: use stored cursor (ISO timestamp) to fetch only new events
        if cursor and cursor != "_done":
            try:
                cursor_data = _json.loads(cursor)
                after_cursor = cursor_data.get("after")
                if after_cursor:
                    # Use only the `after` cursor for pagination — GitHub's audit log
                    # API returns 400 when both `after` and `phrase` are provided.
                    audit_params["after"] = after_cursor
                else:
                    # No pagination cursor — use time-based filter
                    timestamp_cursor = cursor_data.get("timestamp")
                    if timestamp_cursor:
                        audit_params["phrase"] = f"created:>={timestamp_cursor}"
            except (ValueError, TypeError):
                # Legacy cursor format: treat as ISO timestamp
                audit_params["phrase"] = f"created:>={cursor}"
        elif cursor is None and delta_since is not None:
            # First page of a delta sync: use the previous run's completion time
            audit_params["phrase"] = f"created:>={delta_since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        elif cursor is None:
            # First full sync: limit lookback to 90 days
            lookback = datetime.now(UTC) - timedelta(days=90)
            audit_params["phrase"] = f"created:>={lookback.strftime('%Y-%m-%dT%H:%M:%SZ')}"

        resp = await _github_get(
            url,
            headers,
            audit_params,
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
        )
        if resp.status_code in (403, 404):
            logger.warning(
                "github_sync.audit_log_unavailable",
                enterprise=enterprise_slug,
                status=resp.status_code,
                hint="GitHub App may need 'organization_administration:read' "
                "or enterprise audit log permission",
            )
            return [], None
        if resp.status_code == 400 and "after" in audit_params:
            # The 'after' cursor may have expired. Fall back to timestamp-based
            # filter using the cursor's stored timestamp if available.
            logger.warning(
                "github_sync.audit_log_cursor_expired",
                enterprise=enterprise_slug,
                cursor=audit_params.get("after"),
            )
            fallback_params: dict[str, object] = {
                "include": "all",
                "per_page": page_size,
            }
            try:
                cursor_data = _json.loads(cursor)  # type: ignore[arg-type]
                ts = cursor_data.get("timestamp")
                if ts:
                    fallback_params["phrase"] = f"created:>={ts}"
            except (ValueError, TypeError):
                pass
            if "phrase" not in fallback_params:
                lookback = datetime.now(UTC) - timedelta(days=7)
                fallback_params["phrase"] = f"created:>={lookback.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            resp = await _github_get(
                url,
                headers,
                fallback_params,
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code != 200:
                resp.raise_for_status()
        else:
            resp.raise_for_status()
        events = resp.json()

        if not events:
            return [], None

        # Determine next cursor from the last event's _document_id and timestamp
        last_event = events[-1]
        last_ts_raw = last_event.get("@timestamp") or last_event.get("created_at")
        if isinstance(last_ts_raw, (int, float)):
            dt = datetime.fromtimestamp(last_ts_raw / 1000, tz=UTC)
            last_ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif last_ts_raw:
            last_ts = str(last_ts_raw)
        else:
            last_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # GitHub audit log uses Link header or returns `after` cursor
        # Build a composite cursor with both the after value and timestamp
        after_value = last_event.get("_document_id", "")

        # Check for Link header with rel="next"
        has_more = _has_next_page(resp.headers)
        if has_more:
            next_cursor = _json.dumps({"after": after_value, "timestamp": last_ts})
        elif len(events) == page_size:
            # No Link header but we got a full page — there might be more
            next_cursor = _json.dumps({"after": after_value, "timestamp": last_ts})
        else:
            next_cursor = None

        return events, next_cursor

    # ── Team repos (nested: teams → repos per team) ──────────────────────
    if entity_type == "team_repos":
        if cursor is None:
            all_slugs: list[str] = []
            teams_url = f"{_GITHUB_API_BASE}/orgs/{org}/teams"
            tp = 1
            while True:
                resp = await _github_get(
                    teams_url,
                    headers,
                    {"per_page": 100, "page": tp},
                    rate_limiter,
                    etag_cache=etag_cache,
                    api_counter=api_counter,
                    entity_type=entity_type,
                )
                if resp.status_code == 403:
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

        repos_url = f"{_GITHUB_API_BASE}/orgs/{org}/teams/{team_slug}/repos"
        resp = await _github_get(
            repos_url,
            headers,
            {"per_page": page_size, "page": page},
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
        )
        if resp.status_code == 403:
            # Skip this team, advance
            try:
                idx = all_slugs.index(team_slug)
            except ValueError:
                return [], None
            if idx + 1 < len(all_slugs):
                state["current"] = all_slugs[idx + 1]
                state["page"] = 1
                return [], json.dumps(state)
            return [], None
        resp.raise_for_status()
        items = resp.json()
        for item in items:
            item["_team_slug"] = team_slug
            # Extract highest permission
            perms = item.get("permissions", {})
            for perm_level in ("admin", "maintain", "push", "triage", "pull"):
                if perms.get(perm_level):
                    item["_permission"] = perm_level
                    break
            else:
                item["_permission"] = "pull"

        if _has_next_page(resp.headers):
            state["page"] = page + 1
            return items, json.dumps(state)

        try:
            idx = all_slugs.index(team_slug)
        except ValueError:
            return items, None
        if idx + 1 < len(all_slugs):
            state["current"] = all_slugs[idx + 1]
            state["page"] = 1
            return items, json.dumps(state)
        return items, None

    # ── Repo collaborators (iterate repos, fetch direct collaborators) ────
    if entity_type == "repo_collaborators":
        cursor_data = json.loads(cursor) if cursor else {"repo_idx": 0, "page": 1}
        repo_idx = cursor_data["repo_idx"]
        page = cursor_data["page"]

        from sqlalchemy import select as sa_select

        from app.models.github_sync import Repository

        sf = _make_session_factory()
        async with sf() as db_session:
            result = await db_session.execute(
                sa_select(Repository.repo_name).where(
                    Repository.org == org,
                    Repository.archived == False,  # noqa: E712
                )
            )
            repo_names: list[str] = [row[0] for row in result.fetchall()]

        if not repo_names or repo_idx >= len(repo_names):
            return [], None

        items: list[dict] = []
        while repo_idx < len(repo_names):
            repo_name = repo_names[repo_idx]
            collab_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/collaborators"
            resp = await _github_get(
                collab_url,
                headers,
                {"per_page": page_size, "page": page, "affiliation": "direct"},
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code in (403, 404):
                repo_idx += 1
                page = 1
                continue
            resp.raise_for_status()
            collabs = resp.json()
            for c in collabs:
                perms = c.get("permissions", {})
                perm = "read"
                for p in ("admin", "maintain", "push", "triage", "pull"):
                    if perms.get(p):
                        perm = {"pull": "read"}.get(p, p)
                        break
                items.append(
                    {
                        "_repo_name": repo_name,
                        "login": c.get("login"),
                        "id": c.get("id"),
                        "permission": perm,
                    }
                )

            if _has_next_page(resp.headers):
                return items, json.dumps({"repo_idx": repo_idx, "page": page + 1})

            repo_idx += 1
            page = 1
            # Return batch after each repo to keep pages manageable
            if items:
                next_cursor = (
                    json.dumps({"repo_idx": repo_idx, "page": 1})
                    if repo_idx < len(repo_names)
                    else None
                )
                return items, next_cursor

        return items, None

    # ── Repo webhooks (iterate repos, fetch hooks per repo) ───────────────
    if entity_type == "repo_webhooks":
        cursor_data = json.loads(cursor) if cursor else {"repo_idx": 0, "page": 1}
        repo_idx = cursor_data["repo_idx"]
        page = cursor_data["page"]

        from sqlalchemy import select as sa_select

        from app.models.github_sync import Repository

        sf = _make_session_factory()
        async with sf() as db_session:
            result = await db_session.execute(
                sa_select(Repository.repo_name).where(
                    Repository.org == org,
                    Repository.archived == False,  # noqa: E712
                )
            )
            repo_names: list[str] = [row[0] for row in result.fetchall()]

        if not repo_names or repo_idx >= len(repo_names):
            return [], None

        items: list[dict] = []
        while repo_idx < len(repo_names):
            repo_name = repo_names[repo_idx]
            hooks_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/hooks"
            resp = await _github_get(
                hooks_url,
                headers,
                {"per_page": page_size, "page": page},
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code in (403, 404):
                repo_idx += 1
                page = 1
                continue
            resp.raise_for_status()
            hooks = resp.json()
            for h in hooks:
                config = h.get("config", {})
                items.append(
                    {
                        "_repo_name": repo_name,
                        "hook_id": h.get("id"),
                        "name": h.get("name", "web"),
                        "active": h.get("active", False),
                        "config_url": config.get("url"),
                        "config_content_type": config.get("content_type"),
                        "config_insecure_ssl": config.get("insecure_ssl"),
                        "events": h.get("events", []),
                    }
                )

            if _has_next_page(resp.headers):
                return items, json.dumps({"repo_idx": repo_idx, "page": page + 1})

            repo_idx += 1
            page = 1
            if items:
                next_cursor = (
                    json.dumps({"repo_idx": repo_idx, "page": 1})
                    if repo_idx < len(repo_names)
                    else None
                )
                return items, next_cursor

        return items, None

    # ── Actions permissions (org-level, single call per org) ──────────────
    if entity_type == "actions_permissions":
        if cursor is not None:
            return [], None  # Single-page entity
        perm_url = f"{_GITHUB_API_BASE}/orgs/{org}/actions/permissions"
        resp = await _github_get(
            perm_url,
            headers,
            {},
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
        )
        if resp.status_code == 403:
            return [], None
        resp.raise_for_status()
        data = resp.json()

        # Also fetch selected actions if applicable
        allowed_actions = data.get("allowed_actions")
        github_owned = True
        verified = False
        patterns: list[str] = []
        if allowed_actions == "selected":
            sel_url = f"{_GITHUB_API_BASE}/orgs/{org}/actions/permissions/selected-actions"
            sel_resp = await _github_get(
                sel_url,
                headers,
                {},
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if sel_resp.status_code == 200:
                sel_data = sel_resp.json()
                github_owned = sel_data.get("github_owned_allowed", True)
                verified = sel_data.get("verified_allowed", False)
                patterns = sel_data.get("patterns_allowed", [])

        items = [
            {
                "enabled_repositories": data.get("enabled_repositories", "all"),
                "allowed_actions": allowed_actions,
                "github_owned_allowed": github_owned,
                "verified_allowed": verified,
                "patterns_allowed": patterns,
            }
        ]
        return items, None

    # ── Self-hosted runners (paginated, nested in "runners" key) ──────────
    if entity_type == "self_hosted_runners":
        page = int(cursor) if cursor else 1
        runners_url = f"{_GITHUB_API_BASE}/orgs/{org}/actions/runners"
        resp = await _github_get(
            runners_url,
            headers,
            {"per_page": page_size, "page": page},
            rate_limiter,
            etag_cache=etag_cache,
            api_counter=api_counter,
            entity_type=entity_type,
        )
        if resp.status_code == 403:
            return [], None
        resp.raise_for_status()
        data = resp.json()
        runners = data.get("runners", [])
        items = []
        for r in runners:
            labels = [lb.get("name", "") for lb in (r.get("labels") or [])]
            rg = r.get("runner_group_id")
            rg_name = r.get("runner_group_name")
            items.append(
                {
                    "runner_id": r.get("id"),
                    "name": r.get("name", ""),
                    "os": r.get("os", "unknown"),
                    "status": r.get("status", "offline"),
                    "busy": r.get("busy", False),
                    "labels": labels,
                    "runner_group_id": rg,
                    "runner_group_name": rg_name,
                }
            )
        # Determine if more pages: total_count > page * page_size
        total = data.get("total_count", 0)
        if page * page_size < total:
            return items, str(page + 1)
        return items, None

    # ── Deploy keys (iterate repos, fetch keys per repo) ──────────────────
    if entity_type == "deploy_keys":
        cursor_data = json.loads(cursor) if cursor else {"repo_idx": 0, "page": 1}
        repo_idx = cursor_data["repo_idx"]
        page = cursor_data["page"]

        from sqlalchemy import select as sa_select

        from app.models.github_sync import Repository

        sf = _make_session_factory()
        async with sf() as db_session:
            result = await db_session.execute(
                sa_select(Repository.repo_name).where(
                    Repository.org == org,
                    Repository.archived == False,  # noqa: E712
                )
            )
            repo_names: list[str] = [row[0] for row in result.fetchall()]

        if not repo_names or repo_idx >= len(repo_names):
            return [], None

        items: list[dict] = []
        while repo_idx < len(repo_names):
            repo_name = repo_names[repo_idx]
            keys_url = f"{_GITHUB_API_BASE}/repos/{org}/{repo_name}/keys"
            resp = await _github_get(
                keys_url,
                headers,
                {"per_page": page_size, "page": page},
                rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type=entity_type,
            )
            if resp.status_code in (403, 404):
                repo_idx += 1
                page = 1
                continue
            resp.raise_for_status()
            keys = resp.json()
            for k in keys:
                items.append(
                    {
                        "_repo_name": repo_name,
                        "key_id": k.get("id"),
                        "title": k.get("title", ""),
                        "read_only": k.get("read_only", True),
                        "created_at": k.get("created_at"),
                    }
                )

            if _has_next_page(resp.headers):
                return items, json.dumps({"repo_idx": repo_idx, "page": page + 1})

            repo_idx += 1
            page = 1
            if items:
                next_cursor = (
                    json.dumps({"repo_idx": repo_idx, "page": 1})
                    if repo_idx < len(repo_names)
                    else None
                )
                return items, next_cursor

        return items, None

    logger.error("github_sync.unknown_entity_type", entity_type=entity_type)
    return [], None


# ── Upsert helpers (one per entity type) ──────────────────────────────────────


async def _upsert_org_members(
    session: AsyncSession, org: str, items: list[dict], delta_since: datetime | None = None
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgMember

    current_logins: set[str] = set()
    for item in items:
        login = item["login"]
        current_logins.add(login)
        stmt = (
            insert(OrgMember)
            .values(
                org=org,
                github_login=login,
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

    # Delta sync: remove members no longer in the current list
    if delta_since is not None and current_logins:
        from sqlalchemy import delete

        await session.execute(
            delete(OrgMember).where(
                OrgMember.org == org,
                OrgMember.github_login.notin_(current_logins),
            )
        )
    await session.commit()


async def _upsert_repositories(session: AsyncSession, org: str, items: list[dict]) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import Repository

    for item in items:
        pushed_dt = _parse_gh_dt(item.get("pushed_at"))
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
    session: AsyncSession, org: str, items: list[dict], delta_since: datetime | None = None
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgTeam

    current_slugs: set[str] = set()
    for item in items:
        slug = item["slug"]
        current_slugs.add(slug)
        parent = item.get("parent") or {}
        stmt = (
            insert(OrgTeam)
            .values(
                org=org,
                team_slug=slug,
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

    # Delta sync: remove teams no longer in the current list
    if delta_since is not None and current_slugs:
        from sqlalchemy import delete

        await session.execute(
            delete(OrgTeam).where(
                OrgTeam.org == org,
                OrgTeam.team_slug.notin_(current_slugs),
            )
        )
    await session.commit()


async def _upsert_team_members(
    session: AsyncSession, org: str, items: list[dict], delta_since: datetime | None = None
) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgTeamMember

    # Track current memberships per team for delta sync
    team_logins: dict[str, set[str]] = {}
    for item in items:
        team_slug = item.get("_team_slug", "unknown")
        if team_slug not in team_logins:
            team_logins[team_slug] = set()
        team_logins[team_slug].add(item["login"])
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

    # Delta sync: remove members no longer in any team that was re-synced
    if delta_since is not None:
        from sqlalchemy import delete

        for team_slug, logins in team_logins.items():
            if logins:
                await session.execute(
                    delete(OrgTeamMember).where(
                        OrgTeamMember.org == org,
                        OrgTeamMember.team_slug == team_slug,
                        OrgTeamMember.github_login.notin_(logins),
                    )
                )
    await session.commit()


async def _upsert_branch_protections(session: AsyncSession, org: str, items: list[dict]) -> None:
    from sqlalchemy import delete, text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import RepoBranchProtection

    # Remove stale protection rows for this org — only repos with real
    # protection will be re-inserted below.  This ensures the
    # "missing_protection" posture rule can detect unprotected repos by
    # looking for repos WITHOUT a corresponding row.
    protected_repos = {item["_repo_name"] for item in items}
    if not protected_repos:
        # No protected repos at all — delete everything for this org
        await session.execute(delete(RepoBranchProtection).where(RepoBranchProtection.org == org))
    else:
        # Delete rows for repos that lost their protection
        await session.execute(
            delete(RepoBranchProtection).where(
                RepoBranchProtection.org == org,
                RepoBranchProtection.repo_name.notin_(protected_repos),
            )
        )

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


async def _upsert_installations(session: AsyncSession, _org: str | None, items: list[dict]) -> None:
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


async def _enrich_org_settings(
    sf: async_sessionmaker[AsyncSession],
    run_id: str,
    token_manager: GitHubAppTokenManager,
    rate_limiter: GitHubRateLimiter,
    org_inst_map: dict[str, int],
    fallback_installation_id: int,
) -> int:
    """Supplement org security settings via REST API.

    Uses org-level installation tokens (which have ``administration:read``)
    to fetch fields like ``two_factor_requirement_enabled`` that require
    elevated permissions.  For orgs without their own installation, falls
    back to GraphQL which can access org settings via the enterprise token.
    Returns the number of orgs enriched.
    """
    from sqlalchemy import select, update

    from app.models.github_sync import EnterpriseOrg

    async with sf() as session:
        result = await session.execute(select(EnterpriseOrg))
        org_list = list(result.scalars().all())

    await _write_sync_log(
        sf,
        run_id,
        f"Enrichment: found {len(org_list)} org(s) to enrich",
        entity_type="orgs",
    )

    enriched = 0
    # Orgs that REST couldn't enrich — will try GraphQL batch fallback
    unenriched_orgs: list[EnterpriseOrg] = []

    for org_row in org_list:
        try:
            # Only enrich orgs that have their own installation with admin:read
            inst_id = org_inst_map.get(org_row.org_login)
            if inst_id is None:
                # No org-level installation — skip (app must be installed)
                continue

            token = await token_manager.get_installation_token(inst_id)
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            resp = await _github_get(
                f"{_GITHUB_API_BASE}/orgs/{org_row.org_login}",
                headers,
                {},
                rate_limiter,
            )
            if resp.status_code != 200:
                logger.warning(
                    "github_sync.org_enrich_http_error",
                    org=org_row.org_login,
                    status=resp.status_code,
                )
                unenriched_orgs.append(org_row)
                continue
            data = resp.json()

            settings_update: dict[str, object] = {}
            rest_fields = {
                "two_factor_required": "two_factor_requirement_enabled",
                "default_repo_permission": "default_repository_permission",
                "members_can_fork_private_repos": "members_can_fork_private_repositories",
                "members_can_create_public_repos": "members_can_create_public_repositories",
            }
            for db_col, api_key in rest_fields.items():
                api_val = data.get(api_key)
                if api_val is not None:
                    settings_update[db_col] = api_val

            await _write_sync_log(
                sf,
                run_id,
                f"REST enrichment for {org_row.org_login}: {len(settings_update)} fields",
                entity_type="orgs",
                org=org_row.org_login,
            )

            if not settings_update:
                unenriched_orgs.append(org_row)
                continue

            async with sf() as session:
                await session.execute(
                    update(EnterpriseOrg)
                    .where(EnterpriseOrg.id == org_row.id)
                    .values(**settings_update)
                )
                await session.commit()
            logger.info(
                "github_sync.org_enriched",
                org=org_row.org_login,
                fields=list(settings_update.keys()),
            )
            enriched += 1
        except Exception as exc:
            logger.warning(
                "github_sync.org_enrich_failed",
                org=org_row.org_login,
                error=str(exc),
            )
            unenriched_orgs.append(org_row)

    # GraphQL fallback removed — org enrichment requires the app to be
    # installed on each org with administration:read permission.
    if unenriched_orgs:
        logger.info(
            "github_sync.enrichment_skipped_no_installation",
            count=len(unenriched_orgs),
        )

    return enriched


_ORG_SETTINGS_GRAPHQL_QUERY = """
query($login: String!) {
  organization(login: $login) {
    login
    requiresTwoFactorAuthentication
    ipAllowListEnabledSetting
    membersCanForkPrivateRepositories
    defaultRepositoryPermissionSetting
    membersCanCreatePublicRepositories
  }
}
"""


async def _enrich_orgs_graphql(
    sf: async_sessionmaker[AsyncSession],
    run_id: str,
    token_manager: GitHubAppTokenManager,
    rate_limiter: GitHubRateLimiter,
    installation_id: int,
    orgs: list,
) -> int:
    """Enrich org settings via GraphQL using the enterprise installation token.

    The enterprise-level token typically has broader read access to org metadata
    through GraphQL than the REST API provides.
    """
    from sqlalchemy import update

    from app.models.github_sync import EnterpriseOrg

    token = await token_manager.get_installation_token(installation_id)
    enriched = 0

    for org_row in orgs:
        try:
            result = await _graphql_page(
                token,
                _ORG_SETTINGS_GRAPHQL_QUERY,
                {"login": org_row.org_login},
                rate_limiter,
            )

            data = (result.get("data") or {}).get("organization")
            if not data:
                # GraphQL may return errors for orgs we can't access
                errors = result.get("errors", [])
                if errors:
                    logger.debug(
                        "github_sync.org_graphql_no_access",
                        org=org_row.org_login,
                        errors=[e.get("message", "") for e in errors[:2]],
                    )
                continue

            settings_update: dict[str, object] = {}

            # Map GraphQL fields to DB columns
            two_fa = data.get("requiresTwoFactorAuthentication")
            if two_fa is not None:
                settings_update["two_factor_required"] = two_fa

            ip_allow = data.get("ipAllowListEnabledSetting")
            if ip_allow is not None:
                # GraphQL returns ENABLED/DISABLED enum
                settings_update["ip_allow_list_enabled"] = (
                    ip_allow == "ENABLED" if isinstance(ip_allow, str) else ip_allow
                )

            fork_private = data.get("membersCanForkPrivateRepositories")
            if fork_private is not None:
                settings_update["members_can_fork_private_repos"] = fork_private

            default_perm = data.get("defaultRepositoryPermissionSetting")
            if default_perm is not None:
                # GraphQL returns "READ"/"WRITE"/"ADMIN"/"NONE" — lowercase for DB
                settings_update["default_repo_permission"] = default_perm.lower()

            create_public = data.get("membersCanCreatePublicRepositories")
            if create_public is not None:
                settings_update["members_can_create_public_repos"] = create_public

            await _write_sync_log(
                sf,
                run_id,
                f"GraphQL enrichment for {org_row.org_login}: {len(settings_update)} fields",
                entity_type="orgs",
                org=org_row.org_login,
            )

            if not settings_update:
                continue

            async with sf() as session:
                await session.execute(
                    update(EnterpriseOrg)
                    .where(EnterpriseOrg.id == org_row.id)
                    .values(**settings_update)
                )
                await session.commit()
            logger.info(
                "github_sync.org_enriched_graphql",
                org=org_row.org_login,
                fields=list(settings_update.keys()),
            )
            enriched += 1

        except Exception as exc:
            logger.warning(
                "github_sync.org_graphql_enrich_failed",
                org=org_row.org_login,
                error=str(exc),
            )

    return enriched


async def _upsert_outside_collaborators(
    session: AsyncSession, org: str, items: list[dict], delta_since: datetime | None = None
) -> None:
    """Upsert outside collaborators for an org."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgOutsideCollaborator

    # The enterprise_slug is not available at this level — use org as a
    # placeholder.  The orchestrator fans out per (entity_type, org) and
    # does not pass the enterprise slug through; the org field is what
    # matters for health queries.
    current_logins: set[str] = set()
    for item in items:
        login = item["login"]
        current_logins.add(login)
        stmt = (
            insert(OrgOutsideCollaborator)
            .values(
                enterprise_slug=item.get("_enterprise_slug", org),
                org=org,
                login=login,
                github_id=item["id"],
                avatar_url=item.get("avatar_url"),
                site_admin=item.get("site_admin", False),
            )
            .on_conflict_do_update(
                constraint="uq_outside_collab_slug_org_login",
                set_={
                    "github_id": item["id"],
                    "avatar_url": item.get("avatar_url"),
                    "site_admin": item.get("site_admin", False),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)

    # Delta sync: remove collaborators no longer in the current list
    if delta_since is not None and current_logins:
        from sqlalchemy import delete

        await session.execute(
            delete(OrgOutsideCollaborator).where(
                OrgOutsideCollaborator.org == org,
                OrgOutsideCollaborator.login.notin_(current_logins),
            )
        )
    await session.commit()


async def _upsert_secret_scanning_summary(
    session: AsyncSession, org: str, items: list[dict]
) -> None:
    """Upsert secret scanning alert summary for an org."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgSecretScanningAlertSummary

    for item in items:
        stmt = (
            insert(OrgSecretScanningAlertSummary)
            .values(
                enterprise_slug=item.get("_enterprise_slug", org),
                org=item.get("_org", org),
                open_count=item["open_count"],
                resolved_count=item["resolved_count"],
                total_count=item["total_count"],
            )
            .on_conflict_do_update(
                constraint="uq_secret_scanning_summary_slug_org",
                set_={
                    "open_count": item["open_count"],
                    "resolved_count": item["resolved_count"],
                    "total_count": item["total_count"],
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_dependabot_summary(session: AsyncSession, org: str, items: list[dict]) -> None:
    """Upsert dependabot alert summary for an org."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgDependabotAlertSummary

    for item in items:
        stmt = (
            insert(OrgDependabotAlertSummary)
            .values(
                enterprise_slug=item.get("_enterprise_slug", org),
                org=item.get("_org", org),
                open_count=item["open_count"],
                fixed_count=item["fixed_count"],
                dismissed_count=item["dismissed_count"],
                total_count=item["total_count"],
                critical_count=item["critical_count"],
                high_count=item["high_count"],
                medium_count=item["medium_count"],
                low_count=item["low_count"],
            )
            .on_conflict_do_update(
                constraint="uq_dependabot_summary_slug_org",
                set_={
                    "open_count": item["open_count"],
                    "fixed_count": item["fixed_count"],
                    "dismissed_count": item["dismissed_count"],
                    "total_count": item["total_count"],
                    "critical_count": item["critical_count"],
                    "high_count": item["high_count"],
                    "medium_count": item["medium_count"],
                    "low_count": item["low_count"],
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_license_consumption(
    session: AsyncSession, _org: str | None, items: list[dict]
) -> None:
    """Upsert enterprise license consumption data."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import EnterpriseLicenseConsumption

    for item in items:
        stmt = (
            insert(EnterpriseLicenseConsumption)
            .values(
                enterprise_slug=item["_enterprise_slug"],
                total_seats_purchased=item["total_seats_purchased"],
                total_seats_consumed=item["total_seats_consumed"],
                seats=item.get("seats"),
            )
            .on_conflict_do_update(
                constraint="uq_license_consumption_slug",
                set_={
                    "total_seats_purchased": item["total_seats_purchased"],
                    "total_seats_consumed": item["total_seats_consumed"],
                    "seats": item.get("seats"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_code_scanning_summary(
    session: AsyncSession, org: str, items: list[dict[str, object]]
) -> None:
    """Upsert code scanning alert summary for an org."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgCodeScanningAlertSummary

    for item in items:
        stmt = (
            insert(OrgCodeScanningAlertSummary)
            .values(
                enterprise_slug=item.get("_enterprise_slug", org),
                org=item.get("_org", org),
                open_count=item["open_count"],
                fixed_count=item["fixed_count"],
                dismissed_count=item["dismissed_count"],
                total_count=item["total_count"],
                error_count=item["error_count"],
                warning_count=item["warning_count"],
                note_count=item["note_count"],
            )
            .on_conflict_do_update(
                constraint="uq_code_scanning_summary_slug_org",
                set_={
                    "open_count": item["open_count"],
                    "fixed_count": item["fixed_count"],
                    "dismissed_count": item["dismissed_count"],
                    "total_count": item["total_count"],
                    "error_count": item["error_count"],
                    "warning_count": item["warning_count"],
                    "note_count": item["note_count"],
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_actions_workflow_summary(
    session: AsyncSession, org: str, items: list[dict[str, object]]
) -> None:
    """Upsert actions workflow summary for an org."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgActionsWorkflowSummary

    for item in items:
        stmt = (
            insert(OrgActionsWorkflowSummary)
            .values(
                enterprise_slug=item.get("_enterprise_slug", org),
                org=item.get("_org", org),
                total_workflows=item["total_workflows"],
                active_workflows=item["active_workflows"],
                total_runs=item["total_runs"],
                successful_runs=item["successful_runs"],
                failed_runs=item["failed_runs"],
                cancelled_runs=item["cancelled_runs"],
            )
            .on_conflict_do_update(
                constraint="uq_actions_workflow_summary_slug_org",
                set_={
                    "total_workflows": item["total_workflows"],
                    "active_workflows": item["active_workflows"],
                    "total_runs": item["total_runs"],
                    "successful_runs": item["successful_runs"],
                    "failed_runs": item["failed_runs"],
                    "cancelled_runs": item["cancelled_runs"],
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_mfa_status(
    session: AsyncSession, org: str, items: list[dict[str, object]]
) -> None:
    """Update MFA status on org members.

    Receives a single item with a list of logins that have MFA disabled.
    Marks all other org members as MFA enabled.
    """
    from sqlalchemy import update

    from app.models.github_sync import OrgMember

    for item in items:
        no_mfa_logins = list(item.get("no_mfa_logins") or [])

        # Set all members in this org to mfa_enabled = True first
        await session.execute(
            update(OrgMember).where(OrgMember.org == org).values(mfa_enabled=True)
        )

        # Then mark the ones without MFA as disabled
        if no_mfa_logins:
            await session.execute(
                update(OrgMember)
                .where(
                    OrgMember.org == org,
                    OrgMember.github_login.in_(no_mfa_logins),
                )
                .values(mfa_enabled=False)
            )
    await session.commit()


async def _upsert_secret_scanning_alerts(
    session: AsyncSession, org: str, items: list[dict[str, object]]
) -> None:
    """Upsert individual secret scanning alert records.

    The ``items`` list comes from ``_fetch_page`` which returns raw GitHub
    API JSON objects (one per alert). We store each alert individually
    to enable accurate MTTR, resolution rate, and actor correlation.
    """
    from sqlalchemy import text as sa_text

    for a in items:
        repo = a.get("repository") or {}
        repo_full_name = repo.get("full_name", "") if isinstance(repo, dict) else ""
        bypassed_by = a.get("push_protection_bypassed_by") or {}
        bypassed_login = bypassed_by.get("login", "") if isinstance(bypassed_by, dict) else ""

        # Map locations to first file path and commit SHA
        locations = a.get("locations") or []
        file_path = None
        commit_sha = None
        if locations and isinstance(locations, list):
            first_loc = locations[0] if locations else {}
            details = first_loc.get("details") or {}
            file_path = details.get("path")
            commit_sha = details.get("commit_sha")

        # Fallback: some API responses have location info at top level
        if not file_path:
            file_path = (
                a.get("secret_scanning_location", {}).get("path")
                if isinstance(a.get("secret_scanning_location"), dict)
                else None
            )

        await session.execute(
            sa_text("""
                INSERT INTO secret_scanning_alerts
                    (org_slug, alert_number, repo_full_name, secret_type,
                     secret_type_display, file_path, commit_sha, state,
                     resolution, push_protection_bypassed,
                     push_protection_bypassed_by, created_at, resolved_at,
                     synced_at)
                VALUES
                    (:org_slug, :alert_number, :repo_full_name, :secret_type,
                     :secret_type_display, :file_path, :commit_sha, :state,
                     :resolution, :push_protection_bypassed,
                     :push_protection_bypassed_by, :created_at, :resolved_at,
                     NOW())
                ON CONFLICT (org_slug, repo_full_name, alert_number) DO UPDATE SET
                    secret_type = EXCLUDED.secret_type,
                    secret_type_display = EXCLUDED.secret_type_display,
                    file_path = EXCLUDED.file_path,
                    commit_sha = EXCLUDED.commit_sha,
                    state = EXCLUDED.state,
                    resolution = EXCLUDED.resolution,
                    push_protection_bypassed = EXCLUDED.push_protection_bypassed,
                    push_protection_bypassed_by = EXCLUDED.push_protection_bypassed_by,
                    resolved_at = EXCLUDED.resolved_at,
                    synced_at = NOW()
            """),
            {
                "org_slug": org,
                "alert_number": a.get("number", 0),
                "repo_full_name": repo_full_name,
                "secret_type": a.get("secret_type", "unknown"),
                "secret_type_display": a.get("secret_type_display_name"),
                "file_path": file_path,
                "commit_sha": commit_sha,
                "state": a.get("state", "open"),
                "resolution": a.get("resolution"),
                "push_protection_bypassed": bool(a.get("push_protection_bypassed")),
                "push_protection_bypassed_by": bypassed_login or None,
                "created_at": _parse_gh_dt(a.get("created_at")),
                "resolved_at": _parse_gh_dt(a.get("resolved_at")),
            },
        )
    await session.commit()


async def _upsert_code_scanning_alerts(
    session: AsyncSession, org: str, items: list[dict[str, object]]
) -> None:
    """Upsert individual code scanning alert records.

    Stores each alert individually to enable per-alert severity breakdown,
    MTTR calculation, and dismissal actor correlation.
    """
    from sqlalchemy import text as sa_text

    for a in items:
        repo = a.get("repository") or {}
        repo_full_name = repo.get("full_name", "") if isinstance(repo, dict) else ""
        rule = a.get("rule") or {}
        if not isinstance(rule, dict):
            rule = {}
        tool_obj = a.get("tool") or {}
        if not isinstance(tool_obj, dict):
            tool_obj = {}
        most_recent = a.get("most_recent_instance") or {}
        if not isinstance(most_recent, dict):
            most_recent = {}
        location = most_recent.get("location") or {}
        if not isinstance(location, dict):
            location = {}
        dismissed_by_obj = a.get("dismissed_by") or {}
        if not isinstance(dismissed_by_obj, dict):
            dismissed_by_obj = {}

        # CWE IDs from the rule's tags (format: "external/cwe/cwe-79")
        cwe_ids = []
        for tag in rule.get("tags") or []:
            if isinstance(tag, str) and tag.startswith("external/cwe/"):
                cwe_ids.append(tag.replace("external/cwe/", "").upper())

        await session.execute(
            sa_text("""
                INSERT INTO code_scanning_alerts
                    (org_slug, alert_number, repo_full_name, rule_id,
                     rule_description, severity, security_severity,
                     cwe_ids, tool_name, file_path, start_line, state,
                     dismissed_by, dismissed_reason, dismissed_at,
                     created_at, fixed_at, synced_at)
                VALUES
                    (:org_slug, :alert_number, :repo_full_name, :rule_id,
                     :rule_description, :severity, :security_severity,
                     :cwe_ids, :tool_name, :file_path, :start_line, :state,
                     :dismissed_by, :dismissed_reason, :dismissed_at,
                     :created_at, :fixed_at, NOW())
                ON CONFLICT (org_slug, repo_full_name, alert_number) DO UPDATE SET
                    rule_id = EXCLUDED.rule_id,
                    rule_description = EXCLUDED.rule_description,
                    severity = EXCLUDED.severity,
                    security_severity = EXCLUDED.security_severity,
                    cwe_ids = EXCLUDED.cwe_ids,
                    tool_name = EXCLUDED.tool_name,
                    file_path = EXCLUDED.file_path,
                    start_line = EXCLUDED.start_line,
                    state = EXCLUDED.state,
                    dismissed_by = EXCLUDED.dismissed_by,
                    dismissed_reason = EXCLUDED.dismissed_reason,
                    dismissed_at = EXCLUDED.dismissed_at,
                    fixed_at = EXCLUDED.fixed_at,
                    synced_at = NOW()
            """),
            {
                "org_slug": org,
                "alert_number": a.get("number", 0),
                "repo_full_name": repo_full_name,
                "rule_id": rule.get("id", "unknown"),
                "rule_description": rule.get("description"),
                "severity": rule.get("severity"),
                "security_severity": rule.get("security_severity_level"),
                "cwe_ids": cwe_ids or None,
                "tool_name": tool_obj.get("name"),
                "file_path": location.get("path"),
                "start_line": location.get("start_line"),
                "state": a.get("state", "open"),
                "dismissed_by": dismissed_by_obj.get("login"),
                "dismissed_reason": a.get("dismissed_reason"),
                "dismissed_at": _parse_gh_dt(a.get("dismissed_at")),
                "created_at": _parse_gh_dt(a.get("created_at")),
                "fixed_at": _parse_gh_dt(a.get("fixed_at")),
            },
        )
    await session.commit()


async def _upsert_dependabot_alerts(
    session: AsyncSession, org: str, items: list[dict[str, object]]
) -> None:
    """Upsert individual Dependabot alert records.

    Stores each alert individually to enable accurate vulnerability aging,
    CVSS breakdown, and 90-day critical aging signal generation.
    """
    from sqlalchemy import text as sa_text

    for a in items:
        repo = a.get("repository") or {}
        repo_full_name = repo.get("full_name", "") if isinstance(repo, dict) else ""
        sec_vuln = a.get("security_vulnerability") or {}
        if not isinstance(sec_vuln, dict):
            sec_vuln = {}
        pkg = sec_vuln.get("package") or {}
        if not isinstance(pkg, dict):
            pkg = {}
        first_patched = sec_vuln.get("first_patched_version") or {}
        if not isinstance(first_patched, dict):
            first_patched = {}
        sec_advisory = a.get("security_advisory") or {}
        if not isinstance(sec_advisory, dict):
            sec_advisory = {}
        cvss = sec_advisory.get("cvss") or {}
        if not isinstance(cvss, dict):
            cvss = {}
        dismissed_by_obj = a.get("dismissed_by") or {}
        if not isinstance(dismissed_by_obj, dict):
            dismissed_by_obj = {}

        # CWE IDs from advisory
        cwe_ids = []
        for cwe in sec_advisory.get("cwes") or []:
            if isinstance(cwe, dict):
                cwe_ids.append(cwe.get("cwe_id", ""))
            elif isinstance(cwe, str):
                cwe_ids.append(cwe)

        await session.execute(
            sa_text("""
                INSERT INTO dependabot_alerts
                    (org_slug, alert_number, repo_full_name, package_name,
                     package_ecosystem, severity, cvss_score, cve_id,
                     cwe_ids, vulnerable_version_range, patched_version,
                     state, dismissed_by, dismissed_reason, created_at,
                     fixed_at, auto_dismissed_at, synced_at)
                VALUES
                    (:org_slug, :alert_number, :repo_full_name, :package_name,
                     :package_ecosystem, :severity, :cvss_score, :cve_id,
                     :cwe_ids, :vulnerable_version_range, :patched_version,
                     :state, :dismissed_by, :dismissed_reason, :created_at,
                     :fixed_at, :auto_dismissed_at, NOW())
                ON CONFLICT (org_slug, repo_full_name, alert_number) DO UPDATE SET
                    package_name = EXCLUDED.package_name,
                    package_ecosystem = EXCLUDED.package_ecosystem,
                    severity = EXCLUDED.severity,
                    cvss_score = EXCLUDED.cvss_score,
                    cve_id = EXCLUDED.cve_id,
                    cwe_ids = EXCLUDED.cwe_ids,
                    vulnerable_version_range = EXCLUDED.vulnerable_version_range,
                    patched_version = EXCLUDED.patched_version,
                    state = EXCLUDED.state,
                    dismissed_by = EXCLUDED.dismissed_by,
                    dismissed_reason = EXCLUDED.dismissed_reason,
                    fixed_at = EXCLUDED.fixed_at,
                    auto_dismissed_at = EXCLUDED.auto_dismissed_at,
                    synced_at = NOW()
            """),
            {
                "org_slug": org,
                "alert_number": a.get("number", 0),
                "repo_full_name": repo_full_name,
                "package_name": pkg.get("name", "unknown"),
                "package_ecosystem": pkg.get("ecosystem"),
                "severity": sec_vuln.get("severity"),
                "cvss_score": cvss.get("score"),
                "cve_id": sec_advisory.get("cve_id"),
                "cwe_ids": cwe_ids or None,
                "vulnerable_version_range": sec_vuln.get("vulnerable_version_range"),
                "patched_version": first_patched.get("identifier"),
                "state": a.get("state", "open"),
                "dismissed_by": dismissed_by_obj.get("login"),
                "dismissed_reason": a.get("dismissed_reason"),
                "created_at": _parse_gh_dt(a.get("created_at")),
                "fixed_at": _parse_gh_dt(a.get("fixed_at")),
                "auto_dismissed_at": _parse_gh_dt(a.get("auto_dismissed_at")),
            },
        )
    await session.commit()


async def _upsert_items(
    session: AsyncSession,
    entity_type: str,
    org: str | None,
    items: list[dict[str, object]],
    delta_since: datetime | None = None,
) -> None:
    """Dispatch to the appropriate upsert function for *entity_type*.

    Uses INSERT ... ON CONFLICT DO UPDATE SET synced_at = NOW(), [...fields].

    For entity types that support delta sync (org_members, teams,
    team_members, outside_collaborators), the ``delta_since`` parameter
    is forwarded so the handler can prune stale records.
    """
    org_str = org or ""

    if entity_type == "org_members":
        await _upsert_org_members(session, org_str, items, delta_since=delta_since)
    elif entity_type == "repositories":
        await _upsert_repositories(session, org_str, items)
    elif entity_type == "teams":
        await _upsert_teams(session, org_str, items, delta_since=delta_since)
    elif entity_type == "team_members":
        await _upsert_team_members(session, org_str, items, delta_since=delta_since)
    elif entity_type == "branch_protections":
        await _upsert_branch_protections(session, org_str, items)
    elif entity_type == "installations":
        await _upsert_installations(session, org, items)
    elif entity_type == "orgs":
        await _upsert_enterprise_orgs(session, org, items)
    elif entity_type == "enterprise_members":
        await _upsert_enterprise_members(session, org, items)
    elif entity_type == "outside_collaborators":
        await _upsert_outside_collaborators(session, org_str, items, delta_since=delta_since)
    elif entity_type == "secret_scanning_alerts":
        await _upsert_secret_scanning_summary(session, org_str, items)
        # Also upsert individual alert records from raw API data
        for item in items:
            raw_alerts = item.get("_raw_alerts") or []
            if raw_alerts:
                await _upsert_secret_scanning_alerts(session, org_str, raw_alerts)
    elif entity_type == "dependabot_alerts":
        await _upsert_dependabot_summary(session, org_str, items)
        # Also upsert individual alert records from raw API data
        for item in items:
            raw_alerts = item.get("_raw_alerts") or []
            if raw_alerts:
                await _upsert_dependabot_alerts(session, org_str, raw_alerts)
    elif entity_type == "license_consumption":
        await _upsert_license_consumption(session, org, items)
    elif entity_type == "code_scanning_alerts":
        await _upsert_code_scanning_summary(session, org_str, items)
        # Also upsert individual alert records from raw API data
        for item in items:
            raw_alerts = item.get("_raw_alerts") or []
            if raw_alerts:
                await _upsert_code_scanning_alerts(session, org_str, raw_alerts)
    elif entity_type == "actions_workflows":
        await _upsert_actions_workflow_summary(session, org_str, items)
    elif entity_type == "mfa_status":
        await _upsert_mfa_status(session, org_str, items)
    elif entity_type == "audit_log":
        await _upsert_audit_log_events(session, org, items)
    elif entity_type in ("repo_commits", "pull_requests", "workflow_runs", "issues", "deployments"):
        await _upsert_activity_events(session, org_str, items)
    elif entity_type == "team_repos":
        await _upsert_team_repos(session, org_str, items)
    elif entity_type == "repo_collaborators":
        await _upsert_repo_collaborators(session, org_str, items)
    elif entity_type == "credential_authorizations":
        await _upsert_credential_authorizations(session, org_str, items)
    elif entity_type == "org_webhooks":
        await _upsert_org_webhooks(session, org_str, items)
    elif entity_type == "repo_webhooks":
        await _upsert_repo_webhooks(session, org_str, items)
    elif entity_type == "actions_permissions":
        await _upsert_actions_permissions(session, org_str, items)
    elif entity_type == "self_hosted_runners":
        await _upsert_self_hosted_runners(session, org_str, items)
    elif entity_type == "deploy_keys":
        await _upsert_deploy_keys(session, org_str, items)
    else:
        logger.error("github_sync.unknown_upsert_entity", entity_type=entity_type)


async def _upsert_audit_log_events(
    session: AsyncSession,
    enterprise_slug: str | None,
    items: list[dict[str, object]],
) -> None:
    """Normalize and insert audit log events into the events table with dedup.

    Each raw event from the GitHub Enterprise audit log API is normalized
    using the same field mapping as ``BaseIngestionWorker._normalize_event()``
    and inserted into the ``events`` table. Deduplication is handled via
    ``_document_id`` (or a computed hash) written to the ``event_dedup`` table.
    """
    import hashlib
    import json

    from sqlalchemy import text

    if not items:
        return

    inserted = 0
    for raw_event in items:
        action = raw_event.get("action")
        if not action:
            continue

        # Parse timestamp
        ts_raw = raw_event.get("@timestamp") or raw_event.get("created_at")
        if ts_raw is None:
            created_at = datetime.now(UTC)
        elif isinstance(ts_raw, (int, float)):
            created_at = datetime.fromtimestamp(ts_raw / 1000, tz=UTC)
        else:
            try:
                created_at = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except ValueError:
                created_at = datetime.now(UTC)

        source_ip = raw_event.get("@ip") or raw_event.get("actor_ip")

        # GeoIP enrichment (best-effort)
        geo_country_code = geo_city = geo_latitude = geo_longitude = None
        geo_is_proxy = False
        if source_ip:
            try:
                from app.services.geoip_service import get_geoip_location

                geo = get_geoip_location(source_ip)
                if geo:
                    geo_country_code = geo.country_code
                    geo_city = geo.city
                    geo_latitude = geo.latitude
                    geo_longitude = geo.longitude
                    geo_is_proxy = geo.is_proxy or False
            except Exception:
                logger.debug("geoip.lookup_failed", source_ip=source_ip)

        # Compute dedup hash from stable fields
        key_fields = {
            "action": raw_event.get("action", ""),
            "actor": raw_event.get("actor", ""),
            "org": raw_event.get("org", ""),
            "repo": raw_event.get("repo", ""),
            "created_at": str(raw_event.get("created_at", "")),
            "source_ip": str(raw_event.get("@ip", raw_event.get("source_ip", ""))),
        }
        canonical = json.dumps(key_fields, sort_keys=True)
        # SHA-256 used for event deduplication, not for protecting secrets.
        # The hash is a deterministic fingerprint for idempotent ingestion.
        dedup_hash = hashlib.sha256(canonical.encode(), usedforsecurity=False).hexdigest()

        # Use GitHub's _document_id if present, otherwise the computed hash
        document_id = raw_event.get("_document_id") or dedup_hash

        # Check for existing dedup record
        existing = await session.execute(
            text("SELECT 1 FROM event_dedup WHERE document_id = :doc_id"),
            {"doc_id": document_id},
        )
        if existing.fetchone():
            continue

        # Strip @-prefixed fields from the data blob
        data = {k: v for k, v in raw_event.items() if not k.startswith("@")}

        # Security: strip secret names from workflow events
        if action == "workflows.prepared_workflow_job":
            secrets_passed = data.get("secrets_passed", [])
            data["secrets_passed_count"] = (
                len(secrets_passed) if isinstance(secrets_passed, list) else 0
            )
            data.pop("secrets_passed", None)

        normalized = {
            "document_id": document_id,
            "action": action,
            "actor": raw_event.get("actor"),
            "actor_id": raw_event.get("actor_id"),
            "actor_is_bot": bool(raw_event.get("actor_is_bot", False)),
            "org": raw_event.get("org"),
            "repo": raw_event.get("repo"),
            "source_ip": source_ip,
            "created_at": created_at,
            "data": json.dumps(data),
            "geo_country_code": geo_country_code,
            "geo_city": geo_city,
            "geo_latitude": geo_latitude,
            "geo_longitude": geo_longitude,
            "geo_is_proxy": geo_is_proxy,
            "user_agent": raw_event.get("user_agent"),
            "ingestion_source": "github_enterprise_sync",
            "source_file_path": f"enterprise/{enterprise_slug or 'unknown'}/audit-log",
        }

        # Insert event
        result = await session.execute(
            text("""
                INSERT INTO events (
                    document_id, action, actor, actor_id, actor_is_bot,
                    org, repo, source_ip, created_at, data,
                    geo_country_code, geo_city, geo_latitude, geo_longitude, geo_is_proxy,
                    user_agent, ingestion_source, source_file_path
                ) VALUES (
                    :document_id, :action, :actor, :actor_id, :actor_is_bot,
                    :org, :repo, :source_ip, :created_at, CAST(:data AS jsonb),
                    :geo_country_code, :geo_city,
                    :geo_latitude, :geo_longitude, :geo_is_proxy,
                    :user_agent, :ingestion_source, :source_file_path
                )
                RETURNING id
            """),
            normalized,
        )
        row = result.fetchone()
        if not row:
            continue
        event_id = row[0]

        # Insert dedup record
        await session.execute(
            text(
                "INSERT INTO event_dedup (document_id, event_id, created_at) "
                "VALUES (:doc_id, :event_id, :ts) ON CONFLICT DO NOTHING"
            ),
            {
                "doc_id": document_id,
                "event_id": event_id,
                "ts": created_at,
            },
        )
        inserted += 1

    await session.commit()

    if inserted:
        logger.info(
            "github_sync.audit_log_events_inserted",
            inserted=inserted,
            total=len(items),
            enterprise=enterprise_slug,
        )


async def _upsert_activity_events(
    session: AsyncSession,
    org_str: str,
    items: list[dict[str, object]],
) -> None:
    """Insert pre-normalized activity events (commits, PRs) into the events table.

    Each item in *items* is already normalized by the ``_fetch_page`` handler
    for ``repo_commits`` or ``pull_requests`` — all required fields are present.
    Deduplication uses the ``document_id`` via the ``event_dedup`` table,
    matching the pattern used by ``_upsert_audit_log_events``.
    """
    from sqlalchemy import text

    if not items:
        return

    inserted = 0
    for event in items:
        document_id = event.get("document_id")
        if not document_id:
            continue

        action = event.get("action")
        if not action:
            continue

        created_at = event.get("created_at")
        if created_at is None:
            created_at = datetime.now(UTC)

        # Check dedup table for existing record
        existing = await session.execute(
            text("SELECT 1 FROM event_dedup WHERE document_id = :doc_id"),
            {"doc_id": document_id},
        )
        if existing.fetchone():
            continue

        data_value = event.get("data", "{}")
        if isinstance(data_value, dict):
            import json as _json

            data_value = _json.dumps(data_value)

        normalized = {
            "document_id": document_id,
            "action": action,
            "actor": event.get("actor"),
            "actor_id": event.get("actor_id"),
            "actor_is_bot": bool(event.get("actor_is_bot", False)),
            "org": event.get("org") or org_str,
            "repo": event.get("repo"),
            "source_ip": None,
            "created_at": created_at,
            "data": data_value,
            "geo_country_code": None,
            "geo_city": None,
            "geo_latitude": None,
            "geo_longitude": None,
            "geo_is_proxy": None,
            "user_agent": None,
            "ingestion_source": event.get("ingestion_source", "github_api_sync"),
            "source_file_path": event.get("source_file_path", f"api/{org_str}/unknown"),
        }

        result = await session.execute(
            text("""
                INSERT INTO events (
                    document_id, action, actor, actor_id, actor_is_bot,
                    org, repo, source_ip, created_at, data,
                    geo_country_code, geo_city, geo_latitude, geo_longitude, geo_is_proxy,
                    user_agent, ingestion_source, source_file_path
                ) VALUES (
                    :document_id, :action, :actor, :actor_id, :actor_is_bot,
                    :org, :repo, :source_ip, :created_at, CAST(:data AS jsonb),
                    :geo_country_code, :geo_city,
                    :geo_latitude, :geo_longitude, :geo_is_proxy,
                    :user_agent, :ingestion_source, :source_file_path
                )
                RETURNING id
            """),
            normalized,
        )
        row = result.fetchone()
        if not row:
            continue
        event_id = row[0]

        await session.execute(
            text(
                "INSERT INTO event_dedup (document_id, event_id, created_at) "
                "VALUES (:doc_id, :event_id, :ts) ON CONFLICT DO NOTHING"
            ),
            {
                "doc_id": document_id,
                "event_id": event_id,
                "ts": created_at,
            },
        )
        inserted += 1

    await session.commit()

    if inserted:
        logger.info(
            "github_sync.activity_events_inserted",
            inserted=inserted,
            total=len(items),
            org=org_str,
        )


async def _upsert_team_repos(session: AsyncSession, org: str, items: list[dict]) -> None:
    """Upsert team-repo access mappings."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgTeamRepo

    for item in items:
        stmt = (
            insert(OrgTeamRepo)
            .values(
                org=org,
                team_slug=item.get("_team_slug", ""),
                repo_name=item.get("name", ""),
                repo_id=item.get("id", 0),
                permission=item.get("_permission", "pull"),
            )
            .on_conflict_do_update(
                constraint="uq_org_team_repos_org_team_repo",
                set_={
                    "repo_id": item.get("id", 0),
                    "permission": item.get("_permission", "pull"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_repo_collaborators(session: AsyncSession, org: str, items: list[dict]) -> None:
    """Upsert direct repo collaborators."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import RepoCollaborator

    for item in items:
        login = item.get("login")
        if not login:
            continue
        stmt = (
            insert(RepoCollaborator)
            .values(
                org=org,
                repo_name=item.get("_repo_name", ""),
                github_login=login,
                github_id=item.get("id"),
                permission=item.get("permission", "read"),
            )
            .on_conflict_do_update(
                constraint="uq_repo_collaborators_org_repo_login",
                set_={
                    "github_id": item.get("id"),
                    "permission": item.get("permission", "read"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_credential_authorizations(
    session: AsyncSession, org: str, items: list[dict]
) -> None:
    """Upsert SAML/SSO credential authorizations."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgCredentialAuthorization

    for item in items:
        cred_id = item.get("credential_id")
        if not cred_id:
            continue
        authorized_at = _parse_gh_dt(item.get("credential_authorized_at"))
        accessed_at = _parse_gh_dt(item.get("credential_accessed_at"))
        stmt = (
            insert(OrgCredentialAuthorization)
            .values(
                org=org,
                github_login=item.get("login", ""),
                credential_id=cred_id,
                credential_type=item.get("credential_type", "unknown"),
                token_last_eight=item.get("token_last_eight"),
                credential_authorized_at=authorized_at,
                credential_accessed_at=accessed_at,
                scopes=item.get("scopes"),
            )
            .on_conflict_do_update(
                constraint="uq_org_credential_auth_org_cred",
                set_={
                    "github_login": item.get("login", ""),
                    "credential_type": item.get("credential_type", "unknown"),
                    "token_last_eight": item.get("token_last_eight"),
                    "credential_authorized_at": authorized_at,
                    "credential_accessed_at": accessed_at,
                    "scopes": item.get("scopes"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_org_webhooks(session: AsyncSession, org: str, items: list[dict]) -> None:
    """Upsert org-level webhooks."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgWebhook

    for item in items:
        hook_id = item.get("id")
        if not hook_id:
            continue
        config = item.get("config", {})
        stmt = (
            insert(OrgWebhook)
            .values(
                org=org,
                hook_id=hook_id,
                name=item.get("name", "web"),
                active=item.get("active", False),
                config_url=config.get("url"),
                config_content_type=config.get("content_type"),
                config_insecure_ssl=config.get("insecure_ssl"),
                events=item.get("events"),
            )
            .on_conflict_do_update(
                constraint="uq_org_webhooks_org_hook",
                set_={
                    "name": item.get("name", "web"),
                    "active": item.get("active", False),
                    "config_url": config.get("url"),
                    "config_content_type": config.get("content_type"),
                    "config_insecure_ssl": config.get("insecure_ssl"),
                    "events": item.get("events"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_repo_webhooks(session: AsyncSession, org: str, items: list[dict]) -> None:
    """Upsert repo-level webhooks."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import RepoWebhook

    for item in items:
        hook_id = item.get("hook_id")
        if not hook_id:
            continue
        stmt = (
            insert(RepoWebhook)
            .values(
                org=org,
                repo_name=item.get("_repo_name", ""),
                hook_id=hook_id,
                name=item.get("name", "web"),
                active=item.get("active", False),
                config_url=item.get("config_url"),
                config_content_type=item.get("config_content_type"),
                config_insecure_ssl=item.get("config_insecure_ssl"),
                events=item.get("events"),
            )
            .on_conflict_do_update(
                constraint="uq_repo_webhooks_org_repo_hook",
                set_={
                    "name": item.get("name", "web"),
                    "active": item.get("active", False),
                    "config_url": item.get("config_url"),
                    "config_content_type": item.get("config_content_type"),
                    "config_insecure_ssl": item.get("config_insecure_ssl"),
                    "events": item.get("events"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_actions_permissions(session: AsyncSession, org: str, items: list[dict]) -> None:
    """Upsert org-level Actions permissions."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgActionsPermissions

    for item in items:
        stmt = (
            insert(OrgActionsPermissions)
            .values(
                org=org,
                enabled_repositories=item.get("enabled_repositories", "all"),
                allowed_actions=item.get("allowed_actions"),
                github_owned_allowed=item.get("github_owned_allowed", True),
                verified_allowed=item.get("verified_allowed", False),
                patterns_allowed=item.get("patterns_allowed"),
            )
            .on_conflict_do_update(
                constraint="uq_org_actions_permissions_org",
                set_={
                    "enabled_repositories": item.get("enabled_repositories", "all"),
                    "allowed_actions": item.get("allowed_actions"),
                    "github_owned_allowed": item.get("github_owned_allowed", True),
                    "verified_allowed": item.get("verified_allowed", False),
                    "patterns_allowed": item.get("patterns_allowed"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_self_hosted_runners(session: AsyncSession, org: str, items: list[dict]) -> None:
    """Upsert org-level self-hosted runners."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import OrgSelfHostedRunner

    for item in items:
        runner_id = item.get("runner_id")
        if not runner_id:
            continue
        stmt = (
            insert(OrgSelfHostedRunner)
            .values(
                org=org,
                runner_id=runner_id,
                name=item.get("name", ""),
                os=item.get("os", "unknown"),
                status=item.get("status", "offline"),
                busy=item.get("busy", False),
                labels=item.get("labels"),
                runner_group_id=item.get("runner_group_id"),
                runner_group_name=item.get("runner_group_name"),
            )
            .on_conflict_do_update(
                constraint="uq_org_self_hosted_runners_org_runner",
                set_={
                    "name": item.get("name", ""),
                    "os": item.get("os", "unknown"),
                    "status": item.get("status", "offline"),
                    "busy": item.get("busy", False),
                    "labels": item.get("labels"),
                    "runner_group_id": item.get("runner_group_id"),
                    "runner_group_name": item.get("runner_group_name"),
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _upsert_deploy_keys(session: AsyncSession, org: str, items: list[dict]) -> None:
    """Upsert repo deploy keys."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import RepoDeployKey

    for item in items:
        key_id = item.get("key_id")
        if not key_id:
            continue
        key_added_at = _parse_gh_dt(item.get("created_at"))
        stmt = (
            insert(RepoDeployKey)
            .values(
                org=org,
                repo_name=item.get("_repo_name", ""),
                key_id=key_id,
                title=item.get("title", ""),
                read_only=item.get("read_only", True),
                key_added_at=key_added_at,
            )
            .on_conflict_do_update(
                constraint="uq_repo_deploy_keys_org_repo_key",
                set_={
                    "title": item.get("title", ""),
                    "read_only": item.get("read_only", True),
                    "key_added_at": key_added_at,
                    "synced_at": text("NOW()"),
                },
            )
        )
        await session.execute(stmt)
    await session.commit()


async def _sync_installation_configs(existing_configs: list, settings: object) -> list:
    """Promote org-level installations into github_app_configs.

    Compares ``github_app_installations`` (synced from the API) with
    ``github_app_configs`` (used by the orchestrator). Any org-level
    installation that exists in the former but not the latter is inserted
    as a new config row so that subsequent syncs use the org-scoped
    installation token — which typically has broader repository access
    than the enterprise-level token.

    Returns the updated list of configs.
    """
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from app.models.github_sync import GitHubAppConfig, GitHubAppInstallation

    app_id = settings.github_app.GITHUB_APP_ID
    existing_inst_ids = {c.installation_id for c in existing_configs}

    async with _make_session_factory()() as session:
        result = await session.execute(
            select(GitHubAppInstallation).where(
                GitHubAppInstallation.app_id == app_id,
                GitHubAppInstallation.target_type == "Organization",
            )
        )
        org_installations = result.scalars().all()

        new_configs = []
        for inst in org_installations:
            if inst.installation_id in existing_inst_ids:
                continue
            stmt = (
                insert(GitHubAppConfig)
                .values(
                    app_id=app_id,
                    installation_id=inst.installation_id,
                    enterprise_slug=None,
                    org_login=inst.target_login,
                    enabled=True,
                )
                .on_conflict_do_update(
                    constraint="uq_github_app_configs_app_install",
                    set_={"org_login": inst.target_login, "enabled": True},
                )
                .returning(GitHubAppConfig)
            )
            row = await session.execute(stmt)
            new_configs.append(row.scalar_one())

        if new_configs:
            await session.commit()
            logger.info(
                "github_sync.promoted_installations",
                count=len(new_configs),
                orgs=[c.org_login for c in new_configs],
            )

        # Reload all configs
        result = await session.execute(
            select(GitHubAppConfig).where(GitHubAppConfig.enabled == True)  # noqa: E712
        )
        return list(result.scalars().all())


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
    private_key = settings.github_app.resolve_private_key()
    if not app_id or not private_key:
        logger.error("github_sync.bootstrap_missing_env", app_id=app_id, has_key=bool(private_key))
        return []

    try:
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
                org_login=acct.get("login") if target == "Organization" else None,
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
