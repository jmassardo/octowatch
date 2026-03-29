"""Feature flags router — returns enabled/disabled state of optional platform features."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, require_role
from app.services.settings_service import get_setting, set_setting

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/features", tags=["features"])

# Default feature states — conservative defaults prevent API errors
FEATURE_DEFAULTS: dict[str, bool] = {
    "copilot_insights": False,
    "velocity": True,
    "dev_activity": True,
    "org_health": True,
}


@router.get("")
async def get_features(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Return the current state of all feature toggles."""
    result: dict[str, bool] = {}
    for key, default in FEATURE_DEFAULTS.items():
        stored = await get_setting(db, f"feature_{key}")
        if stored is not None:
            result[key] = stored.lower() in ("true", "1", "yes", "on")
        else:
            result[key] = default
    return result


@router.put("")
async def update_features(
    payload: dict[str, bool],
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Update feature toggles. Only sys_admin can change these."""
    updated: dict[str, bool] = {}
    for key, enabled in payload.items():
        if key not in FEATURE_DEFAULTS:
            continue
        await set_setting(
            db,
            f"feature_{key}",
            str(enabled).lower(),
            category="features",
            sensitivity="config",
            description=f"Feature toggle: {key}",
            changed_by=current_user.github_login,
        )
        updated[key] = enabled
        logger.info(
            "feature_toggle.updated",
            feature=key,
            enabled=enabled,
            changed_by=current_user.github_login,
        )
    return updated
