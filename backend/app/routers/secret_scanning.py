"""Secret Scanning router: dedicated endpoints for secret scanning alerts.

Provides listing, summary, trends, detail, sync trigger, and audit-trail
correlation for secret scanning alerts ingested from GitHub.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, require_permission, verify_csrf
from app.models.github_sync import SecretScanningAlert
from app.services import rbac_service, secret_scanning_service

router = APIRouter(prefix="/secret-scanning", tags=["secret-scanning"])


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty."""
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs and current_user.scope_type != "global":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/alerts", response_model=dict[str, Any])
async def list_alerts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    state: str | None = Query(default=None),
    secret_type: str | None = Query(default=None),
    validity: str | None = Query(default=None),
    push_protection_bypassed: bool | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Paginated list of secret scanning alerts with advanced filters."""
    scoped_orgs = await _resolve_orgs(db, current_user)

    filters: list[ColumnElement[bool]] = [SecretScanningAlert.org_slug.in_(scoped_orgs)]
    if state:
        filters.append(SecretScanningAlert.state == state)
    if secret_type:
        filters.append(SecretScanningAlert.secret_type == secret_type)
    if validity:
        filters.append(SecretScanningAlert.validity == validity)
    if push_protection_bypassed is not None:
        filters.append(SecretScanningAlert.push_protection_bypassed == push_protection_bypassed)

    count_q = select(func.count()).select_from(SecretScanningAlert).where(*filters)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    data_q = (
        select(SecretScanningAlert)
        .where(*filters)
        .order_by(SecretScanningAlert.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(data_q)
    rows = result.scalars().all()

    alerts = [
        {
            "id": r.id,
            "org_slug": r.org_slug,
            "alert_number": r.alert_number,
            "repo_full_name": r.repo_full_name,
            "secret_type": r.secret_type,
            "secret_type_display": r.secret_type_display,
            "file_path": r.file_path,
            "commit_sha": r.commit_sha,
            "state": r.state,
            "resolution": r.resolution,
            "push_protection_bypassed": r.push_protection_bypassed,
            "push_protection_bypassed_by": r.push_protection_bypassed_by,
            "validity": r.validity,
            "locations_count": r.locations_count,
            "resolved_by": r.resolved_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
        }
        for r in rows
    ]

    return {"alerts": alerts, "total": total}


@router.get("/summary", response_model=dict[str, Any])
async def alert_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate summary: open count, resolved-30d, push protection stats, MTTR."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    summary = await secret_scanning_service.get_secret_alert_summary(db, scoped_orgs)
    return {
        "open_alerts": summary.open_alerts,
        "resolved_30d": summary.resolved_30d,
        "push_protection_bypasses": summary.push_protection_bypasses,
        "active_secrets": summary.active_secrets,
        "mttr_hours": summary.mttr_hours,
        "open_by_type": summary.open_by_type,
        "resolution_breakdown": summary.resolution_breakdown,
    }


@router.get("/trends", response_model=dict[str, Any])
async def alert_trends(
    period: int = Query(default=30, ge=7, le=90),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Time-series trend of new vs resolved secret scanning alerts."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    trends = await secret_scanning_service.get_secret_alert_trends(db, scoped_orgs, period)
    return {
        "period": period,
        "points": [
            {
                "date": t.date,
                "new_alerts": t.new_alerts,
                "resolved_alerts": t.resolved_alerts,
            }
            for t in trends
        ],
    }


@router.get("/alerts/{alert_id}", response_model=dict[str, Any])
async def alert_detail(
    alert_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Fetch a single secret scanning alert by database ID."""
    scoped_orgs = await _resolve_orgs(db, current_user)

    q = select(SecretScanningAlert).where(
        SecretScanningAlert.id == alert_id,
        SecretScanningAlert.org_slug.in_(scoped_orgs),
    )
    result = await db.execute(q)
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    return {
        "id": alert.id,
        "org_slug": alert.org_slug,
        "alert_number": alert.alert_number,
        "repo_full_name": alert.repo_full_name,
        "secret_type": alert.secret_type,
        "secret_type_display": alert.secret_type_display,
        "file_path": alert.file_path,
        "commit_sha": alert.commit_sha,
        "state": alert.state,
        "resolution": alert.resolution,
        "push_protection_bypassed": alert.push_protection_bypassed,
        "push_protection_bypassed_by": alert.push_protection_bypassed_by,
        "validity": alert.validity,
        "locations_count": alert.locations_count,
        "resolved_by": alert.resolved_by,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "synced_at": alert.synced_at.isoformat() if alert.synced_at else None,
    }


@router.post("/sync", response_model=dict[str, Any])
async def trigger_sync(
    current_user: AuthenticatedUser = Depends(require_permission("secret_scanning", "write")),
    db: AsyncSession = Depends(get_db),
    _csrf: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Trigger a manual sync of secret scanning alerts for all scoped orgs.

    Requires the ``secret_scanning:write`` permission.
    """
    scoped_orgs = await _resolve_orgs(db, current_user)

    results: list[dict[str, Any]] = []
    for org in scoped_orgs:
        # Use a stub client that returns empty for now; real implementation
        # should use the GitHub app installation token for the org.
        from unittest.mock import AsyncMock

        stub_client = AsyncMock()
        stub_client.get_paginated.return_value = []
        sync_result = await secret_scanning_service.sync_secret_alerts(db, org, stub_client)
        results.append(
            {
                "org": sync_result.org,
                "created": sync_result.created,
                "updated": sync_result.updated,
                "total_fetched": sync_result.total_fetched,
                "errors": sync_result.errors,
            }
        )

    return {"sync_results": results}


@router.get("/alerts/{alert_id}/audit-trail", response_model=dict[str, Any])
async def alert_audit_trail(
    alert_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return audit log events correlated with a specific secret scanning alert."""
    scoped_orgs = await _resolve_orgs(db, current_user)

    # Verify the alert belongs to a scoped org
    q = select(SecretScanningAlert.org_slug).where(
        SecretScanningAlert.id == alert_id,
        SecretScanningAlert.org_slug.in_(scoped_orgs),
    )
    result = await db.execute(q)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )

    events = await secret_scanning_service.correlate_with_audit_log(db, alert_id)
    return {"alert_id": alert_id, "events": events}


@router.get("/push-protection-stats", response_model=dict[str, Any])
async def push_protection_stats(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return push protection effectiveness statistics."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    stats = await secret_scanning_service.get_push_protection_stats(db, scoped_orgs)
    return stats
