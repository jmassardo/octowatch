"""Suggestions router: typeahead/autocomplete data for actions, fields, and actors."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
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


@router.get("/actions", response_model=dict[str, Any])
async def suggest_actions(
    current_user: AuthenticatedUser = Depends(require_permission("suggestions", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Return distinct action values from events visible to the current user."""
    scoped_orgs = await get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        return {"actions": []}

    result = await db.execute(
        text(
            "SELECT DISTINCT action FROM events"
            " WHERE org = ANY(:scoped_orgs)"
            " ORDER BY action LIMIT 500"
        ),
        {"scoped_orgs": scoped_orgs},
    )
    actions = [row[0] for row in result.fetchall()]
    return {"actions": actions}


@router.get("/fields", response_model=dict[str, Any])
async def suggest_fields(
    current_user: AuthenticatedUser = Depends(require_permission("suggestions", "view")),
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


@router.get("/actors", response_model=dict[str, Any])
async def suggest_actors(
    current_user: AuthenticatedUser = Depends(require_permission("suggestions", "view")),
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
            " ORDER BY actor LIMIT 500"
        ),
        {"scoped_orgs": scoped_orgs},
    )
    actors = [row[0] for row in result.fetchall()]
    return {"actors": actors}


@router.get("/repos", response_model=dict[str, Any])
async def suggest_repos(
    current_user: AuthenticatedUser = Depends(require_permission("suggestions", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Return distinct repo values from events visible to the current user."""
    scoped_orgs = await get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        return {"repos": []}

    result = await db.execute(
        text(
            "SELECT DISTINCT repo FROM events"
            " WHERE org = ANY(:scoped_orgs)"
            " AND repo IS NOT NULL AND repo != ''"
            " ORDER BY repo LIMIT 500"
        ),
        {"scoped_orgs": scoped_orgs},
    )
    repos = [row[0] for row in result.fetchall()]
    return {"repos": repos}


@router.get("/orgs", response_model=dict[str, Any])
async def suggest_orgs(
    current_user: AuthenticatedUser = Depends(require_permission("suggestions", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Return distinct org values from events visible to the current user."""
    scoped_orgs = await get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        return {"orgs": []}

    result = await db.execute(
        text(
            "SELECT DISTINCT org FROM events"
            " WHERE org = ANY(:scoped_orgs)"
            " AND org IS NOT NULL AND org != ''"
            " ORDER BY org LIMIT 500"
        ),
        {"scoped_orgs": scoped_orgs},
    )
    orgs = [row[0] for row in result.fetchall()]
    return {"orgs": orgs}


@router.get("/namespaces", response_model=dict[str, Any])
async def suggest_namespaces(
    current_user: AuthenticatedUser = Depends(require_permission("suggestions", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[str]]:
    """Return distinct namespace values from events visible to the current user."""
    scoped_orgs = await get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        return {"namespaces": []}

    result = await db.execute(
        text(
            "SELECT DISTINCT namespace FROM events"
            " WHERE org = ANY(:scoped_orgs)"
            " AND namespace IS NOT NULL AND namespace != ''"
            " ORDER BY namespace LIMIT 500"
        ),
        {"scoped_orgs": scoped_orgs},
    )
    namespaces = [row[0] for row in result.fetchall()]
    return {"namespaces": namespaces}
