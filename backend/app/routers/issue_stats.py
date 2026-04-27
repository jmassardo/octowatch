"""Issue stats router: per-org and per-repo issue metrics.

Provides endpoints for viewing issue opened/closed counts and average
time-to-close grouped by organization and repository.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.services import issue_stats_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/issue-stats", tags=["issue-stats"])


@router.get("/by-org")
async def get_issue_stats_by_org(
    window_days: int = Query(default=30, ge=1, le=365),
    org: str | None = Query(None, description="Filter to a specific organization"),
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return issue opened/closed counts and avg time-to-close grouped by org."""
    rows = await issue_stats_service.get_issue_stats_by_org(
        db,
        window_days=window_days,
        org=org,
    )

    total_opened = sum(r["opened"] for r in rows)
    total_closed = sum(r["closed"] for r in rows)

    return {
        "window_days": window_days,
        "total_opened": total_opened,
        "total_closed": total_closed,
        "orgs": rows,
    }


@router.get("/by-repo")
async def get_issue_stats_by_repo(
    window_days: int = Query(default=30, ge=1, le=365),
    org: str | None = Query(None, description="Filter to a specific organization"),
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return issue opened/closed counts and avg time-to-close grouped by org and repo."""
    rows = await issue_stats_service.get_issue_stats_by_repo(
        db,
        window_days=window_days,
        org=org,
    )

    total_opened = sum(r["opened"] for r in rows)
    total_closed = sum(r["closed"] for r in rows)

    return {
        "window_days": window_days,
        "total_opened": total_opened,
        "total_closed": total_closed,
        "repos": rows,
    }
