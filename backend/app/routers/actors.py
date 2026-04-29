"""Actors router: profile, activity, detections, and geo endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import AuthenticatedUser, get_db, require_permission
from app.models.audit_event import AuditEvent
from app.models.detection import Detection
from app.schemas.actor import (
    ActorDetectionListResponse,
    ActorDetectionResponse,
    ActorEventListResponse,
    ActorEventResponse,
    ActorLocation,
    ActorLocationsResponse,
    ActorProfile,
)
from app.services.rbac_service import get_user_scope

router = APIRouter(prefix="/actors", tags=["actors"])

_SEVERITY_RISK_WEIGHT = {"critical": 25, "high": 15, "medium": 8, "low": 3, "info": 1}
_OPEN_STATUSES = ("open", "investigating")


def _compute_risk_score(
    detection_count: int,
    severity_counts: dict[str, int],
) -> tuple[float, str]:
    """Compute actor risk score from detection severity distribution.

    Score range: 0–100. Levels: low (0–25), medium (26–50), high (51–75), critical (76–100).
    """
    if detection_count == 0:
        return 0.0, "low"

    weighted = sum(
        _SEVERITY_RISK_WEIGHT.get(sev, 1) * count for sev, count in severity_counts.items()
    )
    # Normalize: cap at 100
    score = min(100.0, round(weighted * 1.0, 1))

    if score >= 76:
        level = "critical"
    elif score >= 51:
        level = "high"
    elif score >= 26:
        level = "medium"
    else:
        level = "low"

    return score, level


@router.get("/{login}", response_model=ActorProfile)
async def get_actor_profile(
    login: str,
    current_user: AuthenticatedUser = Depends(require_permission("events", "view")),
    db: AsyncSession = Depends(get_db),
) -> ActorProfile:
    """Build a comprehensive actor profile from events and detections."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    # Event aggregates
    event_stmt = select(
        func.count(AuditEvent.id).label("event_count"),
        func.min(AuditEvent.created_at).label("first_seen"),
        func.max(AuditEvent.created_at).label("last_seen"),
    ).where(AuditEvent.actor == login)
    if scope.scoped_orgs:
        event_stmt = event_stmt.where(AuditEvent.org.in_(scope.scoped_orgs))
    event_row = (await db.execute(event_stmt)).one()

    # Org memberships from events
    org_stmt = select(distinct(AuditEvent.org)).where(
        AuditEvent.actor == login, AuditEvent.org.isnot(None)
    )
    if scope.scoped_orgs:
        org_stmt = org_stmt.where(AuditEvent.org.in_(scope.scoped_orgs))
    org_result = await db.execute(org_stmt)
    org_memberships = [row[0] for row in org_result.all() if row[0]]

    # Detection aggregates
    det_stmt = select(
        func.count(Detection.id).label("detection_count"),
        func.count(case((Detection.severity == "critical", 1))).label("critical_count"),
        func.count(case((Detection.severity == "high", 1))).label("high_count"),
        func.count(case((Detection.severity == "medium", 1))).label("medium_count"),
        func.count(case((Detection.severity == "low", 1))).label("low_count"),
    ).where(Detection.actor == login)
    if scope.scoped_orgs:
        det_stmt = det_stmt.where(Detection.org.in_(scope.scoped_orgs))
    det_row = (await db.execute(det_stmt)).one()

    severity_counts = {
        "critical": det_row.critical_count,
        "high": det_row.high_count,
        "medium": det_row.medium_count,
        "low": det_row.low_count,
    }
    risk_score, risk_level = _compute_risk_score(det_row.detection_count, severity_counts)

    return ActorProfile(
        login=login,
        avatar_url=f"https://github.com/{login}.png",
        org_memberships=org_memberships,
        detection_count=det_row.detection_count,
        event_count=event_row.event_count,
        risk_score=risk_score,
        risk_level=risk_level,
        first_seen=event_row.first_seen,
        last_seen=event_row.last_seen,
    )


@router.get("/{login}/events", response_model=ActorEventListResponse)
async def get_actor_events(
    login: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(require_permission("events", "view")),
    db: AsyncSession = Depends(get_db),
) -> ActorEventListResponse:
    """Paginated reverse-chronological events for an actor."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    base_stmt = select(AuditEvent).where(AuditEvent.actor == login)
    if scope.scoped_orgs:
        base_stmt = base_stmt.where(AuditEvent.org.in_(scope.scoped_orgs))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = base_stmt.order_by(AuditEvent.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    events = result.scalars().all()

    return ActorEventListResponse(
        items=[ActorEventResponse.model_validate(e) for e in events],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size < total),
    )


@router.get("/{login}/detections", response_model=ActorDetectionListResponse)
async def get_actor_detections(
    login: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(require_permission("events", "view")),
    db: AsyncSession = Depends(get_db),
) -> ActorDetectionListResponse:
    """Paginated detections where this actor is the subject."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    base_stmt = (
        select(Detection).options(selectinload(Detection.rule)).where(Detection.actor == login)
    )
    if scope.scoped_orgs:
        base_stmt = base_stmt.where(Detection.org.in_(scope.scoped_orgs))

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = base_stmt.order_by(Detection.triggered_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    detections = result.scalars().all()

    items = []
    for d in detections:
        items.append(
            ActorDetectionResponse(
                id=d.id,
                title=d.title,
                severity=d.severity,
                status=d.status,
                triggered_at=d.triggered_at,
                rule_name=d.rule.name if d.rule else None,
                org=d.org,
                repo=d.repo,
            )
        )

    return ActorDetectionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size < total),
    )


@router.get("/{login}/locations", response_model=ActorLocationsResponse)
async def get_actor_locations(
    login: str,
    current_user: AuthenticatedUser = Depends(require_permission("events", "view")),
    db: AsyncSession = Depends(get_db),
) -> ActorLocationsResponse:
    """Aggregated geo locations for an actor."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    stmt = select(
        AuditEvent.geo_country_code,
        AuditEvent.geo_city,
        AuditEvent.geo_latitude,
        AuditEvent.geo_longitude,
        func.count(AuditEvent.id).label("event_count"),
        func.max(AuditEvent.created_at).label("last_seen"),
    ).where(
        AuditEvent.actor == login,
        AuditEvent.geo_country_code.isnot(None),
    )
    if scope.scoped_orgs:
        stmt = stmt.where(AuditEvent.org.in_(scope.scoped_orgs))

    stmt = stmt.group_by(
        AuditEvent.geo_country_code,
        AuditEvent.geo_city,
        AuditEvent.geo_latitude,
        AuditEvent.geo_longitude,
    ).order_by(func.count(AuditEvent.id).desc())

    result = await db.execute(stmt)
    rows = result.all()

    total_events = sum(row.event_count for row in rows)
    locations = [
        ActorLocation(
            country_code=row.geo_country_code,
            city=row.geo_city,
            latitude=row.geo_latitude,
            longitude=row.geo_longitude,
            event_count=row.event_count,
            last_seen=row.last_seen,
        )
        for row in rows
    ]

    return ActorLocationsResponse(locations=locations, total_events=total_events)
