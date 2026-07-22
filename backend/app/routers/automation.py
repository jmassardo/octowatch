"""Automation targets CRUD and delivery history API."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_permission

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])


# ─── Request/Response models ─────────────────────────────────────────────────


class CreateTargetRequest(BaseModel):
    """Request body for creating an automation target."""

    name: str
    target_type: str = Field(pattern="^(webhook|repository_dispatch)$")
    webhook_url: str | None = None
    webhook_secret: str | None = None
    webhook_headers: dict[str, Any] | None = None
    dispatch_repo: str | None = None
    dispatch_event_type: str | None = None
    dispatch_token_env_var: str | None = None
    rule_ids: list[int] | None = None
    rule_categories: list[str] | None = None
    severity_filter: list[str] | None = None
    org_filter: list[str] | None = None
    is_catch_all: bool = False
    rate_limit_per_minute: int = 100
    max_retries: int = 3
    enabled: bool = True


class UpdateTargetRequest(BaseModel):
    """Request body for partially updating an automation target."""

    name: str | None = None
    webhook_url: str | None = None
    webhook_secret: str | None = None
    webhook_headers: dict[str, Any] | None = None
    dispatch_repo: str | None = None
    dispatch_event_type: str | None = None
    dispatch_token_env_var: str | None = None
    rule_ids: list[int] | None = None
    rule_categories: list[str] | None = None
    severity_filter: list[str] | None = None
    org_filter: list[str] | None = None
    is_catch_all: bool | None = None
    rate_limit_per_minute: int | None = None
    max_retries: int | None = None
    enabled: bool | None = None


class TestTargetRequest(BaseModel):
    """Send a test payload to verify target configuration."""

    detection_id: int | None = None  # If set, use real detection; otherwise send sample


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/targets")
async def list_targets(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("automation", "read")),
) -> dict[str, Any]:
    """List all automation targets."""
    result = await db.execute(
        text("""
            SELECT id, name, target_type, webhook_url, dispatch_repo,
                   dispatch_event_type, rule_ids, rule_categories,
                   severity_filter, org_filter, is_catch_all,
                   rate_limit_per_minute, max_retries, enabled,
                   created_by, created_at, updated_at
            FROM automation_targets
            ORDER BY created_at DESC
        """)
    )
    targets = [dict(row._mapping) for row in result.fetchall()]
    # Don't expose secrets
    for t in targets:
        t.pop("webhook_secret", None)
    return {"targets": targets}


@router.get("/targets/{target_id}")
async def get_target(
    target_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("automation", "read")),
) -> dict[str, Any]:
    """Get a single automation target."""
    result = await db.execute(
        text("SELECT * FROM automation_targets WHERE id = :id"),
        {"id": target_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Target not found")
    target = dict(row._mapping)
    target.pop("webhook_secret", None)  # Don't expose
    return target


@router.post("/targets", status_code=201)
async def create_target(
    body: CreateTargetRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("automation", "write")),
) -> dict[str, Any]:
    """Create a new automation target."""
    # Validate based on target_type
    if body.target_type == "webhook" and not body.webhook_url:
        raise HTTPException(400, "webhook_url required for webhook targets")
    if body.target_type == "repository_dispatch" and not body.dispatch_repo:
        raise HTTPException(400, "dispatch_repo required for repository_dispatch targets")

    logger.info(
        "automation.target.creating",
        name=body.name,
        target_type=body.target_type,
    )

    result = await db.execute(
        text("""
            INSERT INTO automation_targets
                (name, target_type, webhook_url, webhook_secret, webhook_headers,
                 dispatch_repo, dispatch_event_type, dispatch_token_env_var,
                 rule_ids, rule_categories, severity_filter, org_filter,
                 is_catch_all, rate_limit_per_minute, max_retries, enabled, created_by)
            VALUES
                (:name, :target_type, :webhook_url, :webhook_secret, :webhook_headers,
                 :dispatch_repo, :dispatch_event_type, :dispatch_token_env_var,
                 :rule_ids, :rule_categories, :severity_filter, :org_filter,
                 :is_catch_all, :rate_limit_per_minute, :max_retries, :enabled, 'admin')
            RETURNING id
        """),
        {
            "name": body.name,
            "target_type": body.target_type,
            "webhook_url": body.webhook_url,
            "webhook_secret": body.webhook_secret,
            "webhook_headers": body.webhook_headers,
            "dispatch_repo": body.dispatch_repo,
            "dispatch_event_type": body.dispatch_event_type,
            "dispatch_token_env_var": body.dispatch_token_env_var,
            "rule_ids": body.rule_ids,
            "rule_categories": body.rule_categories,
            "severity_filter": body.severity_filter,
            "org_filter": body.org_filter,
            "is_catch_all": body.is_catch_all,
            "rate_limit_per_minute": body.rate_limit_per_minute,
            "max_retries": body.max_retries,
            "enabled": body.enabled,
        },
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(500, "Failed to create target")
    await db.commit()

    logger.info("automation.target.created", target_id=row[0])
    return {"id": row[0], "status": "created"}


@router.patch("/targets/{target_id}")
async def update_target(
    body: UpdateTargetRequest,
    target_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("automation", "write")),
) -> dict[str, Any]:
    """Update an automation target."""
    # Build dynamic SET clause from non-None fields
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = target_id

    result = await db.execute(
        text(
            f"UPDATE automation_targets SET {set_clauses}, "  # noqa: S608
            "updated_at = NOW() WHERE id = :id RETURNING id"
        ),
        updates,
    )
    if not result.fetchone():
        raise HTTPException(404, "Target not found")
    await db.commit()

    logger.info("automation.target.updated", target_id=target_id)
    return {"id": target_id, "status": "updated"}


@router.delete("/targets/{target_id}")
async def delete_target(
    target_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("automation", "write")),
) -> dict[str, Any]:
    """Delete an automation target and all its delivery records."""
    result = await db.execute(
        text("DELETE FROM automation_targets WHERE id = :id RETURNING id"),
        {"id": target_id},
    )
    if not result.fetchone():
        raise HTTPException(404, "Target not found")
    await db.commit()

    logger.info("automation.target.deleted", target_id=target_id)
    return {"id": target_id, "status": "deleted"}


@router.post("/targets/{target_id}/test")
async def test_target(
    body: TestTargetRequest,
    target_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("automation", "write")),
) -> dict[str, Any]:
    """Send a test/dry-run payload to an automation target."""
    from app.services.automation_service import (
        build_alert_payload,
        deliver_repository_dispatch,
        deliver_webhook,
        dispatch_automation,
    )

    if body.detection_id:
        result = await dispatch_automation(db, body.detection_id, dry_run=True)
        return {"status": "test_sent", **result}

    # Build a sample payload
    sample_detection = {
        "id": 0,
        "triggered_at": "2025-01-01T00:00:00Z",
        "severity": "medium",
        "confidence": "medium",
        "confidence_score": 0.75,
        "status": "open",
        "actor": "test-actor",
        "org": "test-org",
        "repo": "test-org/test-repo",
    }
    sample_rule = {
        "id": 0,
        "name": "Test Rule",
        "slug": "test-rule",
        "category": "test",
        "logic_type": "threshold",
    }
    payload = build_alert_payload(sample_detection, sample_rule)

    # Load target
    target_result = await db.execute(
        text("SELECT * FROM automation_targets WHERE id = :id"),
        {"id": target_id},
    )
    target_row = target_result.fetchone()
    if not target_row:
        raise HTTPException(404, "Target not found")
    target = dict(target_row._mapping)

    if target["target_type"] == "webhook":
        status_code, error = await deliver_webhook(target, payload)
    else:
        status_code, error = await deliver_repository_dispatch(target, payload)

    return {
        "status": "test_sent",
        "response_code": status_code,
        "error": error,
    }


@router.get("/deliveries")
async def list_deliveries(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("automation", "read")),
    target_id: int | None = Query(None),
    detection_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """List automation delivery history with optional filters."""
    filters: list[str] = []
    params: dict[str, Any] = {"limit": limit}

    if target_id:
        filters.append("ad.target_id = :target_id")
        params["target_id"] = target_id
    if detection_id:
        filters.append("ad.detection_id = :detection_id")
        params["detection_id"] = detection_id
    if status:
        filters.append("ad.status = :status")
        params["status"] = status

    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    result = await db.execute(
        text(
            f"SELECT ad.id, ad.target_id, ad.detection_id, ad.status, "  # noqa: S608
            "ad.attempts, ad.last_attempt_at, ad.next_retry_at, "
            "ad.response_code, ad.error_message, ad.payload_hash, "
            "ad.is_dry_run, ad.created_at, "
            "at.name as target_name, at.target_type "
            "FROM automation_deliveries ad "
            "JOIN automation_targets at ON ad.target_id = at.id "
            f"{where} "
            "ORDER BY ad.created_at DESC "
            "LIMIT :limit"
        ),
        params,
    )
    deliveries = [dict(row._mapping) for row in result.fetchall()]
    return {"deliveries": deliveries}


@router.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(
    delivery_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_permission("automation", "write")),
) -> dict[str, Any]:
    """Manually retry a failed delivery."""
    # Reset delivery for retry
    result = await db.execute(
        text("""
            UPDATE automation_deliveries
            SET status = 'failed', next_retry_at = NOW()
            WHERE id = :id AND status IN ('failed', 'exhausted')
            RETURNING detection_id
        """),
        {"id": delivery_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Delivery not found or not in failed state")
    await db.commit()

    # Queue retry immediately
    from app.workers.automation_worker import retry_failed_deliveries_task

    retry_failed_deliveries_task.delay()

    logger.info("automation.delivery.retry_queued", delivery_id=delivery_id)
    return {"id": delivery_id, "status": "retry_queued"}
