"""Admin settings router — CRUD for the encrypted settings store.

All endpoints require ``sys_admin`` role. Values are masked in responses
based on their sensitivity level.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.schemas.setup import SettingUpdate
from app.services.config_overlay import load_settings_overlay
from app.services.settings_service import (
    delete_setting,
    get_audit_trail,
    list_settings,
    set_setting,
)

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])


@router.get("")
async def list_all_settings(
    category: str | None = Query(None, description="Filter by category"),
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str | None]]:
    """List all settings with masked values."""
    return await list_settings(db, category=category)


@router.get("/audit/trail")
async def get_audit_trail_endpoint(
    setting_key: str | None = Query(None, description="Filter by setting key"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, str | int | None]]:
    """Get the audit trail for setting changes."""
    return await get_audit_trail(db, setting_key=setting_key, limit=limit, offset=offset)


@router.get("/{key}")
async def get_setting_endpoint(
    key: str,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | None]:
    """Get a single setting (masked)."""
    items = await list_settings(db)
    for item in items:
        if item["key"] == key:
            return item
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Setting '{key}' not found",
    )


@router.put("/{key}")
async def update_setting_endpoint(
    key: str,
    payload: SettingUpdate,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update a setting value. Creates audit trail entry and refreshes overlay."""
    await set_setting(
        db,
        key,
        payload.value,
        category=payload.category or "config",
        sensitivity=payload.sensitivity or "config",
        description=payload.description,
        changed_by=current_user.github_login,
    )
    # Refresh the in-memory overlay so changes take effect immediately
    await load_settings_overlay(db)
    return {"status": "ok", "message": f"Setting '{key}' updated"}


@router.delete("/{key}")
async def delete_setting_endpoint(
    key: str,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a setting (reverts to env var default)."""
    deleted = await delete_setting(db, key, changed_by=current_user.github_login)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )
    # Refresh overlay — the env var default will now take effect
    await load_settings_overlay(db)
    return {"status": "ok", "message": f"Setting '{key}' deleted, reverted to env var default"}
