"""Admin retention router — manage centralised data retention policies.

All endpoints require ``admin_settings`` / ``admin`` permission.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.services import retention_service
from app.utils.client_ip import get_client_ip

router = APIRouter(prefix="/admin/retention", tags=["admin-retention"])


class RetentionPolicyUpdate(BaseModel):
    """Request body for updating a retention policy."""

    retention_days: int = Field(..., ge=1, le=3650, description="New retention period in days")


class RetentionPolicyResponse(BaseModel):
    """Response for a single retention policy."""

    data_type: str
    category: str
    display_name: str
    description: str
    retention_days: int
    minimum_days: int
    is_system: bool
    updated_by: str | None = None
    updated_at: str | None = None
    table_name: str
    time_column: str
    row_count: int = 0
    size_bytes: int = 0


@router.get("", response_model=list[RetentionPolicyResponse])
async def list_retention_policies(
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all retention policies with optional storage statistics."""
    policies = await retention_service.get_all_policies(db)

    # Attempt to fetch storage stats; failures are non-fatal
    try:
        stats = await retention_service.get_storage_stats(db)
    except Exception:
        stats = {}

    result: list[dict[str, Any]] = []
    for data_type, policy in sorted(policies.items()):
        entry = {**policy}
        data_stats = stats.get(data_type, {})
        entry["row_count"] = data_stats.get("row_count", 0)
        entry["size_bytes"] = data_stats.get("size_bytes", 0)
        result.append(entry)
    return result


@router.patch(
    "/{data_type}",
    response_model=dict[str, Any],
    dependencies=[Depends(verify_csrf)],
)
async def update_retention_policy(
    data_type: str,
    payload: RetentionPolicyUpdate,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update the retention period for a data type.

    Validates against the enforced minimum_days.  Changes are audit-logged.
    """
    ip = get_client_ip(request)
    try:
        result = await retention_service.update_retention_policy(
            db,
            data_type,
            payload.retention_days,
            user_login=current_user.github_login,
            ip_address=ip,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {"status": "ok", **result}
