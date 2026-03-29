"""Suggestions router: typeahead/autocomplete data for actions, fields, and actors."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.services.rbac_service import get_scoped_orgs

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

# Static fields that are always available in the event schema
_STATIC_FIELDS: list[str] = [
    "actor",
    "action",
    "org",
    "repo",
    "source_ip",
    "created_at",
]


@router.get("/actions")
async def suggest_actions(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Return distinct action values from events visible to the current user."""
    scoped_orgs = await get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        return {"actions": []}

    result = await db.execute(
        text("SELECT DISTINCT action FROM events WHERE org = ANY(:scoped_orgs) ORDER BY action"),
        {"scoped_orgs": scoped_orgs},
    )
    actions = [row[0] for row in result.fetchall()]
    return {"actions": actions}


@router.get("/fields")
async def suggest_fields(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Return known field paths for use in rule conditions.

    Combines static event columns with dynamic keys found in the JSONB ``data``
    column, prefixed with ``data.``.
    """
    scoped_orgs = await get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        return {"fields": list(_STATIC_FIELDS)}

    result = await db.execute(
        text(
            "SELECT DISTINCT jsonb_object_keys(data) AS key FROM events"
            " WHERE org = ANY(:scoped_orgs)"
            " LIMIT 100"
        ),
        {"scoped_orgs": scoped_orgs},
    )
    dynamic_keys = sorted(f"data.{row[0]}" for row in result.fetchall())
    return {"fields": list(_STATIC_FIELDS) + dynamic_keys}


@router.get("/actors")
async def suggest_actors(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Return distinct actor values from events visible to the current user."""
    scoped_orgs = await get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        return {"actors": []}

    result = await db.execute(
        text(
            "SELECT DISTINCT actor FROM events"
            " WHERE org = ANY(:scoped_orgs)"
            " AND actor IS NOT NULL AND actor != ''"
            " ORDER BY actor"
        ),
        {"scoped_orgs": scoped_orgs},
    )
    actors = [row[0] for row in result.fetchall()]
    return {"actors": actors}
