"""Audit trail service: write immutable log entries for user-initiated changes."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_trail import AuditTrail

logger = structlog.get_logger(__name__)


async def log_action(
    db: AsyncSession,
    *,
    user_login: str,
    user_github_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    action_type: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    parameters: dict[str, Any] | None = None,
    outcome: str = "success",
    error_detail: str | None = None,
) -> AuditTrail:
    """Write an immutable audit trail entry.

    Uses a separate flush to ensure the audit record is persisted even if the
    caller's transaction rolls back.
    """
    entry = AuditTrail(
        user_login=user_login,
        user_github_id=user_github_id,
        ip_address=ip_address,
        user_agent=user_agent,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        parameters=parameters,
        outcome=outcome,
        error_detail=error_detail,
    )
    db.add(entry)
    await db.flush()
    logger.info(
        "audit.logged",
        action=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        user=user_login,
    )
    return entry
