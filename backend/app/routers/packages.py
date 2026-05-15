"""GitHub Packages monitoring router: security posture and operations visibility.

Endpoints expose package inventory, security alerts, summary dashboards,
and stale container image detection. All endpoints enforce RBAC via
``require_permission`` and scope results to the caller's orgs.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.services import package_monitoring_service as svc
from app.services import rbac_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/packages", tags=["packages"])


# ── RBAC helper ──────────────────────────────────────────────────────────────


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


# ── Response schemas ─────────────────────────────────────────────────────────


class PackageSummaryResponse(BaseModel):
    """Dashboard summary of packages monitoring."""

    total_packages: int
    public_packages: int
    private_packages: int
    by_type: dict[str, int] = Field(default_factory=dict)
    newly_public: int = 0
    stale_images: int = 0
    open_alerts: int = 0


class PackageAlertResponse(BaseModel):
    """A single package security alert."""

    id: int
    package_id: int
    package_name: str
    package_org: str
    alert_type: str
    severity: str
    message: str
    detected_at: str
    resolved_at: str | None
    status: str


class PackageAlertListResponse(BaseModel):
    """Paginated list of package alerts."""

    alerts: list[PackageAlertResponse]
    total: int


class PackageInventoryItemResponse(BaseModel):
    """A single package in the inventory."""

    id: int
    org: str
    repo: str | None
    name: str
    package_type: str
    visibility: str
    owner: str | None
    versions_count: int
    latest_version: str | None
    last_published_at: str | None
    is_stale: bool
    published_outside_actions: bool
    published_by_external: bool


class PackageInventoryResponse(BaseModel):
    """Paginated package inventory."""

    items: list[PackageInventoryItemResponse]
    total: int
    page: int
    page_size: int


class StaleImageResponse(BaseModel):
    """A stale container image."""

    id: int
    org: str
    repo: str | None
    name: str
    last_published_at: str | None
    days_since_rebuild: int
    owner: str | None


class StaleImageListResponse(BaseModel):
    """List of stale container images."""

    images: list[StaleImageResponse]
    total: int
    threshold_days: int


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=PackageSummaryResponse,
    summary="Package monitoring summary",
    description="Dashboard summary: totals, public/private breakdown, alerts.",
)
async def get_summary(
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> PackageSummaryResponse:
    """Return the aggregate package monitoring summary."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    summary = await svc.get_packages_summary(db, scoped_orgs)
    return PackageSummaryResponse(
        total_packages=summary.total_packages,
        public_packages=summary.public_packages,
        private_packages=summary.private_packages,
        by_type=summary.by_type,
        newly_public=summary.newly_public,
        stale_images=summary.stale_images,
        open_alerts=summary.open_alerts,
    )


@router.get(
    "/alerts",
    response_model=PackageAlertListResponse,
    summary="Package security alerts",
    description="Filtered, paginated security alerts from package monitoring.",
)
async def get_alerts(
    alert_status: str | None = Query(None, alias="status", description="open or resolved"),
    severity: str | None = Query(None, description="high, medium, or low"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> PackageAlertListResponse:
    """Return filtered, paginated package security alerts."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    result = await svc.get_package_alerts(
        db,
        scoped_orgs,
        alert_status=alert_status,
        severity=severity,
        page=page,
        page_size=page_size,
    )
    return PackageAlertListResponse(
        alerts=[
            PackageAlertResponse(
                id=a.id,
                package_id=a.package_id,
                package_name=a.package_name,
                package_org=a.package_org,
                alert_type=a.alert_type,
                severity=a.severity,
                message=a.message,
                detected_at=a.detected_at,
                resolved_at=a.resolved_at,
                status=a.status,
            )
            for a in result.alerts
        ],
        total=result.total,
    )


@router.get(
    "/inventory",
    response_model=PackageInventoryResponse,
    summary="Package inventory",
    description="Paginated inventory of all packages with optional type/visibility filters.",
)
async def get_inventory(
    package_type: str | None = Query(None, alias="type", description="npm, maven, docker, etc."),
    visibility: str | None = Query(None, description="public or private"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> PackageInventoryResponse:
    """Return the full paginated package inventory."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    result = await svc.get_package_inventory(
        db,
        scoped_orgs,
        package_type=package_type,
        visibility=visibility,
        page=page,
        page_size=page_size,
    )
    return PackageInventoryResponse(
        items=[
            PackageInventoryItemResponse(
                id=item.id,
                org=item.org,
                repo=item.repo,
                name=item.name,
                package_type=item.package_type,
                visibility=item.visibility,
                owner=item.owner,
                versions_count=item.versions_count,
                latest_version=item.latest_version,
                last_published_at=item.last_published_at,
                is_stale=item.is_stale,
                published_outside_actions=item.published_outside_actions,
                published_by_external=item.published_by_external,
            )
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/stale-images",
    response_model=StaleImageListResponse,
    summary="Stale container images",
    description="Container images not rebuilt within the configured threshold.",
)
async def get_stale_images(
    days: int = Query(90, ge=1, le=365, description="Days threshold for staleness"),
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> StaleImageListResponse:
    """Return container images not rebuilt within the threshold."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    result = await svc.get_stale_images(db, scoped_orgs, days_threshold=days)
    return StaleImageListResponse(
        images=[
            StaleImageResponse(
                id=img.id,
                org=img.org,
                repo=img.repo,
                name=img.name,
                last_published_at=img.last_published_at,
                days_since_rebuild=img.days_since_rebuild,
                owner=img.owner,
            )
            for img in result.images
        ],
        total=result.total,
        threshold_days=result.threshold_days,
    )
