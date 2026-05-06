"""Event service: scoped event queries against the TimescaleDB hypertable."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent, EventRawPayload
from app.schemas.audit_event import EventListParams
from app.services.rbac_service import OrgRepoScope, apply_client_filters, inject_scope_predicate

logger = structlog.get_logger(__name__)


async def list_events(
    session: AsyncSession,
    params: EventListParams,
    scope: OrgRepoScope,
) -> tuple[list[AuditEvent], int]:
    """Return (events, total_count) filtered by params and scoped to user's RBAC scope."""
    base_stmt = select(AuditEvent)

    # Mandatory RBAC scope injection — this cannot be bypassed by client params
    base_stmt = inject_scope_predicate(
        base_stmt,
        scope,
        AuditEvent.org,
        AuditEvent.repo,  # type: ignore[arg-type]
    )

    # Optional client-supplied narrowing filters
    base_stmt = apply_client_filters(
        base_stmt,
        scope,
        params.org,
        params.repo,
        AuditEvent.org,
        AuditEvent.repo,  # type: ignore[arg-type]
    )

    # Track whether user-supplied narrowing filters are active
    has_narrowing_filters = False

    # Additional filters
    if params.actor:
        base_stmt = base_stmt.where(AuditEvent.actor == params.actor)
        has_narrowing_filters = True
    if params.action:
        if params.action.endswith(".*"):
            ns = params.action[:-2]
            base_stmt = base_stmt.where(AuditEvent.namespace == ns)
        else:
            base_stmt = base_stmt.where(AuditEvent.action == params.action)
        has_narrowing_filters = True
    if params.namespace:
        base_stmt = base_stmt.where(AuditEvent.namespace == params.namespace)
        has_narrowing_filters = True
    if params.source_ip:
        base_stmt = base_stmt.where(
            func.host(AuditEvent.source_ip) == params.source_ip  # type: ignore[arg-type]
        )
        has_narrowing_filters = True
    if params.since:
        base_stmt = base_stmt.where(AuditEvent.created_at >= params.since)
        has_narrowing_filters = True
    if params.until:
        base_stmt = base_stmt.where(AuditEvent.created_at < params.until)
        has_narrowing_filters = True
    if params.actor_is_bot is not None:
        base_stmt = base_stmt.where(AuditEvent.actor_is_bot == params.actor_is_bot)
        has_narrowing_filters = True
    if params.geo_country_code:
        base_stmt = base_stmt.where(AuditEvent.geo_country_code == params.geo_country_code)
        has_narrowing_filters = True

    # Count total results — use fast estimated count when no narrowing filters
    if has_narrowing_filters:
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total: int = (await session.execute(count_stmt)).scalar_one()
    else:
        # Use pg_class reltuples for a fast approximate count on unfiltered queries
        est_result = await session.execute(
            text("SELECT reltuples::bigint FROM pg_class WHERE relname = 'events'")
        )
        row = est_result.scalar_one_or_none()
        total = max(int(row), 0) if row else 0

    # Ordering
    sort_columns = {
        "created_at": AuditEvent.created_at,
        "action": AuditEvent.action,
        "actor": AuditEvent.actor,
        "repo": AuditEvent.repo,
    }
    if params.sort.endswith("_asc"):
        col_key = params.sort[:-4]
        ascending = True
    else:
        col_key = params.sort[:-5]
        ascending = False
    sort_col = sort_columns.get(col_key, AuditEvent.created_at)
    order_clause = sort_col.asc() if ascending else sort_col.desc()
    if col_key != "created_at":
        base_stmt = base_stmt.order_by(order_clause, AuditEvent.created_at.desc())
    else:
        base_stmt = base_stmt.order_by(order_clause)

    # Pagination
    offset = (params.page - 1) * params.page_size
    base_stmt = base_stmt.offset(offset).limit(params.page_size)

    result = await session.execute(base_stmt)
    events = list(result.scalars().all())
    return events, total


async def get_event_by_id(
    session: AsyncSession,
    event_id: int,
    scope: OrgRepoScope,
) -> AuditEvent | None:
    """Fetch a single event by ID, enforcing RBAC scope."""
    stmt = select(AuditEvent).where(AuditEvent.id == event_id)
    stmt = inject_scope_predicate(stmt, scope, AuditEvent.org, AuditEvent.repo)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_raw_payload(
    session: AsyncSession,
    event_id: int,
    scope: OrgRepoScope,
) -> dict[str, Any] | None:
    """Fetch raw payload for event, after verifying RBAC scope via events table."""
    # First verify the event is in scope
    event = await get_event_by_id(session, event_id, scope)
    if event is None:
        return None

    stmt = select(EventRawPayload.raw_json).where(EventRawPayload.event_id == event_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row
