"""Events router: list, get, and raw payload endpoints."""

from __future__ import annotations

from time import perf_counter

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.schemas.audit_event import EventListParams, EventListResponse, EventResponse
from app.services.event_service import get_event_by_id, get_raw_payload, list_events
from app.services.rbac_service import get_user_scope

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=EventListResponse)
async def list_events_endpoint(
    params: EventListParams = Depends(),
    current_user: AuthenticatedUser = Depends(require_permission("events", "view")),
    db: AsyncSession = Depends(get_db),
    response: Response = None,  # type: ignore[assignment]
) -> EventListResponse:
    """List audit events with filtering, pagination, and scope enforcement."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    start = perf_counter()
    try:
        events, total, count_is_estimated, next_cursor = await list_events(
            db, params=params, scope=scope
        )
    except ValueError as exc:
        # Invalid cursor
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        # Catch statement_timeout (QueryCanceledError surfaces as a generic DB exception)
        exc_name = type(exc).__name__
        if "QueryCanceled" in exc_name or "QueryCanceledError" in exc_name:
            logger.warning("events_query_timeout", params=params.model_dump(exclude_none=True))
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Query timed out. Try narrowing your filters.",
            ) from exc
        raise

    elapsed_ms = int((perf_counter() - start) * 1000)
    if response is not None:
        response.headers["X-Query-Time-Ms"] = str(elapsed_ms)

    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in events],
        total=total,
        page=params.page,
        page_size=params.page_size,
        has_next=(
            (params.page * params.page_size < total) if not params.cursor else bool(next_cursor)
        ),
        count_is_estimated=count_is_estimated,
        next_cursor=next_cursor,
    )


@router.get("/{event_id}", response_model=EventResponse)
async def get_event_endpoint(
    event_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("events", "view")),
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
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the raw (original) payload for an event. Restricted to sys_admin."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    payload = await get_raw_payload(db, event_id=event_id, scope=scope)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw payload not found")
    return {"event_id": event_id, "raw_payload": payload.raw_json}
