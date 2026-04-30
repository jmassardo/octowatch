"""Audit log query router: paginated, filterable view of the internal audit trail.

The audit log is immutable — no UPDATE or DELETE endpoints are provided.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.models.audit_trail import AuditTrail
from app.schemas.team import AuditLogEntryResponse, AuditLogListResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/audit-log", tags=["admin-audit"])

MAX_EXPORT_ROWS = 100_000


@router.get("", response_model=AuditLogListResponse)
async def list_audit_log(
    current_user: AuthenticatedUser = Depends(require_permission("audit_log", "view")),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    actor: str | None = Query(None, description="Filter by actor login"),
    action: str | None = Query(None, description="Filter by action (supports prefix match with *)"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    outcome: str | None = Query(None, description="Filter by outcome (success/denied/error)"),
    start_date: datetime | None = Query(None, description="Filter from this date (inclusive)"),
    end_date: datetime | None = Query(None, description="Filter until this date (inclusive)"),
) -> AuditLogListResponse:
    """Query the audit log with pagination and filters."""
    stmt = select(AuditTrail)
    count_stmt = select(func.count()).select_from(AuditTrail)

    # Apply filters
    if actor:
        stmt = stmt.where(AuditTrail.user_login == actor)
        count_stmt = count_stmt.where(AuditTrail.user_login == actor)
    if action:
        if action.endswith("*"):
            prefix = action[:-1]
            stmt = stmt.where(AuditTrail.action_type.startswith(prefix))
            count_stmt = count_stmt.where(AuditTrail.action_type.startswith(prefix))
        else:
            stmt = stmt.where(AuditTrail.action_type == action)
            count_stmt = count_stmt.where(AuditTrail.action_type == action)
    if resource_type:
        stmt = stmt.where(AuditTrail.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditTrail.resource_type == resource_type)
    if outcome:
        stmt = stmt.where(AuditTrail.outcome == outcome)
        count_stmt = count_stmt.where(AuditTrail.outcome == outcome)
    if start_date:
        stmt = stmt.where(AuditTrail.timestamp >= start_date)
        count_stmt = count_stmt.where(AuditTrail.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(AuditTrail.timestamp <= end_date)
        count_stmt = count_stmt.where(AuditTrail.timestamp <= end_date)

    # Get total count
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    stmt = stmt.order_by(AuditTrail.timestamp.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    items = [
        AuditLogEntryResponse(
            id=e.id,
            timestamp=e.timestamp,
            actor=e.user_login,
            action=e.action_type,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            details=e.parameters,
            ip_address=str(e.ip_address) if e.ip_address else None,
            user_agent=e.user_agent,
            outcome=e.outcome,
        )
        for e in entries
    ]

    return AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
    )


@router.get("/export")
async def export_audit_log(
    current_user: AuthenticatedUser = Depends(require_permission("audit_log", "export")),
    db: AsyncSession = Depends(get_db),
    actor: str | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    outcome: str | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
) -> StreamingResponse:
    """Export audit log as CSV (max 100k rows)."""
    stmt = select(AuditTrail)

    # Apply same filters as list endpoint
    if actor:
        stmt = stmt.where(AuditTrail.user_login == actor)
    if action:
        if action.endswith("*"):
            prefix = action[:-1]
            stmt = stmt.where(AuditTrail.action_type.startswith(prefix))
        else:
            stmt = stmt.where(AuditTrail.action_type == action)
    if resource_type:
        stmt = stmt.where(AuditTrail.resource_type == resource_type)
    if outcome:
        stmt = stmt.where(AuditTrail.outcome == outcome)
    if start_date:
        stmt = stmt.where(AuditTrail.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(AuditTrail.timestamp <= end_date)

    # Check count first to enforce limit
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    if total > MAX_EXPORT_ROWS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Export exceeds maximum of {MAX_EXPORT_ROWS:,} rows "
                f"({total:,} matched). Please narrow your filters."
            ),
        )

    stmt = stmt.order_by(AuditTrail.timestamp.desc()).limit(MAX_EXPORT_ROWS)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "timestamp",
            "actor",
            "action",
            "resource_type",
            "resource_id",
            "outcome",
            "ip_address",
            "user_agent",
            "details",
        ]
    )
    for e in entries:
        writer.writerow(
            [
                e.id,
                e.timestamp.isoformat() if e.timestamp else "",
                e.user_login,
                e.action_type,
                e.resource_type or "",
                e.resource_id or "",
                e.outcome,
                str(e.ip_address) if e.ip_address else "",
                e.user_agent or "",
                str(e.parameters) if e.parameters else "",
            ]
        )

    output.seek(0)

    logger.info(
        "audit_log.export",
        user=current_user.github_login,
        row_count=len(entries),
    )

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=audit_log_export.csv",
        },
    )
