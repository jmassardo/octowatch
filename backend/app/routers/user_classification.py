"""User behavior classification router.

Provides endpoints for persona distribution summaries, paginated user
classifications, and triggering manual classification runs.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.services import rbac_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/user-classification", tags=["user-classification"])


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty."""
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs and current_user.scope_type != "global":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


@router.get("/summary", response_model=dict[str, Any])
async def classification_summary(
    current_user: AuthenticatedUser = Depends(require_permission("user_classification", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return persona distribution summary for scoped orgs."""
    from app.services.user_classification_service import get_classification_summary

    scoped_orgs = await _resolve_orgs(db, current_user)
    return await get_classification_summary(db, scoped_orgs)


@router.get("/users", response_model=dict[str, Any])
async def list_classified_users(
    persona: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_permission("user_classification", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return paginated user classifications with optional persona filter."""
    from app.services.user_classification_service import get_user_classifications

    scoped_orgs = await _resolve_orgs(db, current_user)
    return await get_user_classifications(
        db, scoped_orgs, persona=persona, page=page, page_size=page_size
    )


@router.post("/run", response_model=dict[str, Any])
async def trigger_classification_run(
    window_days: int = Query(default=90, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("user_classification", "manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger a manual classification run for all scoped orgs."""
    from app.services.user_classification_service import classify_users

    scoped_orgs = await _resolve_orgs(db, current_user)
    if not scoped_orgs:
        return {"status": "ok", "orgs_processed": 0, "users_classified": 0}

    total_classified = 0
    for org in scoped_orgs:
        count = await classify_users(db=db, org=org, window_days=window_days)
        total_classified += count

    logger.info(
        "user_classification.manual_run",
        actor=current_user.github_login,
        orgs=len(scoped_orgs),
        users_classified=total_classified,
    )

    return {
        "status": "ok",
        "orgs_processed": len(scoped_orgs),
        "users_classified": total_classified,
    }
