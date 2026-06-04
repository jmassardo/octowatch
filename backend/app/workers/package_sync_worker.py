"""Background worker for GitHub Packages monitoring sync.

Queue: github_sync

Periodically syncs package data from the GitHub API (REST) for all
configured orgs, stores results in the ``packages`` table, computes
staleness flags, and generates security alerts when risk conditions are met.

Runs every 6 hours via Celery beat.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from celery import Task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


# ── Alert generation helpers ─────────────────────────────────────────────────

_STALE_THRESHOLD_DAYS = 90

_EXPECTED_REGISTRY_TYPES = frozenset(
    {
        "npm",
        "maven",
        "docker",
        "container",
        "nuget",
        "rubygems",
    }
)


async def _generate_alerts(session: AsyncSession) -> int:
    """Scan the packages table and create alerts for risk conditions.

    Returns the number of new alerts created.
    """
    created = 0

    # 1. Public exposure alerts — packages with visibility=public that have no open alert
    public_q = await session.execute(
        text(
            "SELECT p.id, p.org, p.name FROM packages p "
            "WHERE p.visibility = 'public' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM package_alerts a "
            "  WHERE a.package_id = p.id AND a.alert_type = 'public_exposure' "
            "  AND a.status = 'open'"
            ")"
        )
    )
    for row in public_q.fetchall():
        await session.execute(
            text(
                "INSERT INTO package_alerts (package_id, alert_type, severity, message) "
                "VALUES (:pkg_id, 'public_exposure', 'medium', :msg)"
            ),
            {
                "pkg_id": row.id,
                "msg": f"Package '{row.name}' in org '{row.org}' has public visibility",
            },
        )
        created += 1

    # 2. Stale image alerts
    stale_q = await session.execute(
        text(
            "SELECT p.id, p.org, p.name FROM packages p "
            "WHERE p.is_stale = true AND p.package_type = 'container' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM package_alerts a "
            "  WHERE a.package_id = p.id AND a.alert_type = 'stale_image' "
            "  AND a.status = 'open'"
            ")"
        )
    )
    for row in stale_q.fetchall():
        await session.execute(
            text(
                "INSERT INTO package_alerts (package_id, alert_type, severity, message) "
                "VALUES (:pkg_id, 'stale_image', 'medium', :msg)"
            ),
            {
                "pkg_id": row.id,
                "msg": (
                    f"Container image '{row.name}' in org '{row.org}' "
                    f"has not been rebuilt in over {_STALE_THRESHOLD_DAYS} days"
                ),
            },
        )
        created += 1

    # 3. External publisher alerts
    ext_q = await session.execute(
        text(
            "SELECT p.id, p.org, p.name FROM packages p "
            "WHERE p.published_by_external = true "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM package_alerts a "
            "  WHERE a.package_id = p.id AND a.alert_type = 'external_publisher' "
            "  AND a.status = 'open'"
            ")"
        )
    )
    for row in ext_q.fetchall():
        await session.execute(
            text(
                "INSERT INTO package_alerts (package_id, alert_type, severity, message) "
                "VALUES (:pkg_id, 'external_publisher', 'high', :msg)"
            ),
            {
                "pkg_id": row.id,
                "msg": (
                    f"Package '{row.name}' in org '{row.org}' "
                    f"was published by a non-org-member (external collaborator)"
                ),
            },
        )
        created += 1

    # 4. Unexpected registry type alerts
    unreg_q = await session.execute(
        text(
            "SELECT p.id, p.org, p.name, p.package_type FROM packages p "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM package_alerts a "
            "  WHERE a.package_id = p.id AND a.alert_type = 'unexpected_registry' "
            "  AND a.status = 'open'"
            ")"
        )
    )
    for row in unreg_q.fetchall():
        if row.package_type not in _EXPECTED_REGISTRY_TYPES:
            await session.execute(
                text(
                    "INSERT INTO package_alerts "
                    "(package_id, alert_type, severity, message) "
                    "VALUES (:pkg_id, 'unexpected_registry', 'medium', :msg)"
                ),
                {
                    "pkg_id": row.id,
                    "msg": (
                        f"Package '{row.name}' in org '{row.org}' uses "
                        f"unexpected registry type '{row.package_type}'"
                    ),
                },
            )
            created += 1

    # 5. Auto-resolve alerts where the condition is no longer true
    await session.execute(
        text(
            "UPDATE package_alerts SET status = 'resolved', resolved_at = NOW() "
            "WHERE alert_type = 'public_exposure' AND status = 'open' "
            "AND package_id IN ("
            "  SELECT id FROM packages WHERE visibility != 'public'"
            ")"
        )
    )
    await session.execute(
        text(
            "UPDATE package_alerts SET status = 'resolved', resolved_at = NOW() "
            "WHERE alert_type = 'stale_image' AND status = 'open' "
            "AND package_id IN ("
            "  SELECT id FROM packages WHERE is_stale = false"
            ")"
        )
    )

    return created


async def _update_staleness_flags(session: AsyncSession) -> int:
    """Mark container images as stale if not rebuilt within threshold days.

    Returns the number of packages updated.
    """
    result = await session.execute(
        text(
            "UPDATE packages SET is_stale = true, updated_at = NOW() "
            "WHERE package_type = 'container' "
            "AND is_stale = false "
            "AND (last_published_at IS NULL "
            "     OR last_published_at < NOW() - INTERVAL '1 day' * :threshold)"
        ),
        {"threshold": _STALE_THRESHOLD_DAYS},
    )
    stale_count = result.rowcount or 0

    # Un-stale packages that were recently rebuilt
    result2 = await session.execute(
        text(
            "UPDATE packages SET is_stale = false, updated_at = NOW() "
            "WHERE package_type = 'container' "
            "AND is_stale = true "
            "AND last_published_at IS NOT NULL "
            "AND last_published_at >= NOW() - INTERVAL '1 day' * :threshold"
        ),
        {"threshold": _STALE_THRESHOLD_DAYS},
    )
    unstale_count = result2.rowcount or 0

    return stale_count + unstale_count


async def _sync_packages_for_org(session: AsyncSession, org: str) -> int:
    """Sync packages for a single org from GitHub API.

    Uses the REST API: GET /orgs/{org}/packages for each package type.
    Returns the number of packages upserted.

    Note: Requires a valid GitHub token configured in the app. If no GitHub
    App config is found, the sync is skipped gracefully.
    """
    try:
        from app.services.github_token_service import GitHubAppTokenManager
    except ImportError:
        logger.warning("package_sync.github_token_service_unavailable")
        return 0

    # Look up GitHub App installation for this org
    install_q = await session.execute(
        text(
            "SELECT i.installation_id, i.app_id "
            "FROM github_app_installations i "
            "WHERE i.target_type = 'Organization' AND i.target_login = :org "
            "ORDER BY i.synced_at DESC LIMIT 1"
        ),
        {"org": org},
    )
    install_row = install_q.fetchone()
    if not install_row:
        logger.info("package_sync.no_installation", org=org)
        return 0

    try:
        from app.config import settings

        private_key = settings.github_app.resolve_private_key()
        if not private_key:
            logger.warning("package_sync.no_private_key", org=org)
            return 0
        token_manager = GitHubAppTokenManager(
            app_id=install_row.app_id,
            private_key_pem=private_key,
        )
        token = await token_manager.get_installation_token(
            install_row.installation_id,
        )
    except Exception as exc:
        logger.warning("package_sync.token_error", org=org, error=str(exc))
        return 0

    import httpx

    upserted = 0
    package_types = ["npm", "maven", "docker", "container", "nuget", "rubygems"]

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30.0,
    ) as client:
        for pkg_type in package_types:
            page = 1
            while True:
                resp = await client.get(
                    f"/orgs/{org}/packages",
                    params={"package_type": pkg_type, "per_page": 100, "page": page},
                )
                if resp.status_code == 404:
                    break
                if resp.status_code == 403:
                    logger.warning(
                        "package_sync.forbidden",
                        org=org,
                        package_type=pkg_type,
                    )
                    break
                resp.raise_for_status()
                packages = resp.json()
                if not packages:
                    break

                for pkg in packages:
                    pkg_name = pkg.get("name", "")
                    visibility = pkg.get("visibility", "private")
                    owner_login = pkg.get("owner", {}).get("login", "")
                    repo_name = (
                        pkg.get("repository", {}).get("full_name")
                        if pkg.get("repository")
                        else None
                    )

                    # Fetch version count
                    versions_count = 0
                    latest_version = None
                    last_published = None
                    try:
                        ver_resp = await client.get(
                            f"/orgs/{org}/packages/{pkg_type}/{pkg_name}/versions",
                            params={"per_page": 1},
                        )
                        if ver_resp.status_code == 200:
                            versions = ver_resp.json()
                            if versions:
                                latest_version = versions[0].get("name")
                                last_published = versions[0].get("updated_at")

                        # Get total version count from the link header or a separate call
                        count_resp = await client.get(
                            f"/orgs/{org}/packages/{pkg_type}/{pkg_name}/versions",
                            params={"per_page": 1, "page": 1},
                        )
                        if count_resp.status_code == 200:
                            # Parse link header for total
                            link = count_resp.headers.get("link", "")
                            if 'rel="last"' in link:
                                import re

                                match = re.search(r"page=(\d+)>; rel=\"last\"", link)
                                if match:
                                    versions_count = int(match.group(1))
                            else:
                                versions_count = len(count_resp.json())
                    except Exception as ver_exc:
                        logger.debug(
                            "package_sync.version_fetch_error",
                            org=org,
                            package=pkg_name,
                            error=str(ver_exc),
                        )

                    # Check if published outside GitHub Actions
                    published_outside = False
                    # Check last version metadata for source
                    try:
                        if latest_version:
                            meta_resp = await client.get(
                                f"/orgs/{org}/packages/{pkg_type}/{pkg_name}/versions",
                                params={"per_page": 1},
                            )
                            if meta_resp.status_code == 200:
                                meta = meta_resp.json()
                                if meta:
                                    metadata = meta[0].get("metadata", {})
                                    container_meta = metadata.get("container", {})
                                    # If no workflow ref in metadata, manual push
                                    is_container = pkg_type in (
                                        "docker",
                                        "container",
                                    )
                                    no_pkg_type = not container_meta.get("package_type")
                                    if is_container and no_pkg_type:
                                        published_outside = True
                    except Exception as meta_exc:
                        logger.debug(
                            "package_sync.metadata_check_error",
                            package=pkg_name,
                            error=str(meta_exc),
                        )

                    # Check if publisher is external collaborator
                    published_by_ext = False
                    if owner_login and owner_login != org:
                        member_q = await session.execute(
                            text("SELECT 1 FROM org_members WHERE org = :org AND login = :login"),
                            {"org": org, "login": owner_login},
                        )
                        if not member_q.fetchone():
                            published_by_ext = True

                    # Upsert the package
                    now = datetime.now(UTC)
                    await session.execute(
                        text(
                            "INSERT INTO packages "
                            "(org, repo, name, package_type, visibility, owner, "
                            " versions_count, latest_version, last_published_at, "
                            " published_outside_actions, published_by_external, updated_at) "
                            "VALUES (:org, :repo, :name, :pkg_type, :vis, :owner, "
                            " :ver_count, :latest_ver, :last_pub, "
                            " :pub_outside, :pub_ext, :now) "
                            "ON CONFLICT (org, name) DO UPDATE SET "
                            " repo = EXCLUDED.repo, "
                            " package_type = EXCLUDED.package_type, "
                            " visibility = EXCLUDED.visibility, "
                            " owner = EXCLUDED.owner, "
                            " versions_count = EXCLUDED.versions_count, "
                            " latest_version = EXCLUDED.latest_version, "
                            " last_published_at = EXCLUDED.last_published_at, "
                            " published_outside_actions = EXCLUDED.published_outside_actions, "
                            " published_by_external = EXCLUDED.published_by_external, "
                            " updated_at = EXCLUDED.updated_at"
                        ),
                        {
                            "org": org,
                            "repo": repo_name,
                            "name": pkg_name,
                            "pkg_type": pkg_type,
                            "vis": visibility,
                            "owner": owner_login or None,
                            "ver_count": versions_count,
                            "latest_ver": latest_version,
                            "last_pub": last_published,
                            "pub_outside": published_outside,
                            "pub_ext": published_by_ext,
                            "now": now,
                        },
                    )
                    upserted += 1

                page += 1
                if len(packages) < 100:
                    break

    return upserted


async def _run_sync() -> None:
    """Run the full packages sync: fetch from GitHub, update flags, generate alerts."""
    session_factory = _make_session_factory()
    async with session_factory() as session:
        # Get all configured orgs
        orgs_q = await session.execute(
            text(
                "SELECT DISTINCT target_login "
                "FROM github_app_installations "
                "WHERE target_type = 'Organization'"
            )
        )
        orgs = [row.target_login for row in orgs_q.fetchall()]

        if not orgs:
            logger.info("package_sync.no_orgs_configured")
            return

        total_upserted = 0
        for org in orgs:
            try:
                count = await _sync_packages_for_org(session, org)
                total_upserted += count
                logger.info("package_sync.org_complete", org=org, packages=count)
            except Exception as exc:
                logger.error("package_sync.org_failed", org=org, error=str(exc))

        # Update staleness flags
        stale_updated = await _update_staleness_flags(session)
        logger.info("package_sync.staleness_updated", count=stale_updated)

        # Generate alerts
        alerts_created = await _generate_alerts(session)
        logger.info("package_sync.alerts_created", count=alerts_created)

        await session.commit()
        logger.info(
            "package_sync.complete",
            orgs=len(orgs),
            packages_upserted=total_upserted,
            alerts_created=alerts_created,
        )


# ── Celery task ──────────────────────────────────────────────────────────────


@celery_app.task(
    name="app.workers.package_sync_worker.sync_packages",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def sync_packages(self: Task) -> dict[str, str]:
    """Celery task: sync GitHub Packages data and generate alerts.

    Runs every 6 hours via Celery beat schedule.
    """
    try:
        asyncio.run(_run_sync())
        return {"status": "ok"}
    except Exception as exc:
        logger.error("package_sync.task_failed", error=str(exc))
        raise self.retry(exc=exc) from exc
