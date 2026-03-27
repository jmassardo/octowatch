"""Events router: list, get, and raw payload endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.schemas.audit_event import EventListParams, EventListResponse, EventResponse
from app.services.event_service import get_event_by_id, get_raw_payload, list_events
from app.services.rbac_service import get_user_scope

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventListResponse)
async def list_events_endpoint(
    params: EventListParams = Depends(),
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> EventListResponse:
    """List audit events with filtering, pagination, and scope enforcement."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    events, total = await list_events(db, params=params, scope=scope)
    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in events],
        total=total,
        page=params.page,
        page_size=params.page_size,
        has_next=(params.page * params.page_size < total),
    )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event_endpoint(
    event_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> EventResponse:
    """Get a single audit event by ID (scope-checked)."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    event = await get_event_by_id(db, event_id=event_id, scope=scope)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return EventResponse.model_validate(event)


@router.get("/{event_id}/raw", response_model=dict)
async def get_raw_payload_endpoint(
    event_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the raw (original) payload for an event. Restricted to sys_admin."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    payload = await get_raw_payload(db, event_id=event_id, scope=scope)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw payload not found")
    return {"event_id": event_id, "raw_payload": payload.raw_json}
