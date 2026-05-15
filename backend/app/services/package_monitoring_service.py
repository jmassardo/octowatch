"""Package monitoring service.

Provides summary, alerts, inventory, and stale image queries for GitHub
Packages security and operations monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class PackageSummary:
    """Dashboard-level summary of package monitoring."""

    total_packages: int
    public_packages: int
    private_packages: int
    by_type: dict[str, int] = field(default_factory=dict)
    newly_public: int = 0
    stale_images: int = 0
    open_alerts: int = 0


@dataclass
class PackageAlertRecord:
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


@dataclass
class PackageAlertList:
    """Paginated list of package alerts."""

    alerts: list[PackageAlertRecord] = field(default_factory=list)
    total: int = 0


@dataclass
class PackageInventoryItem:
    """A single package in the inventory view."""

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


@dataclass
class PackageInventory:
    """Paginated package inventory."""

    items: list[PackageInventoryItem] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


@dataclass
class StaleImageRecord:
    """A stale container image."""

    id: int
    org: str
    repo: str | None
    name: str
    last_published_at: str | None
    days_since_rebuild: int
    owner: str | None


@dataclass
class StaleImageList:
    """List of stale container images."""

    images: list[StaleImageRecord] = field(default_factory=list)
    total: int = 0
    threshold_days: int = 90


# ── Helpers ──────────────────────────────────────────────────────────────────


def _org_filter(
    scoped_orgs: list[str],
    *,
    table_alias: str = "p",
) -> tuple[str, dict[str, Any]]:
    """Build an org-scoping SQL fragment and parameter dict."""
    if not scoped_orgs:
        return "", {}
    placeholders = ", ".join(f":org_{i}" for i in range(len(scoped_orgs)))
    params = {f"org_{i}": org for i, org in enumerate(scoped_orgs)}
    return f"AND {table_alias}.org IN ({placeholders})", params


# ── Service functions ────────────────────────────────────────────────────────


async def get_packages_summary(
    session: AsyncSession,
    scoped_orgs: list[str],
) -> PackageSummary:
    """Return dashboard-level summary of packages for scoped orgs."""
    org_filter, params = _org_filter(scoped_orgs)

    # Total packages
    total_q = await session.execute(
        text(f"SELECT count(*) FROM packages p WHERE 1=1 {org_filter}"),
        params,
    )
    total = total_q.scalar() or 0

    # Public vs private
    vis_q = await session.execute(
        text(
            f"SELECT visibility, count(*) as cnt FROM packages p "
            f"WHERE 1=1 {org_filter} GROUP BY visibility"
        ),
        params,
    )
    vis_counts: dict[str, int] = {row.visibility: row.cnt for row in vis_q.fetchall()}
    public_count = vis_counts.get("public", 0)
    private_count = vis_counts.get("private", 0)

    # By type
    type_q = await session.execute(
        text(
            f"SELECT package_type, count(*) as cnt FROM packages p "
            f"WHERE 1=1 {org_filter} GROUP BY package_type"
        ),
        params,
    )
    by_type: dict[str, int] = {row.package_type: row.cnt for row in type_q.fetchall()}

    # Newly public (changed to public in last 7 days based on alerts)
    newly_q = await session.execute(
        text(
            "SELECT count(*) FROM package_alerts a "
            "JOIN packages p ON a.package_id = p.id "
            f"WHERE a.alert_type = 'public_exposure' AND a.status = 'open' "
            f"AND a.detected_at >= NOW() - INTERVAL '7 days' {org_filter}"
        ),
        params,
    )
    newly_public = newly_q.scalar() or 0

    # Stale images count
    stale_q = await session.execute(
        text(
            f"SELECT count(*) FROM packages p "
            f"WHERE p.is_stale = true AND p.package_type = 'container' {org_filter}"
        ),
        params,
    )
    stale_count = stale_q.scalar() or 0

    # Open alerts count
    alerts_q = await session.execute(
        text(
            "SELECT count(*) FROM package_alerts a "
            f"JOIN packages p ON a.package_id = p.id WHERE a.status = 'open' {org_filter}"
        ),
        params,
    )
    open_alerts = alerts_q.scalar() or 0

    return PackageSummary(
        total_packages=total,
        public_packages=public_count,
        private_packages=private_count,
        by_type=by_type,
        newly_public=newly_public,
        stale_images=stale_count,
        open_alerts=open_alerts,
    )


async def get_package_alerts(
    session: AsyncSession,
    scoped_orgs: list[str],
    *,
    alert_status: str | None = None,
    severity: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> PackageAlertList:
    """Return filtered, paginated package security alerts."""
    org_filter, params = _org_filter(scoped_orgs)

    where_clauses = f"WHERE 1=1 {org_filter}"
    if alert_status:
        where_clauses += " AND a.status = :alert_status"
        params["alert_status"] = alert_status
    if severity:
        where_clauses += " AND a.severity = :severity"
        params["severity"] = severity

    # Count
    count_q = await session.execute(
        text(
            f"SELECT count(*) FROM package_alerts a "
            f"JOIN packages p ON a.package_id = p.id {where_clauses}"
        ),
        params,
    )
    total = count_q.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    rows_q = await session.execute(
        text(
            f"SELECT a.id, a.package_id, p.name as package_name, p.org as package_org, "
            f"a.alert_type, a.severity, a.message, a.detected_at, a.resolved_at, a.status "
            f"FROM package_alerts a "
            f"JOIN packages p ON a.package_id = p.id {where_clauses} "
            f"ORDER BY a.detected_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    rows = rows_q.fetchall()

    alerts = [
        PackageAlertRecord(
            id=row.id,
            package_id=row.package_id,
            package_name=row.package_name,
            package_org=row.package_org,
            alert_type=row.alert_type,
            severity=row.severity,
            message=row.message,
            detected_at=row.detected_at.isoformat() if row.detected_at else "",
            resolved_at=row.resolved_at.isoformat() if row.resolved_at else None,
            status=row.status,
        )
        for row in rows
    ]

    return PackageAlertList(alerts=alerts, total=total)


async def get_package_inventory(
    session: AsyncSession,
    scoped_orgs: list[str],
    *,
    package_type: str | None = None,
    visibility: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> PackageInventory:
    """Return paginated inventory of packages with optional filters."""
    org_filter, params = _org_filter(scoped_orgs)

    where_clauses = f"WHERE 1=1 {org_filter}"
    if package_type:
        where_clauses += " AND p.package_type = :package_type"
        params["package_type"] = package_type
    if visibility:
        where_clauses += " AND p.visibility = :visibility"
        params["visibility"] = visibility

    # Count
    count_q = await session.execute(
        text(f"SELECT count(*) FROM packages p {where_clauses}"),
        params,
    )
    total = count_q.scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    rows_q = await session.execute(
        text(
            f"SELECT p.id, p.org, p.repo, p.name, p.package_type, p.visibility, "
            f"p.owner, p.versions_count, p.latest_version, p.last_published_at, "
            f"p.is_stale, p.published_outside_actions, p.published_by_external "
            f"FROM packages p {where_clauses} "
            f"ORDER BY p.updated_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    rows = rows_q.fetchall()

    items = [
        PackageInventoryItem(
            id=row.id,
            org=row.org,
            repo=row.repo,
            name=row.name,
            package_type=row.package_type,
            visibility=row.visibility,
            owner=row.owner,
            versions_count=row.versions_count,
            latest_version=row.latest_version,
            last_published_at=row.last_published_at.isoformat() if row.last_published_at else None,
            is_stale=row.is_stale,
            published_outside_actions=row.published_outside_actions,
            published_by_external=row.published_by_external,
        )
        for row in rows
    ]

    return PackageInventory(items=items, total=total, page=page, page_size=page_size)


async def get_stale_images(
    session: AsyncSession,
    scoped_orgs: list[str],
    *,
    days_threshold: int = 90,
) -> StaleImageList:
    """Return container images not rebuilt within the threshold days."""
    org_filter, params = _org_filter(scoped_orgs)
    params["threshold_days"] = days_threshold

    count_q = await session.execute(
        text(
            f"SELECT count(*) FROM packages p "
            f"WHERE p.package_type = 'container' "
            f"AND (p.last_published_at IS NULL OR "
            f"    p.last_published_at < NOW() - INTERVAL '1 day' * :threshold_days) "
            f"{org_filter}"
        ),
        params,
    )
    total = count_q.scalar() or 0

    rows_q = await session.execute(
        text(
            f"SELECT p.id, p.org, p.repo, p.name, p.last_published_at, p.owner, "
            f"COALESCE(EXTRACT(EPOCH FROM (NOW() - p.last_published_at)) / 86400, 9999)::int "
            f"  as days_since "
            f"FROM packages p "
            f"WHERE p.package_type = 'container' "
            f"AND (p.last_published_at IS NULL OR "
            f"    p.last_published_at < NOW() - INTERVAL '1 day' * :threshold_days) "
            f"{org_filter} "
            f"ORDER BY days_since DESC"
        ),
        params,
    )
    rows = rows_q.fetchall()

    images = [
        StaleImageRecord(
            id=row.id,
            org=row.org,
            repo=row.repo,
            name=row.name,
            last_published_at=row.last_published_at.isoformat() if row.last_published_at else None,
            days_since_rebuild=row.days_since,
            owner=row.owner,
        )
        for row in rows
    ]

    return StaleImageList(images=images, total=total, threshold_days=days_threshold)
