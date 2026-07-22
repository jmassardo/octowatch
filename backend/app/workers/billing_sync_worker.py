"""Celery worker: daily sync of Enhanced Billing API data into utilization_facts.

Polls GitHub's Enhanced Billing API for Actions, Copilot, GHAS, Packages, and
Storage usage data, writing daily aggregates per actor into the utilization_facts table.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import date, timedelta
from typing import Any

import httpx
import redis.asyncio as aioredis
import structlog
from celery import Task
from sqlalchemy import text

from app.celery_app import celery_app
from app.config import settings
from app.database import AsyncSessionLocal
from app.services.github_token_service import GitHubAppTokenManager

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.billing_sync_worker.sync_billing_data",
    bind=True,
    max_retries=2,
)
def sync_billing_data(self: Task) -> dict[str, object]:
    """Daily Celery beat task: sync billing/usage data from GitHub Enhanced Billing API."""
    try:
        result = asyncio.run(_sync_billing())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("billing_sync.task_failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _sync_billing() -> dict[str, Any]:
    """Main billing sync logic."""
    private_key = settings.github_app.resolve_private_key()
    if not private_key:
        logger.warning(
            "billing_sync.skipped",
            reason="no GitHub App credentials configured",
        )
        return {"synced": 0, "skipped": True}

    async with AsyncSessionLocal() as db:
        # Get all active orgs with their installation IDs
        result = await db.execute(
            text(
                "SELECT gac.org_login, gac.installation_id "
                "FROM github_app_configs gac "
                "WHERE gac.enabled = TRUE AND gac.org_login IS NOT NULL"
            )
        )
        org_rows = result.fetchall()

        if not org_rows:
            logger.info("billing_sync.no_orgs")
            return {"synced": 0, "orgs": 0}

        total_upserted = 0
        metric_date = date.today() - timedelta(days=1)  # Yesterday's data

        async with httpx.AsyncClient(timeout=30.0) as client:
            for org_login, installation_id in org_rows:
                try:
                    upserted = await _sync_org_billing(
                        db,
                        client,
                        org_login,
                        installation_id,
                        metric_date,
                        settings,
                        private_key,
                    )
                    total_upserted += upserted
                except Exception:
                    logger.warning("billing_sync.org_failed", org=org_login, exc_info=True)

        await db.commit()
        logger.info("billing_sync.complete", orgs=len(org_rows), upserted=total_upserted)
        return {"synced": total_upserted, "orgs": len(org_rows)}


async def _sync_org_billing(
    db: Any,
    client: Any,
    org_login: str,
    installation_id: int,
    metric_date: date,
    settings: Any,
    private_key: str,
) -> int:
    """Sync billing data for a single org. Returns count of upserted rows."""
    valkey = aioredis.Redis.from_url(settings.VALKEY_URL, decode_responses=True, max_connections=5)
    try:
        token_manager = GitHubAppTokenManager(
            app_id=settings.github_app.GITHUB_APP_ID,
            private_key_pem=private_key,
            valkey_client=valkey,
        )
        token = await token_manager.get_installation_token(installation_id)
    except Exception:
        logger.debug("billing_sync.no_token", org=org_login)
        return 0
    finally:
        await valkey.aclose()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    upserted = 0

    # --- Actions usage ---
    actions_data = await _fetch_api(
        client,
        f"https://api.github.com/orgs/{org_login}/settings/billing/actions",
        headers,
    )
    if actions_data:
        total_minutes = actions_data.get("total_minutes_used", 0)
        total_paid = actions_data.get("total_paid_minutes_used", 0)
        if total_minutes or total_paid:
            await _upsert_fact(
                db,
                org_slug=org_login,
                actor_login="__org_aggregate__",
                feature_area="actions",
                metric_date=metric_date,
                actions_minutes=float(total_minutes + total_paid),
            )
            upserted += 1

    # --- Copilot usage (per-seat) ---
    copilot_data = await _fetch_api(
        client,
        f"https://api.github.com/orgs/{org_login}/copilot/billing/seats",
        headers,
    )
    if copilot_data and "seats" in copilot_data:
        for seat in copilot_data["seats"]:
            assignee = seat.get("assignee", {})
            login = assignee.get("login") if isinstance(assignee, dict) else None
            if not login:
                continue
            last_activity = seat.get("last_activity_at")
            if last_activity:
                await _upsert_fact(
                    db,
                    org_slug=org_login,
                    actor_login=login,
                    feature_area="copilot",
                    metric_date=metric_date,
                    copilot_suggestions=seat.get("last_activity_editor_suggestions_count"),
                    copilot_acceptances=seat.get("last_activity_editor_acceptances_count"),
                )
                upserted += 1

    # --- GHAS (Advanced Security) ---
    ghas_data = await _fetch_api(
        client,
        f"https://api.github.com/orgs/{org_login}/settings/billing/advanced-security",
        headers,
    )
    if ghas_data and "repositories" in ghas_data:
        committer_set: set[str] = set()
        for repo in ghas_data["repositories"]:
            for committer in repo.get("advanced_security_committers_breakdown", []):
                user_login = committer.get("user_login")
                if user_login:
                    committer_set.add(user_login)
        for login in committer_set:
            await _upsert_fact(
                db,
                org_slug=org_login,
                actor_login=login,
                feature_area="ghas",
                metric_date=metric_date,
            )
            upserted += 1

    # --- Packages ---
    packages_data = await _fetch_api(
        client,
        f"https://api.github.com/orgs/{org_login}/settings/billing/packages",
        headers,
    )
    if packages_data:
        total_gb = packages_data.get("total_gigabytes_bandwidth_used", 0)
        if total_gb:
            await _upsert_fact(
                db,
                org_slug=org_login,
                actor_login="__org_aggregate__",
                feature_area="packages",
                metric_date=metric_date,
                storage_bytes=int(total_gb * 1024 * 1024 * 1024),
            )
            upserted += 1

    return upserted


async def _fetch_api(client: Any, url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    """Fetch a GitHub API endpoint, return parsed JSON or None on error."""
    try:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()  # type: ignore[no-any-return]
        if resp.status_code == 404:
            logger.debug("billing_sync.endpoint_not_found", url=url)
        else:
            logger.warning("billing_sync.api_error", url=url, status=resp.status_code)
    except Exception:
        logger.warning("billing_sync.request_failed", url=url, exc_info=True)
    return None


async def _upsert_fact(
    db: Any,
    *,
    org_slug: str,
    actor_login: str,
    feature_area: str,
    metric_date: date,
    actions_minutes: float | None = None,
    actions_runs: int | None = None,
    copilot_suggestions: int | None = None,
    copilot_acceptances: int | None = None,
    copilot_credits: float | None = None,
    ghas_alerts_dismissed: int | None = None,
    git_clones: int | None = None,
    git_pushes: int | None = None,
    packages_published: int | None = None,
    storage_bytes: int | None = None,
) -> None:
    """Upsert a single utilization_facts row."""
    # Use short alias 'uf' for the table in the ON CONFLICT clause
    sql = (
        "INSERT INTO utilization_facts ("
        " org_slug, actor_login, feature_area, metric_date,"
        " actions_minutes, actions_runs,"
        " copilot_suggestions, copilot_acceptances, copilot_credits,"
        " ghas_alerts_dismissed, git_clones, git_pushes,"
        " packages_published, storage_bytes"
        ") VALUES ("
        " :org_slug, :actor_login, :feature_area, :metric_date,"
        " :actions_minutes, :actions_runs,"
        " :copilot_suggestions, :copilot_acceptances, :copilot_credits,"
        " :ghas_alerts_dismissed, :git_clones, :git_pushes,"
        " :packages_published, :storage_bytes"
        ")"
        " ON CONFLICT (org_slug, actor_login, feature_area, metric_date)"
        " DO UPDATE SET"
        " actions_minutes = COALESCE("
        "   EXCLUDED.actions_minutes, utilization_facts.actions_minutes),"
        " actions_runs = COALESCE("
        "   EXCLUDED.actions_runs, utilization_facts.actions_runs),"
        " copilot_suggestions = COALESCE("
        "   EXCLUDED.copilot_suggestions,"
        "   utilization_facts.copilot_suggestions),"
        " copilot_acceptances = COALESCE("
        "   EXCLUDED.copilot_acceptances,"
        "   utilization_facts.copilot_acceptances),"
        " copilot_credits = COALESCE("
        "   EXCLUDED.copilot_credits, utilization_facts.copilot_credits),"
        " ghas_alerts_dismissed = COALESCE("
        "   EXCLUDED.ghas_alerts_dismissed,"
        "   utilization_facts.ghas_alerts_dismissed),"
        " git_clones = COALESCE("
        "   EXCLUDED.git_clones, utilization_facts.git_clones),"
        " git_pushes = COALESCE("
        "   EXCLUDED.git_pushes, utilization_facts.git_pushes),"
        " packages_published = COALESCE("
        "   EXCLUDED.packages_published,"
        "   utilization_facts.packages_published),"
        " storage_bytes = COALESCE("
        "   EXCLUDED.storage_bytes, utilization_facts.storage_bytes)"
    )
    await db.execute(
        text(sql),
        {
            "org_slug": org_slug,
            "actor_login": actor_login,
            "feature_area": feature_area,
            "metric_date": metric_date,
            "actions_minutes": actions_minutes,
            "actions_runs": actions_runs,
            "copilot_suggestions": copilot_suggestions,
            "copilot_acceptances": copilot_acceptances,
            "copilot_credits": copilot_credits,
            "ghas_alerts_dismissed": ghas_alerts_dismissed,
            "git_clones": git_clones,
            "git_pushes": git_pushes,
            "packages_published": packages_published,
            "storage_bytes": storage_bytes,
        },
    )
