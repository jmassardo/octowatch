"""Router for per-organization configuration.

GET  /orgs/{org_slug}/config — returns config (any authenticated user)
PATCH /orgs/{org_slug}/config — updates config (sys_admin only)
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, require_role, verify_csrf
from app.models.org_config import OrgConfig
from app.schemas.org_config import OrgConfigResponse, OrgConfigUpdate

logger = structlog.get_logger(__name__)

COST_PER_SEAT_DEFAULT = 19.0

router = APIRouter(prefix="/orgs", tags=["org-config"])


@router.get("/{org_slug}/config", response_model=OrgConfigResponse)
async def get_org_config(
    org_slug: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgConfigResponse:
    """Return the configuration for an organization.

    Falls back to global defaults when no row exists.
    """
    result = await db.execute(select(OrgConfig).where(OrgConfig.org_slug == org_slug))
    row = result.scalar_one_or_none()

    if row is None:
        return OrgConfigResponse(
            org_slug=org_slug,
            copilot_cost_per_seat=COST_PER_SEAT_DEFAULT,
        )

    return OrgConfigResponse(
        org_slug=row.org_slug,
        copilot_cost_per_seat=(
            row.copilot_cost_per_seat
            if row.copilot_cost_per_seat is not None
            else COST_PER_SEAT_DEFAULT
        ),
    )


@router.patch(
    "/{org_slug}/config",
    response_model=OrgConfigResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_org_config(
    org_slug: str,
    payload: OrgConfigUpdate,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> OrgConfigResponse:
    """Update the configuration for an organization.

    Creates the config row if it does not exist (upsert).
    Only ``sys_admin`` users may call this endpoint.
    """
    result = await db.execute(select(OrgConfig).where(OrgConfig.org_slug == org_slug))
    row = result.scalar_one_or_none()

    if row is None:
        row = OrgConfig(
            org_slug=org_slug,
            copilot_cost_per_seat=payload.copilot_cost_per_seat,
        )
        db.add(row)
    else:
        row.copilot_cost_per_seat = payload.copilot_cost_per_seat
        row.updated_at = datetime.now(tz=UTC)

    await db.commit()
    await db.refresh(row)

    logger.info(
        "org_config.updated",
        org_slug=org_slug,
        copilot_cost_per_seat=payload.copilot_cost_per_seat,
        changed_by=current_user.github_login,
    )

    return OrgConfigResponse(
        org_slug=row.org_slug,
        copilot_cost_per_seat=(
            row.copilot_cost_per_seat
            if row.copilot_cost_per_seat is not None
            else COST_PER_SEAT_DEFAULT
        ),
    )
