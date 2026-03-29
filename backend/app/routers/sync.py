"""Admin sync router — /api/v1/admin/sync/*"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
    SyncScheduleResponse,
    SyncScheduleUpdateRequest,
    SyncTriggerRequest,
    SyncTriggerResponse,
)
from app.services.settings_service import get_setting, set_setting

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
    # Auto-expire stale runs (stuck > 2 hours with no worker processing)
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    await db.execute(
        update(EnterpriseSyncRun)
        .where(
            EnterpriseSyncRun.status.in_(["pending", "running"]),
            EnterpriseSyncRun.created_at < stale_cutoff,
        )
        .values(
            status="failed",
            completed_at=datetime.now(timezone.utc),
            error_message="Auto-expired: no progress for 2+ hours",
        )
    )

    # Check for in-progress run
    running = await db.execute(
        select(EnterpriseSyncRun)
        .where(EnterpriseSyncRun.status.in_(["pending", "running"]))
        .limit(1)
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
    db.add(
        AuditTrail(
            user_login=current_user.github_login,
            action_type="github_sync.trigger",
            resource_type="enterprise_sync_run",
            resource_id=str(run_id),
            parameters={"scope": body.scope},
            outcome="success",
        )
    )
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


@router.get("/status", response_model=SyncRunDetail | None)
async def get_sync_status(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncRunDetail | None:
    """Return the current running sync or the most recently completed run."""
    result = await db.execute(
        select(EnterpriseSyncRun).order_by(EnterpriseSyncRun.created_at.desc()).limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        return None

    cursors_result = await db.execute(
        select(EnterpriseSyncEntityCursor).where(EnterpriseSyncEntityCursor.run_id == run.id)
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
    result = await db.execute(select(EnterpriseSyncRun).where(EnterpriseSyncRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")

    cursors_result = await db.execute(
        select(EnterpriseSyncEntityCursor).where(EnterpriseSyncEntityCursor.run_id == run_id)
    )
    cursors = cursors_result.scalars().all()
    detail = SyncRunDetail.model_validate(run)
    detail.cursors = [CursorRow.model_validate(c) for c in cursors]
    return detail


@router.delete("/runs/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def cancel_run(
    run_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Cancel a pending or running sync run.

    Revokes the Celery task and marks the run as "cancelled".
    """
    result = await db.execute(select(EnterpriseSyncRun).where(EnterpriseSyncRun.id == run_id))
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
    db.add(
        AuditTrail(
            user_login=current_user.github_login,
            action_type="github_sync.cancel",
            resource_type="enterprise_sync_run",
            resource_id=str(run_id),
            outcome="success",
        )
    )
    await db.commit()


@router.get("/config", response_model=SyncConfigResponse)
async def get_sync_config(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncConfigResponse:
    """Return the current sync configuration.

    NEVER exposes GITHUB_APP_PRIVATE_KEY_PATH or any token value.
    """
    configs_result = await db.execute(
        select(GitHubAppConfig).where(GitHubAppConfig.enabled == True)  # noqa: E712
    )
    configs = configs_result.scalars().all()
    installation_ids = [{"org": c.org_login, "installation_id": c.installation_id} for c in configs]
    return SyncConfigResponse(
        app_id=settings.github_app.GITHUB_APP_ID,
        enterprise_slug=settings.github_app.GITHUB_ENTERPRISE_SLUG,
        installation_ids=installation_ids,
        sync_enabled=settings.github_app.GITHUB_SYNC_ENABLED,
        interval_days=settings.github_app.GITHUB_SYNC_INTERVAL_DAYS,
        orgs=settings.github_app.sync_orgs_list,
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
        settings.github_app.GITHUB_SYNC_ENABLED = body.sync_enabled
        await db.execute(update(GitHubAppConfig).values(enabled=body.sync_enabled))

    if body.interval_days is not None:
        settings.github_app.GITHUB_SYNC_INTERVAL_DAYS = body.interval_days

    if body.orgs is not None:
        settings.github_app.GITHUB_SYNC_ORGS = ",".join(body.orgs)

    db.add(
        AuditTrail(
            user_login=current_user.github_login,
            action_type="github_sync.config_update",
            resource_type="github_app_config",
            parameters=body.model_dump(exclude_none=True),
            outcome="success",
        )
    )
    await db.commit()
    return await get_sync_config(current_user=current_user, db=db)


# ── Schedule endpoints ────────────────────────────────────────────────────────

_SCHEDULE_KEYS = (
    "sync_schedule_enabled",
    "sync_schedule_interval_hours",
    "sync_schedule_scope",
)
_SCHEDULE_DEFAULTS: dict[str, str] = {
    "sync_schedule_enabled": "false",
    "sync_schedule_interval_hours": "24",
    "sync_schedule_scope": "full",
}


@router.get("/schedule", response_model=SyncScheduleResponse)
async def get_sync_schedule(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncScheduleResponse:
    """Get current sync schedule configuration.

    Reads from app_settings table using keys prefixed with ``sync_schedule_``.
    Returns sensible defaults when no DB settings exist.
    """
    raw: dict[str, str] = {}
    for key in _SCHEDULE_KEYS:
        value = await get_setting(db, key)
        raw[key] = value if value is not None else _SCHEDULE_DEFAULTS[key]

    enabled = raw["sync_schedule_enabled"].lower() == "true"
    interval_hours = int(raw["sync_schedule_interval_hours"])
    scope = raw["sync_schedule_scope"]

    # Compute next_run_at and last_completed_at from EnterpriseSyncRun table
    last_result = await db.execute(
        select(EnterpriseSyncRun)
        .where(EnterpriseSyncRun.status == "completed")
        .order_by(EnterpriseSyncRun.completed_at.desc())
        .limit(1)
    )
    last_run = last_result.scalar_one_or_none()

    last_completed_at = last_run.completed_at if last_run else None
    next_run_at = None
    if enabled and last_completed_at:
        next_run_at = last_completed_at + timedelta(hours=interval_hours)

    return SyncScheduleResponse(
        enabled=enabled,
        interval_hours=interval_hours,
        scope=scope,
        next_run_at=next_run_at,
        last_completed_at=last_completed_at,
    )


@router.put("/schedule", response_model=SyncScheduleResponse)
async def update_sync_schedule(
    body: SyncScheduleUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SyncScheduleResponse:
    """Update sync schedule configuration.

    Writes to app_settings and logs to audit trail. Only provided fields
    are updated; omitted fields retain their current value.
    """
    changes: dict[str, str] = {}

    if body.enabled is not None:
        value = "true" if body.enabled else "false"
        await set_setting(
            db,
            "sync_schedule_enabled",
            value,
            category="sync",
            sensitivity="config",
            description="Whether scheduled sync is enabled",
            changed_by=current_user.github_login,
        )
        changes["enabled"] = value

    if body.interval_hours is not None:
        value = str(body.interval_hours)
        await set_setting(
            db,
            "sync_schedule_interval_hours",
            value,
            category="sync",
            sensitivity="config",
            description="Sync schedule interval in hours",
            changed_by=current_user.github_login,
        )
        changes["interval_hours"] = value

    if body.scope is not None:
        await set_setting(
            db,
            "sync_schedule_scope",
            body.scope,
            category="sync",
            sensitivity="config",
            description="Scope for scheduled sync runs",
            changed_by=current_user.github_login,
        )
        changes["scope"] = body.scope

    # Operational audit trail entry
    db.add(
        AuditTrail(
            user_login=current_user.github_login,
            action_type="github_sync.schedule_update",
            resource_type="sync_schedule",
            parameters=changes,
            outcome="success",
        )
    )
    await db.commit()

    logger.info(
        "sync.schedule_updated",
        changes=changes,
        user=current_user.github_login,
    )

    return await get_sync_schedule(current_user=current_user, db=db)
