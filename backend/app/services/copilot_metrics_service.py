"""Copilot Metrics service — fetches real data from the GitHub Copilot Metrics API.

Migrated to the new NDJSON Metrics Reports endpoint (2026-03-10 API version).
Calls ``GET /enterprises/{slug}/copilot/metrics/reports/enterprise-1-day`` to
obtain download links, fetches the NDJSON files, parses line by line, then
transforms into shaped payloads for all frontend Copilot panes.

Also integrates the Copilot billing/seats API for per-user adoption data,
team-level aggregation, adoption blockers, and ROI analysis.

Results are cached in Valkey (1-hour TTL) to avoid excessive API round-trips.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import redis.asyncio as aioredis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.github_sync import GitHubAppConfig, OrgTeam, OrgTeamMember
from app.services.github_token_service import GitHubAppTokenManager, GitHubAuthError

logger = structlog.get_logger(__name__)

_GITHUB_API_BASE = "https://api.github.com"

# New API version required for Copilot Metrics Reports NDJSON endpoint
_API_VERSION = "2026-03-10"

# Valkey cache key patterns
_CACHE_KEY = "copilot:metrics:{enterprise_slug}"
_CACHE_SEATS_KEY = "copilot:seats:{org_slug}"
_CACHE_TTL_SECONDS = 90000  # 25 hours (survives between daily syncs)

# ── Colour palette ────────────────────────────────────────────────────────────

_COLOR_GREEN = "#3fb950"
_COLOR_YELLOW = "#d29922"
_COLOR_RED = "#f85149"
_COLOR_BLUE = "#58a6ff"
_COLOR_PURPLE = "#bc8cff"
_COLOR_ORANGE = "#d18616"
_COLOR_CYAN = "#39d2c0"
_COLOR_PINK = "#f778ba"
_COLOR_GRAY = "#8b949e"

_LANG_COLORS: dict[str, str] = {
    "python": "#3572A5",
    "javascript": "#f1e05a",
    "typescript": "#3178c6",
    "java": "#b07219",
    "go": "#00ADD8",
    "ruby": "#701516",
    "rust": "#dea584",
    "c++": "#f34b7d",
    "c#": "#178600",
    "c": "#555555",
    "swift": "#F05138",
    "kotlin": "#A97BFF",
    "php": "#4F5D95",
    "shell": "#89e051",
    "html": "#e34c26",
    "css": "#563d7c",
    "markdown": "#083fa1",
    "sql": "#e38c00",
    "yaml": "#cb171e",
    "json": "#292929",
}

_MODEL_COLORS = [_COLOR_BLUE, _COLOR_PURPLE, _COLOR_GREEN, _COLOR_ORANGE, _COLOR_CYAN, _COLOR_PINK]
_FEATURE_COLORS = [_COLOR_GREEN, _COLOR_BLUE, _COLOR_PURPLE, _COLOR_ORANGE, _COLOR_CYAN]
_EDITOR_COLORS = [_COLOR_BLUE, _COLOR_GREEN, _COLOR_PURPLE, _COLOR_ORANGE, _COLOR_CYAN]

_DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Tier thresholds for seat activity (days in last 28-day window)
_POWER_THRESHOLD = 20
_REGULAR_THRESHOLD = 10
_MINIMAL_THRESHOLD = 1

# Default per-seat costs by plan tier
_COST_BUSINESS = 19.0
_COST_ENTERPRISE = 39.0


# ── Internal helpers ──────────────────────────────────────────────────────────


def _acceptance_color(pct: float) -> str:
    """Return colour based on acceptance-rate thresholds."""
    if pct >= 30:
        return _COLOR_GREEN
    if pct >= 20:
        return _COLOR_YELLOW
    return _COLOR_RED


def _lang_color(lang: str) -> str:
    """Return a colour for a programming language."""
    return _LANG_COLORS.get(lang.lower(), _COLOR_GRAY)


def _cost_for_plan(plan_type: str, cost_override: float | None = None) -> float:
    """Return monthly cost for a Copilot seat plan tier."""
    if cost_override is not None:
        return cost_override
    if plan_type == "enterprise":
        return _COST_ENTERPRISE
    return _COST_BUSINESS


async def _get_enterprise_installation(db: AsyncSession) -> GitHubAppConfig | None:
    """Find the first enabled enterprise-level GitHub App installation."""
    enterprise_slug = settings.github_app.GITHUB_ENTERPRISE_SLUG
    if not enterprise_slug:
        return None
    result = await db.execute(
        select(GitHubAppConfig).where(
            GitHubAppConfig.enterprise_slug == enterprise_slug,
            GitHubAppConfig.enabled.is_(True),
        )
    )
    return result.scalars().first()


async def _get_token_and_valkey(
    db: AsyncSession,
) -> tuple[str, aioredis.Redis, str] | dict[str, str]:
    """Obtain a GitHub App installation token and Valkey client.

    Returns ``(token, valkey_client, enterprise_slug)`` on success, or an
    error dict on failure.
    """
    from app.services.settings_service import get_setting

    copilot_enabled = await get_setting(db, "feature_copilot_insights")
    if copilot_enabled is not None and copilot_enabled.lower() not in ("true", "1", "yes", "on"):
        return {
            "error": "feature_disabled",
            "message": "Copilot Insights is disabled. Enable it in Settings → Features.",
        }
    elif copilot_enabled is None:
        return {
            "error": "feature_disabled",
            "message": "Copilot Insights is disabled. Enable it in Settings → Features.",
        }

    enterprise_slug = settings.github_app.GITHUB_ENTERPRISE_SLUG
    if not enterprise_slug:
        return {"error": "no_enterprise_config", "message": "GITHUB_ENTERPRISE_SLUG is not set."}

    app_id = settings.github_app.GITHUB_APP_ID
    key_path = settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH
    private_key_pem = settings.github_app.GITHUB_APP_PRIVATE_KEY_PEM
    if not app_id or (not key_path and not private_key_pem):
        return {
            "error": "no_enterprise_config",
            "message": "GitHub App credentials (APP_ID / private key) are not configured.",
        }

    valkey: aioredis.Redis | None = None
    try:
        valkey = aioredis.Redis.from_url(
            settings.VALKEY_URL, decode_responses=True, max_connections=5
        )
    except Exception:
        logger.warning("copilot_metrics.valkey_connect_failed", exc_info=True)

    config = await _get_enterprise_installation(db)
    if not config:
        if valkey:
            await valkey.aclose()
        return {
            "error": "no_enterprise_config",
            "message": (
                f"No enabled enterprise GitHub App installation found for '{enterprise_slug}'."
            ),
        }

    try:
        private_key = settings.github_app.resolve_private_key()
        if not private_key:
            raise RuntimeError("Private key could not be resolved")
        token_manager = GitHubAppTokenManager(
            app_id=app_id,
            private_key_pem=private_key,
            valkey_client=valkey
            if valkey
            else aioredis.Redis.from_url(
                settings.VALKEY_URL, decode_responses=True, max_connections=5
            ),
        )
        token = await token_manager.get_installation_token(config.installation_id)
    except GitHubAuthError as exc:
        logger.error("copilot_metrics.token_failed", error=str(exc))
        if valkey:
            await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": "Failed to obtain GitHub App installation token. Check App credentials.",
        }
    except Exception as exc:
        logger.error("copilot_metrics.token_unexpected", error=str(exc), exc_info=True)
        if valkey:
            await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": "Unexpected error obtaining GitHub App token. Check server logs.",
        }

    if valkey is None:
        valkey = aioredis.Redis.from_url(
            settings.VALKEY_URL, decode_responses=True, max_connections=5
        )

    return (token, valkey, enterprise_slug)


def _parse_ndjson(text: str) -> list[dict[str, Any]]:
    """Parse NDJSON (newline-delimited JSON) text into a list of dicts."""
    results: list[dict[str, Any]] = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line:
            results.append(json.loads(line))
    return results


async def _fetch_metrics_raw(db: AsyncSession) -> list[dict[str, Any]] | dict[str, str]:
    """Fetch raw daily metrics from the new GitHub Copilot Metrics NDJSON API.

    Uses the 2026-03-10 API version endpoint that returns download links to
    NDJSON files.  Falls back gracefully on errors.

    Returns either the parsed list of daily metric dicts on success, or an
    error dict.  Results are cached in Valkey for ``_CACHE_TTL_SECONDS``.
    """
    # Check feature toggle first
    from app.services.settings_service import get_setting

    copilot_enabled = await get_setting(db, "feature_copilot_insights")
    if copilot_enabled is not None and copilot_enabled.lower() not in (
        "true",
        "1",
        "yes",
        "on",
    ):
        return {
            "error": "feature_disabled",
            "message": "Copilot Insights is disabled. Enable it in Settings → Features.",
        }
    elif copilot_enabled is None:
        return {
            "error": "feature_disabled",
            "message": "Copilot Insights is disabled. Enable it in Settings → Features.",
        }

    enterprise_slug = settings.github_app.GITHUB_ENTERPRISE_SLUG
    if not enterprise_slug:
        return {"error": "no_enterprise_config", "message": "GITHUB_ENTERPRISE_SLUG is not set."}

    app_id = settings.github_app.GITHUB_APP_ID
    key_path = settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH
    private_key_pem = settings.github_app.GITHUB_APP_PRIVATE_KEY_PEM
    if not app_id or (not key_path and not private_key_pem):
        return {
            "error": "no_enterprise_config",
            "message": "GitHub App credentials (APP_ID / private key) are not configured.",
        }

    # ── Check Valkey cache ────────────────────────────────────────────────────
    cache_key = _CACHE_KEY.format(enterprise_slug=enterprise_slug)
    valkey: aioredis.Redis | None = None
    try:
        valkey = aioredis.Redis.from_url(
            settings.VALKEY_URL, decode_responses=True, max_connections=5
        )
        cached = await valkey.get(cache_key)
        if cached:
            logger.debug("copilot_metrics.cache_hit", enterprise=enterprise_slug)
            return json.loads(cached)  # type: ignore[no-any-return]
    except Exception:
        logger.warning("copilot_metrics.cache_read_failed", exc_info=True)

    # ── Resolve installation ──────────────────────────────────────────────────
    config = await _get_enterprise_installation(db)
    if not config:
        if valkey:
            await valkey.aclose()
        return {
            "error": "no_enterprise_config",
            "message": (
                f"No enabled enterprise GitHub App installation found for '{enterprise_slug}'."
            ),
        }

    # ── Get token ─────────────────────────────────────────────────────────────
    try:
        private_key = settings.github_app.resolve_private_key()
        if not private_key:
            raise RuntimeError("Private key could not be resolved")
        token_manager = GitHubAppTokenManager(
            app_id=app_id,
            private_key_pem=private_key,
            valkey_client=valkey
            if valkey
            else aioredis.Redis.from_url(
                settings.VALKEY_URL, decode_responses=True, max_connections=5
            ),
        )
        token = await token_manager.get_installation_token(config.installation_id)
    except GitHubAuthError as exc:
        logger.error("copilot_metrics.token_failed", error=str(exc))
        if valkey:
            await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": "Failed to obtain GitHub App installation token. Check App credentials.",
        }
    except Exception as exc:
        logger.error("copilot_metrics.token_unexpected", error=str(exc), exc_info=True)
        if valkey:
            await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": "Unexpected error obtaining GitHub App token. Check server logs.",
        }

    # ── Call the new NDJSON metrics reports endpoint ──────────────────────────
    url = (
        f"{_GITHUB_API_BASE}/enterprises/{enterprise_slug}/copilot/metrics/reports/enterprise-1-day"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Step 1: Get the report download links
            response = await client.get(url, headers=headers, timeout=30.0)

            if response.status_code in (403, 404):
                logger.warning(
                    "copilot_metrics.api_error",
                    status=response.status_code,
                    enterprise=enterprise_slug,
                )
                if valkey:
                    await valkey.aclose()
                return {
                    "error": "copilot_not_available",
                    "message": (
                        f"GitHub API returned {response.status_code}. "
                        "Copilot metrics may not be enabled for this enterprise, "
                        "or the App lacks the manage_billing:copilot permission."
                    ),
                }

            if response.status_code == 422:
                logger.warning(
                    "copilot_metrics.api_422",
                    enterprise=enterprise_slug,
                    body=response.text[:500],
                )
                if valkey:
                    await valkey.aclose()
                return {
                    "error": "copilot_not_available",
                    "message": (
                        "GitHub API returned 422. This usually means the Copilot Metrics "
                        "API is disabled in your enterprise settings. Enable it at: "
                        "GitHub Enterprise → Settings → Copilot → Policies → "
                        "Copilot Metrics API access."
                    ),
                }

            response.raise_for_status()
            report_data = response.json()

            # Step 2: Parse NDJSON — the new API may return either:
            # (a) A list of report objects with download_url fields, or
            # (b) The NDJSON data directly inline
            metrics: list[dict[str, Any]] = []

            if isinstance(report_data, list):
                # Check if items have download_url (report links)
                if report_data and "download_url" in report_data[0]:
                    for report_item in report_data:
                        dl_url = report_item.get("download_url", "")
                        if not dl_url:
                            continue
                        dl_resp = await client.get(dl_url, timeout=60.0)
                        dl_resp.raise_for_status()
                        metrics.extend(_parse_ndjson(dl_resp.text))
                else:
                    # Already inline data (same shape as old API)
                    metrics = report_data
            elif isinstance(report_data, dict):
                # Single report object with download_url
                dl_url = report_data.get("download_url", "")
                if dl_url:
                    dl_resp = await client.get(dl_url, timeout=60.0)
                    dl_resp.raise_for_status()
                    metrics = _parse_ndjson(dl_resp.text)

    except httpx.HTTPStatusError as exc:
        logger.error("copilot_metrics.http_error", status=exc.response.status_code, exc_info=True)
        if valkey:
            await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": f"GitHub API error: HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        logger.error("copilot_metrics.fetch_failed", error=str(exc), exc_info=True)
        if valkey:
            await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": "Failed to fetch Copilot metrics from GitHub API. Check server logs.",
        }

    # ── Write back to cache ───────────────────────────────────────────────────
    try:
        if valkey:
            await valkey.set(cache_key, json.dumps(metrics), ex=_CACHE_TTL_SECONDS)
            logger.debug("copilot_metrics.cache_write", enterprise=enterprise_slug)
    except Exception:
        logger.warning("copilot_metrics.cache_write_failed", exc_info=True)
    finally:
        if valkey:
            await valkey.aclose()

    return metrics


async def _fetch_copilot_seats(db: AsyncSession) -> list[dict[str, Any]] | dict[str, str]:
    """Fetch per-user Copilot seat data from the billing/seats API.

    Calls ``GET /orgs/{org}/copilot/billing/seats`` for each org under the
    enterprise.  Results are cached in Valkey.
    """
    auth_result = await _get_token_and_valkey(db)
    if isinstance(auth_result, dict):
        return auth_result

    token, valkey, enterprise_slug = auth_result

    cache_key = _CACHE_SEATS_KEY.format(org_slug=enterprise_slug)
    try:
        cached = await valkey.get(cache_key)
        if cached:
            logger.debug("copilot_seats.cache_hit", enterprise=enterprise_slug)
            return json.loads(cached)  # type: ignore[no-any-return]
    except Exception:
        logger.warning("copilot_seats.cache_read_failed", exc_info=True)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }

    all_seats: list[dict[str, Any]] = []
    # Fetch seats from enterprise-level org listing
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Get orgs in the enterprise
            orgs_url = f"{_GITHUB_API_BASE}/enterprises/{enterprise_slug}/organizations"
            orgs_resp = await client.get(orgs_url, headers=headers, timeout=30.0)
            if orgs_resp.status_code == 200:
                orgs_data = orgs_resp.json()
                org_slugs = [o.get("login", "") for o in orgs_data if o.get("login")]
            else:
                org_slugs = []

            if not org_slugs:
                # Fallback: use enterprise slug as single org
                org_slugs = [enterprise_slug]

            for org_slug in org_slugs:
                page = 1
                while True:
                    seats_url = (
                        f"{_GITHUB_API_BASE}/orgs/{org_slug}/copilot/billing/seats"
                        f"?per_page=100&page={page}"
                    )
                    resp = await client.get(seats_url, headers=headers, timeout=30.0)
                    if resp.status_code != 200:
                        logger.warning(
                            "copilot_seats.api_error",
                            org=org_slug,
                            status=resp.status_code,
                        )
                        break
                    data = resp.json()
                    seats = data.get("seats", [])
                    for seat in seats:
                        seat["_org_slug"] = org_slug
                    all_seats.extend(seats)
                    if len(seats) < 100:
                        break
                    page += 1

    except Exception as exc:
        logger.error("copilot_seats.fetch_failed", error=str(exc), exc_info=True)
        await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": "Failed to fetch Copilot seat data from GitHub API.",
        }

    # Cache the result
    try:
        await valkey.set(cache_key, json.dumps(all_seats), ex=_CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("copilot_seats.cache_write_failed", exc_info=True)
    finally:
        await valkey.aclose()

    return all_seats


def _classify_user(seat: dict[str, Any]) -> str:
    """Classify a seat user into power/regular/minimal/inactive tier."""
    last_activity = seat.get("last_activity_at")
    if not last_activity:
        return "inactive"
    try:
        last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "inactive"

    now = datetime.now(UTC)
    days_since = (now - last_dt).days
    if days_since <= 3:
        return "power"
    if days_since <= 14:
        return "regular"
    if days_since <= 30:
        return "minimal"
    return "inactive"


# ── Cache / DB readers (no live API calls) ────────────────────────────────────


async def _check_feature_enabled(db: AsyncSession) -> dict[str, str] | None:
    """Check feature toggle and enterprise config.  Returns error dict or None."""
    from app.services.settings_service import get_setting

    copilot_enabled = await get_setting(db, "feature_copilot_insights")
    if copilot_enabled is None or copilot_enabled.lower() not in ("true", "1", "yes", "on"):
        return {
            "error": "feature_disabled",
            "message": "Copilot Insights is disabled. Enable it in Settings → Features.",
        }

    enterprise_slug = settings.github_app.GITHUB_ENTERPRISE_SLUG
    if not enterprise_slug:
        return {"error": "no_enterprise_config", "message": "GITHUB_ENTERPRISE_SLUG is not set."}

    return None


async def _read_metrics_from_store(db: AsyncSession) -> list[dict[str, Any]] | dict[str, str]:
    """Read Copilot metrics from Valkey cache or DB.  Never calls GitHub API.

    Returns the same shape as ``_fetch_metrics_raw`` (list of daily metric
    dicts) so that all downstream public functions work unchanged.
    """
    err = await _check_feature_enabled(db)
    if err is not None:
        return err

    enterprise_slug = settings.github_app.GITHUB_ENTERPRISE_SLUG or ""

    # Try Valkey cache first
    cache_key = _CACHE_KEY.format(enterprise_slug=enterprise_slug)
    try:
        valkey = aioredis.Redis.from_url(
            settings.VALKEY_URL, decode_responses=True, max_connections=5
        )
        try:
            cached = await valkey.get(cache_key)
            if cached:
                logger.debug("copilot_metrics.store_cache_hit", enterprise=enterprise_slug)
                return json.loads(cached)  # type: ignore[no-any-return]
        finally:
            await valkey.aclose()
    except Exception:
        logger.warning("copilot_metrics.store_cache_read_failed", exc_info=True)

    # Fall back to DB reconstruction
    return await _reconstruct_metrics_from_db(db, enterprise_slug)


async def _reconstruct_metrics_from_db(
    db: AsyncSession, enterprise_slug: str
) -> list[dict[str, Any]]:
    """Reconstruct the raw API response shape from ``CopilotDailyMetric`` rows."""
    from app.models.copilot_metrics import CopilotDailyMetric

    result = await db.execute(
        select(CopilotDailyMetric)
        .where(CopilotDailyMetric.org_slug == enterprise_slug)
        .order_by(CopilotDailyMetric.date)
    )
    rows = list(result.scalars().all())
    if not rows:
        return []

    days_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        date_str = row.date.isoformat()
        if date_str not in days_map:
            days_map[date_str] = {
                "date": date_str,
                "total_active_users": 0,
                "total_engaged_users": 0,
                "copilot_ide_code_completions": {"total_engaged_users": 0, "editors": []},
                "copilot_ide_chat": {"total_engaged_users": 0, "editors": []},
                "copilot_dotcom_chat": {"total_engaged_users": 0},
                "copilot_dotcom_pull_requests": {"total_engaged_users": 0},
            }

        day = days_map[date_str]

        if row.metric_type == "summary":
            day["total_active_users"] = row.active_users
            day["total_engaged_users"] = row.engaged_users
        elif row.metric_type == "completions":
            completions = day["copilot_ide_code_completions"]
            editor_name = row.editor or "Unknown"
            model_name = row.model or "Unknown"
            lang_name = row.language or "Unknown"

            # Find or create editor
            editor_obj = None
            for e in completions["editors"]:
                if e["name"] == editor_name:
                    editor_obj = e
                    break
            if editor_obj is None:
                editor_obj = {"name": editor_name, "total_engaged_users": 0, "models": []}
                completions["editors"].append(editor_obj)

            # Find or create model
            model_obj = None
            for m in editor_obj["models"]:
                if m["name"] == model_name:
                    model_obj = m
                    break
            if model_obj is None:
                model_obj = {
                    "name": model_name,
                    "total_engaged_users": row.engaged_users,
                    "languages": [],
                }
                editor_obj["models"].append(model_obj)

            model_obj["languages"].append(
                {
                    "name": lang_name,
                    "total_code_suggestions": row.total_suggestions,
                    "total_code_acceptances": row.total_acceptances,
                    "total_code_lines_suggested": row.total_lines_suggested,
                    "total_code_lines_accepted": row.total_lines_accepted,
                }
            )
            # Update editor and section engaged-user estimates
            editor_obj["total_engaged_users"] = max(
                editor_obj["total_engaged_users"], row.engaged_users
            )
            completions["total_engaged_users"] = max(
                completions["total_engaged_users"], row.engaged_users
            )
        elif row.metric_type == "chat":
            day["copilot_ide_chat"]["total_engaged_users"] = row.engaged_users
        elif row.metric_type == "dotcom_chat":
            day["copilot_dotcom_chat"]["total_engaged_users"] = row.engaged_users
        elif row.metric_type == "pr":
            day["copilot_dotcom_pull_requests"]["total_engaged_users"] = row.engaged_users

    return list(days_map.values())


async def _read_seats_from_store(db: AsyncSession) -> list[dict[str, Any]] | dict[str, str]:
    """Read Copilot seat data from Valkey cache or DB.  Never calls GitHub API."""
    err = await _check_feature_enabled(db)
    if err is not None:
        return err

    enterprise_slug = settings.github_app.GITHUB_ENTERPRISE_SLUG or ""

    # Try Valkey cache first
    cache_key = _CACHE_SEATS_KEY.format(org_slug=enterprise_slug)
    try:
        valkey = aioredis.Redis.from_url(
            settings.VALKEY_URL, decode_responses=True, max_connections=5
        )
        try:
            cached = await valkey.get(cache_key)
            if cached:
                logger.debug("copilot_seats.store_cache_hit", enterprise=enterprise_slug)
                return json.loads(cached)  # type: ignore[no-any-return]
        finally:
            await valkey.aclose()
    except Exception:
        logger.warning("copilot_seats.store_cache_read_failed", exc_info=True)

    # Fall back to DB reconstruction
    return await _reconstruct_seats_from_db(db)


async def _reconstruct_seats_from_db(db: AsyncSession) -> list[dict[str, Any]]:
    """Reconstruct seat data from the most recent ``CopilotSeatSnapshot`` rows."""
    from sqlalchemy import func

    from app.models.copilot_metrics import CopilotSeatSnapshot

    latest_result = await db.execute(select(func.max(CopilotSeatSnapshot.snapshot_date)))
    latest_date = latest_result.scalar()
    if not latest_date:
        return []

    result = await db.execute(
        select(CopilotSeatSnapshot).where(CopilotSeatSnapshot.snapshot_date == latest_date)
    )
    snapshots = list(result.scalars().all())

    seats: list[dict[str, Any]] = []
    for snap in snapshots:
        seats.append(
            {
                "assignee": {"login": snap.github_login},
                "_org_slug": snap.org_slug,
                "plan_type": snap.plan_type,
                "last_activity_at": (
                    snap.last_activity_at.isoformat() if snap.last_activity_at else None
                ),
                "last_activity_editor": snap.last_activity_editor,
                "pending_cancellation_date": snap.pending_cancellation_date,
            }
        )

    return seats


# ── Public API ────────────────────────────────────────────────────────────────


async def get_copilot_overview(db: AsyncSession) -> dict[str, Any]:
    """Data for the Overview pane: acceptance rates, language breakdown, user counts."""
    raw = await _read_metrics_from_store(db)
    if isinstance(raw, dict) and "error" in raw:
        return raw

    days: list[dict[str, Any]] = raw  # type: ignore[assignment]
    if not days:
        return {
            "acceptance_rate_days": [],
            "acceptance_rate_values": [],
            "acceptance_threshold": 25,
            "languages": [],
            "total_active_users": 0,
            "total_engaged_users": 0,
        }

    # ── Acceptance rates for last 7 days ──────────────────────────────────────
    recent = days[-7:] if len(days) >= 7 else days
    rate_labels: list[str] = []
    rate_values: list[float] = []

    for day_obj in recent:
        date_str = day_obj.get("date", "")
        try:
            dt = datetime.fromisoformat(date_str)
            rate_labels.append(_DAY_LABELS[dt.weekday()])
        except (ValueError, TypeError):
            rate_labels.append("?")

        completions = day_obj.get("copilot_ide_code_completions") or {}
        total_suggestions = 0
        total_acceptances = 0
        for editor in completions.get("editors", []):
            for model in editor.get("models", []):
                for lang in model.get("languages", []):
                    total_suggestions += lang.get("total_code_suggestions", 0)
                    total_acceptances += lang.get("total_code_acceptances", 0)

        pct = (total_acceptances / total_suggestions * 100) if total_suggestions else 0.0
        rate_values.append(round(pct, 1))

    # ── Language breakdown (all days) ─────────────────────────────────────────
    lang_suggestions: dict[str, int] = {}
    lang_acceptances: dict[str, int] = {}
    for day_obj in days:
        completions = day_obj.get("copilot_ide_code_completions") or {}
        for editor in completions.get("editors", []):
            for model in editor.get("models", []):
                for lang in model.get("languages", []):
                    name = lang.get("name", "Unknown")
                    lang_suggestions[name] = lang_suggestions.get(name, 0) + lang.get(
                        "total_code_suggestions", 0
                    )
                    lang_acceptances[name] = lang_acceptances.get(name, 0) + lang.get(
                        "total_code_acceptances", 0
                    )

    total_sugg = sum(lang_suggestions.values()) or 1
    lang_items: list[dict[str, Any]] = [
        {
            "lang": name,
            "pct": round(count / total_sugg * 100, 1),
            "color": _lang_color(name),
        }
        for name, count in lang_suggestions.items()
    ]
    lang_items.sort(key=lambda x: float(str(x["pct"])), reverse=True)

    # ── Active / engaged user counts ──────────────────────────────────────────
    latest = days[-1] if days else {}
    total_active = latest.get("total_active_users", 0)
    total_engaged = latest.get("total_engaged_users", 0)

    return {
        "acceptance_rate_days": rate_labels,
        "acceptance_rate_values": rate_values,
        "acceptance_threshold": 25,
        "languages": lang_items[:10],  # top 10
        "total_active_users": total_active,
        "total_engaged_users": total_engaged,
    }


async def get_copilot_adoption(db: AsyncSession) -> dict[str, Any]:
    """Data for the Adoption pane: tiers, feature adoption, per-user data."""
    try:
        raw = await _read_metrics_from_store(db)
    except Exception as exc:
        logger.error("copilot_adoption.read_metrics_failed", error=str(exc), exc_info=True)
        return {
            "error": "internal_error",
            "message": f"Failed to read metrics: {type(exc).__name__}: {exc}",
        }
    if isinstance(raw, dict) and "error" in raw:
        return raw

    days: list[dict[str, Any]] = raw  # type: ignore[assignment]
    if not days:
        return {
            "tiers": [],
            "total_adoption": 0,
            "power_users": [],
            "feature_adoption": [],
            "minimal_users": [],
        }

    num_days = len(days)

    # ── Try to get per-user data from seats API ───────────────────────────────
    try:
        seats_data = await _read_seats_from_store(db)
        has_seat_data = isinstance(seats_data, list) and len(seats_data) > 0
    except Exception:
        logger.debug("copilot_adoption.seats_fetch_fallback", exc_info=True)
        seats_data = []
        has_seat_data = False

    power_users: list[dict[str, Any]] = []
    minimal_users: list[dict[str, Any]] = []
    tier_counts = {"power": 0, "regular": 0, "minimal": 0, "inactive": 0}

    if has_seat_data:
        assert isinstance(seats_data, list)
        for seat in seats_data:
            assignee = seat.get("assignee") or {}
            login = assignee.get("login", "unknown")
            tier = _classify_user(seat)
            tier_counts[tier] += 1

            last_activity = seat.get("last_activity_at", "")
            last_editor = seat.get("last_activity_editor", "")

            if tier == "power":
                power_users.append(
                    {
                        "user": login,
                        "days_active": _days_since_last_activity(last_activity),
                        "features_used": _count_features(seat),
                        "last_activity": last_activity,
                        "editor": last_editor,
                    }
                )
            elif tier == "minimal":
                minimal_users.append(
                    {
                        "user": login,
                        "days_active": _days_since_last_activity(last_activity),
                        "last_feature": last_editor or "unknown",
                        "last_activity": last_activity,
                    }
                )
    else:
        # Fallback: estimate tiers from daily active user counts
        daily_active: list[int] = [d.get("total_active_users", 0) for d in days]
        avg_active = sum(daily_active) / num_days if num_days else 0
        max_active = max(daily_active) if daily_active else 0
        latest_active = daily_active[-1] if daily_active else 0

        power_estimate = int(min(daily_active) * 0.9) if daily_active else 0
        regular_estimate = int(avg_active - power_estimate) if avg_active > power_estimate else 0
        minimal_estimate = int(max_active - avg_active) if max_active > avg_active else 0
        inactive_estimate = max(0, int(latest_active * 0.1))

        tier_counts = {
            "power": power_estimate,
            "regular": regular_estimate,
            "minimal": minimal_estimate,
            "inactive": inactive_estimate,
        }

    tiers: list[dict[str, Any]] = [
        {
            "id": "power",
            "label": "Power Users",
            "count": tier_counts["power"],
            "color": _COLOR_GREEN,
            "desc": "Active nearly every day across multiple features",
        },
        {
            "id": "regular",
            "label": "Regular Users",
            "count": tier_counts["regular"],
            "color": _COLOR_BLUE,
            "desc": "Active more than 50% of measured days",
        },
        {
            "id": "minimal",
            "label": "Minimal Users",
            "count": tier_counts["minimal"],
            "color": _COLOR_YELLOW,
            "desc": "Active only 1–2 days in the measurement window",
        },
        {
            "id": "inactive",
            "label": "Inactive / Never",
            "count": tier_counts["inactive"],
            "color": _COLOR_GRAY,
            "desc": "Assigned a seat but no recorded activity",
        },
    ]
    total_adoption = sum(tier_counts.values())

    # ── Feature adoption ──────────────────────────────────────────────────────
    latest = days[-1] if days else {}
    latest_engaged = latest.get("total_engaged_users", 0) or 1

    completions_users = (latest.get("copilot_ide_code_completions") or {}).get(
        "total_engaged_users", 0
    )
    chat_users = (latest.get("copilot_ide_chat") or {}).get("total_engaged_users", 0)
    dotcom_chat_users = (latest.get("copilot_dotcom_chat") or {}).get("total_engaged_users", 0)
    pr_users = (latest.get("copilot_dotcom_pull_requests") or {}).get("total_engaged_users", 0)

    feature_adoption = [
        {
            "feature": "IDE completions",
            "pct": round(completions_users / latest_engaged * 100, 1),
            "color": _COLOR_GREEN,
        },
        {
            "feature": "IDE chat",
            "pct": round(chat_users / latest_engaged * 100, 1),
            "color": _COLOR_BLUE,
        },
        {
            "feature": "Dotcom chat",
            "pct": round(dotcom_chat_users / latest_engaged * 100, 1),
            "color": _COLOR_PURPLE,
        },
        {
            "feature": "PR summaries",
            "pct": round(pr_users / latest_engaged * 100, 1),
            "color": _COLOR_ORANGE,
        },
    ]

    return {
        "tiers": tiers,
        "total_adoption": total_adoption,
        "power_users": power_users,
        "feature_adoption": feature_adoption,
        "minimal_users": minimal_users,
    }


def _days_since_last_activity(last_activity_str: str) -> int:
    """Calculate days since last activity from ISO 8601 timestamp."""
    if not last_activity_str:
        return 999
    try:
        last_dt = datetime.fromisoformat(last_activity_str.replace("Z", "+00:00"))
        return max(0, (datetime.now(UTC) - last_dt).days)
    except (ValueError, TypeError):
        return 999


def _count_features(seat: dict[str, Any]) -> int:
    """Count distinct features used by a seat user from seat metadata."""
    count = 0
    editor = seat.get("last_activity_editor", "")
    if editor:
        count += 1
    # Copilot seat objects may include feature usage indicators
    if seat.get("last_activity_at"):
        count += 1
    return max(1, count)


async def get_copilot_models(db: AsyncSession) -> dict[str, Any]:
    """Data for the Models pane: model usage, feature counts, editors."""
    raw = await _read_metrics_from_store(db)
    if isinstance(raw, dict) and "error" in raw:
        return raw

    days: list[dict[str, Any]] = raw  # type: ignore[assignment]
    if not days:
        return {"models": [], "features": [], "editors": []}

    # ── Aggregate model usage ─────────────────────────────────────────────────
    model_counts: dict[str, int] = {}
    editor_counts: dict[str, int] = {}

    for day_obj in days:
        for feature_key in ("copilot_ide_code_completions", "copilot_ide_chat"):
            feature = day_obj.get(feature_key) or {}
            for editor in feature.get("editors", []):
                editor_name = editor.get("name", "Unknown")
                editor_engaged = editor.get("total_engaged_users", 0)
                editor_counts[editor_name] = editor_counts.get(editor_name, 0) + editor_engaged

                for model in editor.get("models", []):
                    model_name = model.get("name", "Unknown")
                    model_engaged = model.get("total_engaged_users", 0)
                    model_counts[model_name] = model_counts.get(model_name, 0) + model_engaged

    total_model = sum(model_counts.values()) or 1
    models_list: list[dict[str, Any]] = [
        {
            "model": name,
            "pct": round(count / total_model * 100, 1),
            "color": _MODEL_COLORS[i % len(_MODEL_COLORS)],
        }
        for i, (name, count) in enumerate(model_counts.items())
    ]
    models_list.sort(key=lambda x: float(str(x["pct"])), reverse=True)

    # ── Editor breakdown ──────────────────────────────────────────────────────
    total_editor = sum(editor_counts.values()) or 1
    editors_list: list[dict[str, Any]] = [
        {
            "name": name,
            "count": count,
            "pct": round(count / total_editor * 100, 1),
        }
        for name, count in editor_counts.items()
    ]
    editors_list.sort(key=lambda x: int(str(x["count"])), reverse=True)

    # ── Feature usage counts ──────────────────────────────────────────────────
    feature_keys = [
        ("copilot_ide_code_completions", "IDE completions"),
        ("copilot_ide_chat", "IDE chat"),
        ("copilot_dotcom_chat", "Dotcom chat"),
        ("copilot_dotcom_pull_requests", "PR summaries"),
    ]
    features_list: list[dict[str, Any]] = []
    for i, (key, label) in enumerate(feature_keys):
        total_engaged = 0
        for day_obj in days:
            section = day_obj.get(key) or {}
            total_engaged += section.get("total_engaged_users", 0)
        features_list.append(
            {
                "feature": label,
                "count": total_engaged,
                "color": _FEATURE_COLORS[i % len(_FEATURE_COLORS)],
            }
        )

    return {"models": models_list, "features": features_list, "editors": editors_list}


async def get_copilot_anomalies(db: AsyncSession) -> dict[str, Any]:
    """Data for the Anomalies pane: detect metric deviations from baselines."""
    try:
        raw = await _read_metrics_from_store(db)
    except Exception as exc:
        logger.error("copilot_anomalies.read_metrics_failed", error=str(exc), exc_info=True)
        return {
            "error": "internal_error",
            "message": f"Failed to read metrics: {type(exc).__name__}: {exc}",
        }
    if isinstance(raw, dict) and "error" in raw:
        return raw

    days: list[dict[str, Any]] = raw  # type: ignore[assignment]
    if len(days) < 4:
        return {"anomalies": []}

    anomalies: list[dict[str, Any]] = []
    anomaly_id = 0

    # Split into recent (last 3 days) and baseline (previous days)
    recent_days = days[-3:]
    baseline_days = days[:-3]

    if not baseline_days:
        return {"anomalies": []}

    # ── Acceptance rate anomalies ─────────────────────────────────────────────
    def _day_acceptance_rate(day_obj: dict[str, Any]) -> float:
        completions = day_obj.get("copilot_ide_code_completions") or {}
        sugg = 0
        acc = 0
        for editor in completions.get("editors", []):
            for model in editor.get("models", []):
                for lang in model.get("languages", []):
                    sugg += lang.get("total_code_suggestions", 0)
                    acc += lang.get("total_code_acceptances", 0)
        return (acc / sugg * 100) if sugg else 0.0

    baseline_rates = [_day_acceptance_rate(d) for d in baseline_days]
    recent_rates = [_day_acceptance_rate(d) for d in recent_days]

    baseline_avg = sum(baseline_rates) / len(baseline_rates) if baseline_rates else 0
    recent_avg = sum(recent_rates) / len(recent_rates) if recent_rates else 0

    if baseline_avg > 0:
        rate_change = baseline_avg - recent_avg  # positive = drop
        rate_change_pct = rate_change / baseline_avg * 100

        if rate_change_pct > 15:
            anomaly_id += 1
            anomalies.append(
                {
                    "id": anomaly_id,
                    "severity": "high",
                    "title": "Acceptance rate drop",
                    "description": (
                        f"Acceptance rate dropped {rate_change_pct:.0f}% "
                        f"(from {baseline_avg:.1f}% to {recent_avg:.1f}%) over the last 3 days."
                    ),
                    "timestamp": recent_days[-1].get("date", ""),
                    "team": "Enterprise-wide",
                }
            )
        elif rate_change_pct > 10:
            anomaly_id += 1
            anomalies.append(
                {
                    "id": anomaly_id,
                    "severity": "medium",
                    "title": "Acceptance rate decline",
                    "description": (
                        f"Acceptance rate declined {rate_change_pct:.0f}% "
                        f"(from {baseline_avg:.1f}% to {recent_avg:.1f}%) over the last 3 days."
                    ),
                    "timestamp": recent_days[-1].get("date", ""),
                    "team": "Enterprise-wide",
                }
            )
        elif rate_change_pct > 5:
            anomaly_id += 1
            anomalies.append(
                {
                    "id": anomaly_id,
                    "severity": "low",
                    "title": "Slight acceptance rate dip",
                    "description": (
                        f"Acceptance rate dipped {rate_change_pct:.0f}% "
                        f"(from {baseline_avg:.1f}% to {recent_avg:.1f}%) over the last 3 days."
                    ),
                    "timestamp": recent_days[-1].get("date", ""),
                    "team": "Enterprise-wide",
                }
            )

    # ── Active user count anomalies ───────────────────────────────────────────
    baseline_active = [d.get("total_active_users", 0) for d in baseline_days]
    recent_active = [d.get("total_active_users", 0) for d in recent_days]

    baseline_active_avg = sum(baseline_active) / len(baseline_active) if baseline_active else 0
    recent_active_avg = sum(recent_active) / len(recent_active) if recent_active else 0

    if baseline_active_avg > 0:
        active_change_pct = abs(recent_active_avg - baseline_active_avg) / baseline_active_avg * 100
        if active_change_pct > 20:
            direction = "increase" if recent_active_avg > baseline_active_avg else "decrease"
            anomaly_id += 1
            anomalies.append(
                {
                    "id": anomaly_id,
                    "severity": "high",
                    "title": f"Active user {direction}",
                    "description": (
                        f"Active users changed by {active_change_pct:.0f}% "
                        f"({baseline_active_avg:.0f} → {recent_active_avg:.0f})."
                    ),
                    "timestamp": recent_days[-1].get("date", ""),
                    "team": "Enterprise-wide",
                }
            )

    # ── Feature usage spike anomalies ─────────────────────────────────────────
    for feature_key, feature_label in (
        ("copilot_ide_code_completions", "IDE completions"),
        ("copilot_ide_chat", "IDE chat"),
        ("copilot_dotcom_chat", "Dotcom chat"),
        ("copilot_dotcom_pull_requests", "PR summaries"),
    ):
        baseline_engaged = [
            (d.get(feature_key) or {}).get("total_engaged_users", 0) for d in baseline_days
        ]
        recent_engaged = [
            (d.get(feature_key) or {}).get("total_engaged_users", 0) for d in recent_days
        ]

        bl_avg = sum(baseline_engaged) / len(baseline_engaged) if baseline_engaged else 0
        rc_avg = sum(recent_engaged) / len(recent_engaged) if recent_engaged else 0

        if bl_avg > 0:
            spike_pct = (rc_avg - bl_avg) / bl_avg * 100
            if spike_pct > 200:
                anomaly_id += 1
                anomalies.append(
                    {
                        "id": anomaly_id,
                        "severity": "medium",
                        "title": f"{feature_label} usage spike",
                        "description": (
                            f"{feature_label} engaged users spiked {spike_pct:.0f}% "
                            f"({bl_avg:.0f} → {rc_avg:.0f}) compared to baseline."
                        ),
                        "timestamp": recent_days[-1].get("date", ""),
                        "team": "Enterprise-wide",
                    }
                )

    return {"anomalies": anomalies}


# ── Team-level breakdown (#76) ────────────────────────────────────────────────


async def get_copilot_teams(db: AsyncSession) -> dict[str, Any]:
    """Aggregate per-user Copilot metrics by GitHub team membership.

    Cross-references seat data with org_teams and org_team_members tables
    to produce team-level adoption metrics.
    """
    seats_data = await _read_seats_from_store(db)
    if isinstance(seats_data, dict) and "error" in seats_data:
        return seats_data

    seats: list[dict[str, Any]] = seats_data  # type: ignore[assignment]

    # Build a map of login → seat info
    login_to_seat: dict[str, dict[str, Any]] = {}
    for seat in seats:
        assignee = seat.get("assignee") or {}
        login = assignee.get("login", "")
        if login:
            login_to_seat[login.lower()] = seat

    # Fetch team memberships from DB
    team_result = await db.execute(select(OrgTeam))
    teams = list(team_result.scalars().all())

    member_result = await db.execute(select(OrgTeamMember))
    members = list(member_result.scalars().all())

    # Build team → members mapping
    team_members_map: dict[str, list[str]] = {}
    for member in members:
        key = f"{member.org}/{member.team_slug}"
        if key not in team_members_map:
            team_members_map[key] = []
        team_members_map[key].append(member.github_login.lower())

    # Aggregate metrics per team
    team_data: list[dict[str, Any]] = []
    for team in teams:
        key = f"{team.org}/{team.team_slug}"
        team_logins = team_members_map.get(key, [])
        total_members = len(team_logins)

        active_count = 0
        inactive_count = 0
        total_days_since_activity = 0

        for login in team_logins:
            seat = login_to_seat.get(login)
            if seat:
                tier = _classify_user(seat)
                if tier in ("power", "regular"):
                    active_count += 1
                elif tier == "inactive":
                    inactive_count += 1
                else:
                    active_count += 1  # minimal counts as active

                last_act = seat.get("last_activity_at", "")
                total_days_since_activity += _days_since_last_activity(last_act)

        adoption_pct = round(active_count / total_members * 100, 1) if total_members > 0 else 0
        avg_days_inactive = (
            round(total_days_since_activity / total_members, 1) if total_members > 0 else 0
        )

        at_risk = adoption_pct < 30 and total_members >= 3

        team_data.append(
            {
                "team_slug": team.team_slug,
                "team_name": team.name,
                "org": team.org,
                "total_members": total_members,
                "active_users": active_count,
                "inactive_users": inactive_count,
                "adoption_pct": adoption_pct,
                "avg_days_since_activity": avg_days_inactive,
                "at_risk": at_risk,
            }
        )

    team_data.sort(key=lambda x: x["adoption_pct"], reverse=True)

    return {
        "teams": team_data,
        "total_teams": len(team_data),
        "at_risk_count": sum(1 for t in team_data if t["at_risk"]),
    }


# ── Adoption Blockers (#77) ──────────────────────────────────────────────────


async def get_copilot_blockers(db: AsyncSession) -> dict[str, Any]:
    """Identify and categorize Copilot adoption blockers.

    Cross-references seat data, policy events, and content exclusions to
    categorize blockers and generate actionable recommendations.
    """
    try:
        seats_data = await _read_seats_from_store(db)
    except Exception as exc:
        logger.error("copilot_blockers.read_seats_failed", error=str(exc), exc_info=True)
        return {
            "error": "internal_error",
            "message": f"Failed to read seat data: {type(exc).__name__}: {exc}",
        }
    if isinstance(seats_data, dict) and "error" in seats_data:
        return seats_data

    seats: list[dict[str, Any]] = seats_data  # type: ignore[assignment]

    # Categorize blockers
    blockers: list[dict[str, Any]] = []
    blocker_id = 0

    # Get team members who don't have seats (no_seat blocker)
    try:
        member_result = await db.execute(select(OrgTeamMember))
        all_members = list(member_result.scalars().all())
    except Exception as exc:
        logger.error("copilot_blockers.query_team_members_failed", error=str(exc), exc_info=True)
        return {
            "error": "internal_error",
            "message": f"Failed to query team members: {type(exc).__name__}: {exc}",
        }
    seat_logins = {
        (s.get("assignee") or {}).get("login", "").lower()
        for s in seats
        if (s.get("assignee") or {}).get("login")
    }

    no_seat_users: list[str] = []
    for member in all_members:
        if member.github_login.lower() not in seat_logins:
            if member.github_login.lower() not in no_seat_users:
                no_seat_users.append(member.github_login.lower())

    if no_seat_users:
        blocker_id += 1
        blockers.append(
            {
                "id": blocker_id,
                "category": "no_seat",
                "title": "Members without Copilot seats",
                "description": (
                    f"{len(no_seat_users)} team members don't have a Copilot seat assigned."
                ),
                "affected_users": no_seat_users[:50],
                "count": len(no_seat_users),
                "severity": "high" if len(no_seat_users) > 10 else "medium",
                "recommendation": "Assign Copilot seats to these team members to enable adoption.",
            }
        )

    # Inactive seats
    inactive_users: list[str] = []
    for seat in seats:
        tier = _classify_user(seat)
        if tier == "inactive":
            login = (seat.get("assignee") or {}).get("login", "unknown")
            inactive_users.append(login)

    if inactive_users:
        blocker_id += 1
        blockers.append(
            {
                "id": blocker_id,
                "category": "inactive_seat",
                "title": "Inactive seat holders",
                "description": (
                    f"{len(inactive_users)} users have Copilot seats but no recent activity."
                ),
                "affected_users": inactive_users[:50],
                "count": len(inactive_users),
                "severity": "medium",
                "recommendation": (
                    "Reach out to these users for onboarding support, "
                    "or reclaim seats for active developers."
                ),
            }
        )

    # Check for policy restrictions from copilot_policies table
    restrictive_policies: list[Any] = []
    try:
        from app.models.copilot_policy import CopilotPolicy

        policy_result = await db.execute(
            select(CopilotPolicy).where(CopilotPolicy.enabled.is_(True))
        )
        active_policies = list(policy_result.scalars().all())

        restrictive_policies = [
            p
            for p in active_policies
            if p.policy_type in ("content_exclusion", "model_restriction")
        ]
    except Exception as exc:
        logger.warning("copilot_blockers.query_policies_failed", error=str(exc), exc_info=True)
        active_policies = []
    if restrictive_policies:
        blocker_id += 1
        blockers.append(
            {
                "id": blocker_id,
                "category": "policy_restricted",
                "title": "Active restrictive policies",
                "description": (
                    f"{len(restrictive_policies)} active policies may limit Copilot functionality."
                ),
                "affected_users": [],
                "count": len(restrictive_policies),
                "severity": "low",
                "recommendation": (
                    "Review active policies to ensure they don't unnecessarily "
                    "restrict Copilot usage for your teams."
                ),
                "policies": [{"name": p.name, "type": p.policy_type} for p in restrictive_policies],
            }
        )

    # Quick wins
    quick_wins: list[dict[str, Any]] = []
    if inactive_users:
        quick_wins.append(
            {
                "action": "Reclaim inactive seats",
                "impact": f"Save ${len(inactive_users) * _COST_BUSINESS:.0f}/month",
                "effort": "low",
                "description": (f"Reclaim {len(inactive_users)} inactive seats to reduce waste."),
            }
        )
    if no_seat_users and len(no_seat_users) <= 20:
        quick_wins.append(
            {
                "action": "Assign seats to team members",
                "impact": f"Enable {len(no_seat_users)} more developers",
                "effort": "low",
                "description": "Assign Copilot seats to active team members without access.",
            }
        )

    return {
        "blockers": blockers,
        "quick_wins": quick_wins,
        "summary": {
            "total_blockers": len(blockers),
            "no_seat_count": len(no_seat_users),
            "inactive_count": len(inactive_users),
            "policy_restricted_count": len(restrictive_policies),
        },
    }


# ── Policy Change Timeline (#78) ─────────────────────────────────────────────


async def get_copilot_policy_changes(db: AsyncSession) -> dict[str, Any]:
    """Query audit events for Copilot policy changes.

    Searches the events table for ``copilot.*`` and ``copilot_policy.*``
    actions and returns a chronological timeline.
    """
    from app.models.audit_event import AuditEvent

    result = await db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.action.like("copilot%"),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(200)
    )
    events = list(result.scalars().all())

    timeline: list[dict[str, Any]] = []
    for event in events:
        data = event.data if hasattr(event, "data") and event.data else {}
        timeline.append(
            {
                "id": event.id,
                "action": event.action,
                "actor": event.actor or "system",
                "timestamp": event.created_at.isoformat() if event.created_at else "",
                "org": event.org or "",
                "old_value": data.get("old_value", data.get("previous_value", "")),
                "new_value": data.get("new_value", data.get("current_value", "")),
                "description": _describe_policy_action(event.action, data),
            }
        )

    return {
        "timeline": timeline,
        "total_changes": len(timeline),
    }


def _describe_policy_action(action: str, data: dict[str, Any]) -> str:
    """Generate a human-readable description for a policy change action."""
    descriptions: dict[str, str] = {
        "copilot.cfb_seat_assignment_created": "Copilot seat assigned",
        "copilot.cfb_seat_assignment_revoked": "Copilot seat revoked",
        "copilot.cfb_seat_cancelled": "Copilot seat cancelled",
        "copilot.content_exclusion_changed": "Content exclusion rules changed",
        "copilot_policy.update": "Copilot policy updated",
        "copilot_policy.create": "New Copilot policy created",
        "copilot_policy.delete": "Copilot policy deleted",
    }
    return descriptions.get(action, f"Copilot action: {action}")


# ── ROI & Cost Optimization (#85) ────────────────────────────────────────────


async def get_copilot_roi(db: AsyncSession) -> dict[str, Any]:
    """Comprehensive Copilot ROI report.

    Calculates seat cost, utilization, waste, savings opportunities,
    and generates cost optimization recommendations.
    """
    seats_data = await _read_seats_from_store(db)
    metrics_data = await _read_metrics_from_store(db)

    # Handle error cases
    if isinstance(seats_data, dict) and "error" in seats_data:
        return seats_data
    if isinstance(metrics_data, dict) and "error" in metrics_data:
        return metrics_data

    seats: list[dict[str, Any]] = seats_data  # type: ignore[assignment]
    days: list[dict[str, Any]] = metrics_data  # type: ignore[assignment]

    # Get cost config
    from app.models.org_config import OrgConfig

    config_result = await db.execute(select(OrgConfig).limit(1))
    org_config_row = config_result.scalars().first()
    cost_override: float | None = (
        float(org_config_row.copilot_cost_per_seat)
        if org_config_row and org_config_row.copilot_cost_per_seat is not None
        else None
    )

    # Seat analysis
    total_seats = len(seats)
    tier_counts = {"power": 0, "regular": 0, "minimal": 0, "inactive": 0}
    plan_counts: dict[str, int] = {}

    for seat in seats:
        tier = _classify_user(seat)
        tier_counts[tier] += 1
        plan_type = seat.get("plan_type", "business")
        plan_counts[plan_type] = plan_counts.get(plan_type, 0) + 1

    active_seats = tier_counts["power"] + tier_counts["regular"] + tier_counts["minimal"]
    inactive_seats = tier_counts["inactive"]

    # Cost calculations
    total_monthly_cost = 0.0
    for seat in seats:
        plan_type = seat.get("plan_type", "business")
        total_monthly_cost += _cost_for_plan(plan_type, cost_override)

    wasted_monthly = inactive_seats * _cost_for_plan("business", cost_override)
    utilization_pct = round(active_seats / total_seats * 100, 1) if total_seats > 0 else 0

    # Time-series cost efficiency (from metrics data)
    cost_trend: list[dict[str, Any]] = []
    for day_obj in days[-30:]:
        date_str = day_obj.get("date", "")
        active = day_obj.get("total_active_users", 0)
        completions = day_obj.get("copilot_ide_code_completions") or {}
        total_sugg = 0
        total_acc = 0
        for editor in completions.get("editors", []):
            for model in editor.get("models", []):
                for lang in model.get("languages", []):
                    total_sugg += lang.get("total_code_suggestions", 0)
                    total_acc += lang.get("total_code_acceptances", 0)

        cost_per_active = round(total_monthly_cost / 30 / active, 2) if active > 0 else 0
        acc_rate = round(total_acc / total_sugg * 100, 1) if total_sugg > 0 else 0

        cost_trend.append(
            {
                "date": date_str,
                "active_users": active,
                "acceptance_rate": acc_rate,
                "daily_cost_per_active_user": cost_per_active,
            }
        )

    # Recommendations
    recommendations: list[dict[str, Any]] = []

    if inactive_seats > 0:
        recommendations.append(
            {
                "type": "reclaim_seats",
                "title": f"Reclaim {inactive_seats} inactive seats",
                "impact": f"Save ${wasted_monthly:,.0f}/month (${wasted_monthly * 12:,.0f}/year)",
                "priority": "high",
                "description": (
                    f"{inactive_seats} seats have no activity in 30+ days. "
                    "Reclaim and redistribute to active developers."
                ),
            }
        )

    teams_data = await get_copilot_teams(db)
    if isinstance(teams_data, dict) and teams_data.get("at_risk_count", 0) > 0:
        at_risk = teams_data["at_risk_count"]
        recommendations.append(
            {
                "type": "enable_teams",
                "title": f"Enable {at_risk} at-risk teams",
                "impact": "Increase org-wide adoption",
                "priority": "medium",
                "description": (
                    f"{at_risk} teams have <30% Copilot adoption. "
                    "Targeted onboarding can improve overall utilization."
                ),
            }
        )

    if tier_counts["minimal"] > 5:
        recommendations.append(
            {
                "type": "activate_minimal",
                "title": f"Activate {tier_counts['minimal']} minimal users",
                "impact": "Better ROI from existing seats",
                "priority": "medium",
                "description": (
                    f"{tier_counts['minimal']} users have seats but minimal usage. "
                    "Consider training sessions or pairing with power users."
                ),
            }
        )

    return {
        "summary": {
            "total_seats": total_seats,
            "active_seats": active_seats,
            "inactive_seats": inactive_seats,
            "utilization_pct": utilization_pct,
            "total_monthly_cost": round(total_monthly_cost, 2),
            "wasted_monthly": round(wasted_monthly, 2),
            "annual_waste": round(wasted_monthly * 12, 2),
            "cost_per_active_user": (
                round(total_monthly_cost / active_seats, 2) if active_seats > 0 else 0
            ),
        },
        "tier_breakdown": tier_counts,
        "plan_breakdown": plan_counts,
        "cost_trend": cost_trend,
        "recommendations": recommendations,
    }
