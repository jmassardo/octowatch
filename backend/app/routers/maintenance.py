"""Admin maintenance mode endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import (
    AuthenticatedUser,
    get_current_user,
    get_db,
    require_role,
    verify_csrf,
)
from app.schemas.maintenance import (
    MaintenanceStatusResponse,
    MaintenanceToggleRequest,
    MaintenanceUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.config_overlay import load_settings_overlay
from app.services.maintenance_service import (
    MaintenanceStatus,
    get_maintenance_status,
    save_maintenance_status,
)
from app.utils.client_ip import get_client_ip

router = APIRouter(prefix="/admin/maintenance", tags=["maintenance"])


def _to_response(status: MaintenanceStatus) -> MaintenanceStatusResponse:
    return MaintenanceStatusResponse(
        enabled=status.enabled,
        message=status.message,
        severity=status.severity,
        block_writes=status.block_writes,
        started_at=status.started_at,
        estimated_end=status.estimated_end,
    )


@router.get("", response_model=MaintenanceStatusResponse)
async def get_maintenance_status_endpoint(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceStatusResponse:
    """Return the current maintenance mode status for any authenticated user."""

    del current_user
    return _to_response(await get_maintenance_status(db))


@router.put("", response_model=MaintenanceStatusResponse, dependencies=[Depends(verify_csrf)])
async def update_maintenance_status_endpoint(
    payload: MaintenanceUpdateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceStatusResponse:
    """Update the full maintenance mode configuration."""

    saved = await save_maintenance_status(
        db,
        MaintenanceStatus(
            enabled=payload.enabled,
            message=payload.message,
            severity=payload.severity,
            block_writes=payload.block_writes,
            estimated_end=payload.estimated_end,
        ),
        changed_by=current_user.github_login,
    )
    await load_settings_overlay(db)
    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="maintenance.update",
        resource_type="maintenance",
        resource_id="global",
        parameters={
            "enabled": saved.enabled,
            "severity": saved.severity,
            "block_writes": saved.block_writes,
            "estimated_end": saved.estimated_end.isoformat() if saved.estimated_end else None,
        },
    )
    await db.commit()
    return _to_response(saved)


@router.post(
    "/toggle",
    response_model=MaintenanceStatusResponse,
    dependencies=[Depends(verify_csrf)],
)
async def toggle_maintenance_status_endpoint(
    request: Request,
    payload: MaintenanceToggleRequest | None = Body(default=None),
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceStatusResponse:
    """Quickly toggle maintenance mode on or off."""

    current = await get_maintenance_status(db)
    requested = payload.enabled if payload is not None else None
    enabled = (not current.enabled) if requested is None else requested
    saved = await save_maintenance_status(
        db,
        MaintenanceStatus(
            enabled=enabled,
            message=current.message,
            severity=current.severity,
            block_writes=current.block_writes,
            estimated_end=current.estimated_end,
            started_at=current.started_at,
        ),
        changed_by=current_user.github_login,
    )
    await load_settings_overlay(db)
    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="maintenance.toggle",
        resource_type="maintenance",
        resource_id="global",
        parameters={"enabled": saved.enabled},
    )
    await db.commit()
    return _to_response(saved)
