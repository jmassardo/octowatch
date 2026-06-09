"""Copilot Metrics service — fetches real data from the GitHub Copilot Metrics API.

Uses org-level NDJSON Metrics Reports endpoints with per-org installation tokens.
Calls ``GET /orgs/{org}/copilot/metrics/reports/organization-28-day/latest`` for
each Organization GitHub App installation to obtain download links, fetches the
NDJSON files, parses line by line, then transforms into shaped payloads for all
frontend Copilot panes.

Also integrates the Copilot billing/seats API for per-user adoption data,
team-level aggregation, adoption blockers, and ROI analysis.

Results are cached in Valkey (25-hour TTL) to avoid excessive API round-trips.
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
from app.models.github_sync import GitHubAppConfig, GitHubAppInstallation, OrgTeam, OrgTeamMember
from app.services.github_token_service import GitHubAppTokenManager, GitHubAuthError

logger = structlog.get_logger(__name__)

_GITHUB_API_BASE = "https://api.github.com"

# GitHub REST API version — must be 2022-11-28 for Copilot billing/seats endpoints
_API_VERSION = "2022-11-28"

# Metrics NDJSON reports use a newer API version
_METRICS_API_VERSION = "2026-03-10"

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

# ROI calculation defaults
_AVG_DEV_COST_PER_LINE = 0.50
_AVG_MINUTES_SAVED_PER_CHAT_TURN = 2
_AVG_MINUTES_SAVED_PER_PR_SUMMARY = 10
_DEFAULT_HOURLY_RATE = 75.0


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
    from app.services.settings_service import get_setting

    enterprise_slug = (
        await get_setting(db, "github_enterprise_slug")
        or settings.github_app.GITHUB_ENTERPRISE_SLUG
    )
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
    from app.services.config_overlay import refresh_settings
    from app.services.settings_service import get_setting

    # Hydrate settings from app_settings DB — env vars may be blank when
    # credentials were configured via the UI after initial deployment.
    await refresh_settings(db)

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

    # Prefer app_settings over env var — env var may be blank when slug was
    # configured through the UI after initial deployment.
    enterprise_slug = (
        await get_setting(db, "github_enterprise_slug")
        or settings.github_app.GITHUB_ENTERPRISE_SLUG
    )
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


async def _get_org_tokens(
    db: AsyncSession,
) -> list[tuple[str, str]] | dict[str, str]:
    """Get installation tokens for all Organization-type GitHub App installations.

    Returns a list of ``(org_login, token)`` tuples on success, or an error dict
    if credentials are not configured.  Orgs where token generation fails are
    skipped with a warning log.
    """
    app_id = settings.github_app.GITHUB_APP_ID
    key_path = settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH
    private_key_pem = settings.github_app.GITHUB_APP_PRIVATE_KEY_PEM
    if not app_id or (not key_path and not private_key_pem):
        return {
            "error": "no_enterprise_config",
            "message": "GitHub App credentials (APP_ID / private key) are not configured.",
        }

    private_key = settings.github_app.resolve_private_key()
    if not private_key:
        return {
            "error": "no_enterprise_config",
            "message": "GitHub App private key could not be resolved.",
        }

    # Query all org installations from the database
    result = await db.execute(
        select(GitHubAppInstallation.target_login, GitHubAppInstallation.installation_id).where(
            GitHubAppInstallation.target_type == "Organization"
        )
    )
    org_installations = result.fetchall()

    if not org_installations:
        return {
            "error": "no_enterprise_config",
            "message": "No Organization-type GitHub App installations found in the database.",
        }

    # Create a single token manager with a Valkey client
    valkey_for_tokens = aioredis.Redis.from_url(
        settings.VALKEY_URL, decode_responses=True, max_connections=5
    )
    try:
        token_manager = GitHubAppTokenManager(
            app_id=int(app_id),
            private_key_pem=private_key,
            valkey_client=valkey_for_tokens,
        )

        org_tokens: list[tuple[str, str]] = []
        for org_login, installation_id in org_installations:
            try:
                token = await token_manager.get_installation_token(installation_id)
                org_tokens.append((org_login, token))
            except Exception as exc:
                logger.warning(
                    "copilot_metrics.org_token_failed",
                    org=org_login,
                    installation_id=installation_id,
                    error=str(exc),
                )
                continue
    finally:
        await valkey_for_tokens.aclose()

    if not org_tokens:
        return {
            "error": "copilot_not_available",
            "message": "Failed to obtain tokens for any org installation.",
        }

    return org_tokens


async def _fetch_metrics_raw(db: AsyncSession) -> list[dict[str, Any]] | dict[str, str]:
    """Fetch raw daily metrics from org-level Copilot Metrics NDJSON reports.

    Iterates over all Organization GitHub App installations, calls
    ``GET /orgs/{org}/copilot/metrics/reports/organization-28-day/latest``
    for each, downloads the NDJSON files, and aggregates results.

    Returns either the parsed list of daily metric dicts on success, or an
    error dict.  Results are cached in Valkey for ``_CACHE_TTL_SECONDS``.
    """
    # Check feature toggle first
    from app.services.config_overlay import refresh_settings
    from app.services.settings_service import get_setting

    # Hydrate settings from app_settings DB — env vars may be blank when
    # credentials were configured via the UI after initial deployment.
    await refresh_settings(db)

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

    enterprise_slug = (
        await get_setting(db, "github_enterprise_slug")
        or settings.github_app.GITHUB_ENTERPRISE_SLUG
    )
    if not enterprise_slug:
        return {"error": "no_enterprise_config", "message": "GITHUB_ENTERPRISE_SLUG is not set."}

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

    # ── Get org installation tokens ───────────────────────────────────────────
    org_tokens_result = await _get_org_tokens(db)
    if isinstance(org_tokens_result, dict):
        if valkey:
            await valkey.aclose()
        return org_tokens_result

    # ── Fetch NDJSON reports from each org ────────────────────────────────────
    all_metrics: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            for org_login, token in org_tokens_result:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "X-GitHub-Api-Version": _METRICS_API_VERSION,
                }

                report_url = (
                    f"{_GITHUB_API_BASE}/orgs/{org_login}"
                    f"/copilot/metrics/reports/organization-28-day/latest"
                )

                try:
                    resp = await client.get(report_url, headers=headers)
                    if resp.status_code in (403, 404):
                        logger.debug(
                            "copilot_metrics.org_report_unavailable",
                            org=org_login,
                            status=resp.status_code,
                        )
                        continue
                    if resp.status_code != 200:
                        logger.warning(
                            "copilot_metrics.org_report_error",
                            org=org_login,
                            status=resp.status_code,
                        )
                        continue

                    report_data = resp.json()
                    download_links = report_data.get("download_links", [])

                    # Download each NDJSON file immediately (signed URLs are short-lived)
                    for link in download_links:
                        try:
                            ndjson_resp = await client.get(link)
                            if ndjson_resp.status_code == 200:
                                records = _parse_ndjson(ndjson_resp.text)
                                # Tag each record with the org_slug
                                for record in records:
                                    record["_org_slug"] = org_login
                                all_metrics.extend(records)
                            else:
                                logger.warning(
                                    "copilot_metrics.ndjson_download_error",
                                    org=org_login,
                                    status=ndjson_resp.status_code,
                                )
                        except Exception:
                            logger.warning(
                                "copilot_metrics.ndjson_download_failed",
                                org=org_login,
                                exc_info=True,
                            )

                except Exception:
                    logger.warning(
                        "copilot_metrics.org_report_fetch_failed",
                        org=org_login,
                        exc_info=True,
                    )
                    continue

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
            await valkey.set(cache_key, json.dumps(all_metrics), ex=_CACHE_TTL_SECONDS)
            logger.debug("copilot_metrics.cache_write", enterprise=enterprise_slug)
    except Exception:
        logger.warning("copilot_metrics.cache_write_failed", exc_info=True)
    finally:
        if valkey:
            await valkey.aclose()

    return all_metrics


async def _fetch_copilot_seats(db: AsyncSession) -> list[dict[str, Any]] | dict[str, str]:
    """Fetch per-user Copilot seat data from the billing/seats API.

    Iterates over all Organization GitHub App installations, using per-org
    installation tokens to call ``GET /orgs/{org}/copilot/billing/seats``.
    Results are cached in Valkey.
    """
    from app.services.config_overlay import refresh_settings
    from app.services.settings_service import get_setting

    await refresh_settings(db)

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

    enterprise_slug = (
        await get_setting(db, "github_enterprise_slug")
        or settings.github_app.GITHUB_ENTERPRISE_SLUG
    )
    if not enterprise_slug:
        return {"error": "no_enterprise_config", "message": "GITHUB_ENTERPRISE_SLUG is not set."}

    # ── Check Valkey cache ────────────────────────────────────────────────────
    cache_key = _CACHE_SEATS_KEY.format(org_slug=enterprise_slug)
    valkey: aioredis.Redis | None = None
    try:
        valkey = aioredis.Redis.from_url(
            settings.VALKEY_URL, decode_responses=True, max_connections=5
        )
        cached = await valkey.get(cache_key)
        if cached:
            logger.debug("copilot_seats.cache_hit", enterprise=enterprise_slug)
            return json.loads(cached)  # type: ignore[no-any-return]
    except Exception:
        logger.warning("copilot_seats.cache_read_failed", exc_info=True)

    # ── Get org installation tokens ───────────────────────────────────────────
    org_tokens_result = await _get_org_tokens(db)
    if isinstance(org_tokens_result, dict):
        if valkey:
            await valkey.aclose()
        return org_tokens_result

    # ── Fetch seats from each org using per-org tokens ────────────────────────
    all_seats: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            for org_login, token in org_tokens_result:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": _API_VERSION,
                }

                page = 1
                while True:
                    seats_url = (
                        f"{_GITHUB_API_BASE}/orgs/{org_login}/copilot/billing/seats"
                        f"?per_page=100&page={page}"
                    )
                    resp = await client.get(seats_url, headers=headers)
                    if resp.status_code in (403, 404):
                        # Org doesn't have Copilot enabled — skip
                        logger.debug(
                            "copilot_seats.org_not_enabled",
                            org=org_login,
                            status=resp.status_code,
                        )
                        break
                    if resp.status_code != 200:
                        logger.warning(
                            "copilot_seats.api_error",
                            org=org_login,
                            status=resp.status_code,
                        )
                        break
                    data = resp.json()
                    seats = data.get("seats", [])
                    for seat in seats:
                        seat["_org_slug"] = org_login
                    all_seats.extend(seats)
                    if len(seats) < 100:
                        break
                    page += 1

    except Exception as exc:
        logger.error("copilot_seats.fetch_failed", error=str(exc), exc_info=True)
        if valkey:
            await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": "Failed to fetch Copilot seat data from GitHub API.",
        }

    # ── Cache the result ──────────────────────────────────────────────────────
    try:
        if valkey:
            await valkey.set(cache_key, json.dumps(all_seats), ex=_CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("copilot_seats.cache_write_failed", exc_info=True)
    finally:
        if valkey:
            await valkey.aclose()

    return all_seats


def _classify_user(
    seat: dict[str, Any],
    *,
    power_days: int = 3,
    regular_days: int = 14,
    minimal_days: int = 30,
) -> str:
    """Classify a seat user into power/regular/minimal/inactive tier.

    Thresholds are days-since-last-activity boundaries:
    - power: active within ``power_days``
    - regular: active within ``regular_days``
    - minimal: active within ``minimal_days``
    - inactive: no activity within ``minimal_days``
    """
    last_activity = seat.get("last_activity_at")
    if not last_activity:
        return "inactive"
    try:
        last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "inactive"

    now = datetime.now(UTC)
    days_since = (now - last_dt).days
    if days_since <= power_days:
        return "power"
    if days_since <= regular_days:
        return "regular"
    if days_since <= minimal_days:
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

    enterprise_slug = (
        await get_setting(db, "github_enterprise_slug")
        or settings.github_app.GITHUB_ENTERPRISE_SLUG
    )
    if not enterprise_slug:
        return {"error": "no_enterprise_config", "message": "GITHUB_ENTERPRISE_SLUG is not set."}

    return None


async def _read_metrics_from_store(db: AsyncSession) -> list[dict[str, Any]] | dict[str, str]:
    """Read Copilot metrics from Valkey cache or DB.  Never calls GitHub API.

    Returns the same shape as ``_fetch_metrics_raw`` (list of daily metric
    dicts) so that all downstream public functions work unchanged.
    """
    from app.services.settings_service import get_setting

    err = await _check_feature_enabled(db)
    if err is not None:
        return err

    enterprise_slug = (
        await get_setting(db, "github_enterprise_slug")
        or settings.github_app.GITHUB_ENTERPRISE_SLUG
        or ""
    )

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
    """Reconstruct the raw API response shape from ``CopilotDailyMetric`` rows.

    Queries all orgs (not filtered by enterprise_slug which doesn't match
    the stored org_slug values).
    """
    from app.models.copilot_metrics import CopilotDailyMetric

    result = await db.execute(select(CopilotDailyMetric).order_by(CopilotDailyMetric.date))
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
    from app.services.settings_service import get_setting

    err = await _check_feature_enabled(db)
    if err is not None:
        return err

    enterprise_slug = (
        await get_setting(db, "github_enterprise_slug")
        or settings.github_app.GITHUB_ENTERPRISE_SLUG
        or ""
    )

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
    """Data for the Overview pane: acceptance rates, language breakdown, user counts.

    Queries copilot_daily_metrics directly for reliable aggregates regardless
    of cache format.
    """
    from app.models.copilot_metrics import CopilotDailyMetric

    err = await _check_feature_enabled(db)
    if err is not None:
        return err

    # Query summary rows for acceptance rate (last 7 days)
    summary_result = await db.execute(
        select(
            CopilotDailyMetric.date,
            CopilotDailyMetric.active_users,
            CopilotDailyMetric.engaged_users,
            CopilotDailyMetric.total_suggestions,
            CopilotDailyMetric.total_acceptances,
        )
        .where(CopilotDailyMetric.metric_type == "summary")
        .order_by(CopilotDailyMetric.date.desc())
        .limit(28)
    )
    summary_rows = list(summary_result.all())

    if not summary_rows:
        # Fall back to cache/API path for fresh installations
        raw = await _read_metrics_from_store(db)
        if isinstance(raw, dict) and "error" in raw:
            return raw
        if isinstance(raw, list) and raw:
            return _build_overview_from_raw(raw)
        return {
            "acceptance_rate_days": [],
            "acceptance_rate_values": [],
            "acceptance_threshold": 25,
            "languages": [],
            "total_active_users": 0,
            "total_engaged_users": 0,
        }

    # Reverse to chronological order and take last 7
    summary_rows.reverse()
    recent = summary_rows[-7:] if len(summary_rows) >= 7 else summary_rows

    rate_labels: list[str] = []
    rate_values: list[float] = []
    for row in recent:
        rate_labels.append(_DAY_LABELS[row.date.weekday()])
        pct = (
            (row.total_acceptances / row.total_suggestions * 100) if row.total_suggestions else 0.0
        )
        rate_values.append(round(pct, 1))

    # Language breakdown from DB (all available days)
    from sqlalchemy import desc, func

    lang_result = await db.execute(
        select(
            CopilotDailyMetric.language,
            func.sum(CopilotDailyMetric.total_suggestions).label("total_sugg"),
            func.sum(CopilotDailyMetric.total_acceptances).label("total_acc"),
        )
        .where(
            CopilotDailyMetric.metric_type == "completions",
            CopilotDailyMetric.language.isnot(None),
            CopilotDailyMetric.model.is_(None),
        )
        .group_by(CopilotDailyMetric.language)
        .order_by(desc("total_sugg"))
        .limit(10)
    )
    lang_rows = list(lang_result.all())
    grand_total = sum(row.total_sugg for row in lang_rows) or 1
    lang_items: list[dict[str, Any]] = [
        {
            "lang": row.language,
            "pct": round(row.total_sugg / grand_total * 100, 1),
            "color": _lang_color(row.language),
        }
        for row in lang_rows
    ]

    # Latest user counts
    latest = summary_rows[-1] if summary_rows else None
    total_active = latest.active_users if latest else 0
    total_engaged = latest.engaged_users if latest else 0

    return {
        "acceptance_rate_days": rate_labels,
        "acceptance_rate_values": rate_values,
        "acceptance_threshold": 25,
        "languages": lang_items,
        "total_active_users": total_active,
        "total_engaged_users": total_engaged,
    }


def _build_overview_from_raw(days: list[dict[str, Any]]) -> dict[str, Any]:
    """Build overview payload from raw NDJSON records (cache fallback).

    Handles both old nested format and new day_totals format.
    """
    # Flatten day_totals if present (new NDJSON format)
    flat_days: list[dict[str, Any]] = []
    for record in days:
        day_totals = record.get("day_totals", [])
        if day_totals:
            flat_days.extend(day_totals)
        elif record.get("date") or record.get("day"):
            flat_days.append(record)

    if not flat_days:
        return {
            "acceptance_rate_days": [],
            "acceptance_rate_values": [],
            "acceptance_threshold": 25,
            "languages": [],
            "total_active_users": 0,
            "total_engaged_users": 0,
        }

    # Sort by date
    flat_days.sort(key=lambda d: d.get("day", "") or d.get("date", ""))
    recent = flat_days[-7:] if len(flat_days) >= 7 else flat_days

    rate_labels: list[str] = []
    rate_values: list[float] = []
    for day_obj in recent:
        date_str = day_obj.get("day", "") or day_obj.get("date", "")
        try:
            dt = datetime.fromisoformat(date_str)
            rate_labels.append(_DAY_LABELS[dt.weekday()])
        except (ValueError, TypeError):
            rate_labels.append("?")

        # New format: top-level counts
        total_suggestions = day_obj.get("code_generation_activity_count", 0)
        total_acceptances = day_obj.get("code_acceptance_activity_count", 0)

        # Old format fallback
        if not total_suggestions:
            completions = day_obj.get("copilot_ide_code_completions") or {}
            for editor in completions.get("editors", []):
                for model in editor.get("models", []):
                    for lang in model.get("languages", []):
                        total_suggestions += lang.get("total_code_suggestions", 0)
                        total_acceptances += lang.get("total_code_acceptances", 0)

        pct = (total_acceptances / total_suggestions * 100) if total_suggestions else 0.0
        rate_values.append(round(pct, 1))

    # Language breakdown
    lang_suggestions: dict[str, int] = {}
    for day_obj in flat_days:
        # New format: totals_by_language_feature
        for lf in day_obj.get("totals_by_language_feature", []):
            name = lf.get("language", "Unknown")
            lang_suggestions[name] = lang_suggestions.get(name, 0) + lf.get(
                "code_generation_activity_count", 0
            )

        # Old format fallback
        if not lang_suggestions:
            completions = day_obj.get("copilot_ide_code_completions") or {}
            for editor in completions.get("editors", []):
                for model in editor.get("models", []):
                    for lang_obj in model.get("languages", []):
                        name = lang_obj.get("name", "Unknown")
                        lang_suggestions[name] = lang_suggestions.get(name, 0) + lang_obj.get(
                            "total_code_suggestions", 0
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

    # Active/engaged users
    latest = flat_days[-1] if flat_days else {}
    total_active = latest.get("daily_active_users", 0) or latest.get("total_active_users", 0)
    total_engaged = latest.get("monthly_active_users", 0) or latest.get("total_engaged_users", 0)

    return {
        "acceptance_rate_days": rate_labels,
        "acceptance_rate_values": rate_values,
        "acceptance_threshold": 25,
        "languages": lang_items[:10],
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
            "regular_users": [],
            "feature_adoption": [],
            "minimal_users": [],
            "inactive_users": [],
        }

    num_days = len(days)

    # ── Try to get per-user usage data first (most accurate) ──────────────────
    has_usage_data = False
    usage_tiers: dict[str, str] = {}
    usage_credits: dict[str, float] = {}
    usage_active_days: dict[str, int] = {}
    usage_last_active: dict[str, str] = {}

    try:
        from sqlalchemy import func as sa_func

        from app.models.copilot_usage import CopilotUsageReport

        now = datetime.now(UTC)
        period_start = (now - __import__("datetime").timedelta(days=28)).date()

        usage_result = await db.execute(
            select(
                CopilotUsageReport.github_login,
                sa_func.avg(CopilotUsageReport.total_credits_consumed).label("avg_daily"),
                sa_func.sum(CopilotUsageReport.total_credits_consumed).label("total"),
                sa_func.count(CopilotUsageReport.report_date).label("active_days"),
                sa_func.max(CopilotUsageReport.report_date).label("last_active_date"),
            )
            .where(CopilotUsageReport.report_date >= period_start)
            .group_by(CopilotUsageReport.github_login)
        )
        usage_rows = usage_result.fetchall()
        if usage_rows:
            has_usage_data = True
            for urow in usage_rows:
                login = urow[0]
                avg_daily = float(urow[1] or 0)
                total_credits = float(urow[2] or 0)
                active_days = int(urow[3] or 0)
                last_active_date = urow[4]
                usage_credits[login] = total_credits
                usage_active_days[login] = active_days
                if last_active_date is not None:
                    # Handle both date objects and strings
                    if hasattr(last_active_date, "isoformat"):
                        usage_last_active[login] = last_active_date.isoformat()
                    else:
                        usage_last_active[login] = str(last_active_date)

                # Classify by actual credit usage
                if avg_daily >= 5.0 and active_days >= 15:
                    usage_tiers[login] = "power"
                elif avg_daily >= 1.0 and active_days >= 7:
                    usage_tiers[login] = "regular"
                elif active_days >= 1:
                    usage_tiers[login] = "minimal"
                else:
                    usage_tiers[login] = "inactive"
    except Exception:
        logger.debug("copilot_adoption.usage_data_fallback", exc_info=True)

    # ── Try to get per-user data from seats API ───────────────────────────────
    try:
        seats_data = await _read_seats_from_store(db)
        has_seat_data = isinstance(seats_data, list) and len(seats_data) > 0
    except Exception:
        logger.debug("copilot_adoption.seats_fetch_fallback", exc_info=True)
        seats_data = []
        has_seat_data = False

    power_users: list[dict[str, Any]] = []
    regular_users: list[dict[str, Any]] = []
    minimal_users: list[dict[str, Any]] = []
    inactive_users: list[dict[str, Any]] = []
    tier_counts = {"power": 0, "regular": 0, "minimal": 0, "inactive": 0}

    if has_usage_data and usage_tiers:
        # Use actual usage data for tier classification
        for login, tier in usage_tiers.items():
            tier_counts[tier] += 1
            credits = usage_credits.get(login, 0)
            user_days_active = usage_active_days.get(login, 0)
            last_active = usage_last_active.get(login, "")

            if tier == "power":
                power_users.append(
                    {
                        "user": login,
                        "days_active": user_days_active,
                        "features_used": 3,
                        "last_activity": last_active,
                        "editor": "VS Code",
                        "credits_consumed": round(credits, 2),
                    }
                )
            elif tier == "regular":
                regular_users.append(
                    {
                        "user": login,
                        "days_active": user_days_active,
                        "features_used": 2,
                        "last_activity": last_active,
                        "editor": "VS Code",
                        "credits_consumed": round(credits, 2),
                    }
                )
            elif tier == "minimal":
                minimal_users.append(
                    {
                        "user": login,
                        "days_active": user_days_active,
                        "last_feature": "completions",
                        "last_activity": last_active,
                        "credits_consumed": round(credits, 2),
                    }
                )
            elif tier == "inactive":
                inactive_users.append(
                    {
                        "user": login,
                        "days_active": 0,
                        "last_feature": "",
                        "last_activity": "",
                        "credits_consumed": round(credits, 2),
                    }
                )

        # Also account for seated users with no usage data
        if has_seat_data and isinstance(seats_data, list):
            usage_logins = set(usage_tiers.keys())
            for seat in seats_data:
                assignee = seat.get("assignee") or {}
                login = assignee.get("login", "")
                if login and login not in usage_logins:
                    tier_counts["inactive"] += 1
                    inactive_users.append(
                        {
                            "user": login,
                            "days_active": 0,
                            "last_feature": "",
                            "last_activity": "",
                            "credits_consumed": 0,
                        }
                    )

    elif has_seat_data:
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
            elif tier == "regular":
                regular_users.append(
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
            elif tier == "inactive":
                inactive_users.append(
                    {
                        "user": login,
                        "days_active": 0,
                        "last_feature": "",
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
    total_seats_count = len(seats_data) if has_seat_data and isinstance(seats_data, list) else 0
    latest_engaged = latest.get("total_engaged_users", 0) or 1

    completions_users = (latest.get("copilot_ide_code_completions") or {}).get(
        "total_engaged_users", 0
    )
    chat_users = (latest.get("copilot_ide_chat") or {}).get("total_engaged_users", 0)
    dotcom_chat_users = (latest.get("copilot_dotcom_chat") or {}).get("total_engaged_users", 0)
    pr_users = (latest.get("copilot_dotcom_pull_requests") or {}).get("total_engaged_users", 0)

    # Calculate 7-day trends
    def _feature_trend_7d(feature_key: str) -> float:
        """Calculate 7-day trend as percentage change."""
        if len(days) < 14:
            return 0.0
        recent_7 = days[-7:]
        prev_7 = days[-14:-7]
        recent_avg = (
            float(sum((d.get(feature_key) or {}).get("total_engaged_users", 0) for d in recent_7))
            / 7
        )
        prev_avg = (
            float(sum((d.get(feature_key) or {}).get("total_engaged_users", 0) for d in prev_7)) / 7
        )
        if prev_avg == 0:
            return 0.0
        return float(round((recent_avg - prev_avg) / prev_avg * 100, 1))

    feature_adoption: list[dict[str, Any]] = [
        {
            "feature": "IDE completions",
            "active_users": completions_users,
            "total_seats": total_seats_count,
            "pct": round(completions_users / latest_engaged * 100, 1),
            "trend_7d": _feature_trend_7d("copilot_ide_code_completions"),
            "color": _COLOR_GREEN,
        },
        {
            "feature": "IDE chat",
            "active_users": chat_users,
            "total_seats": total_seats_count,
            "pct": round(chat_users / latest_engaged * 100, 1),
            "trend_7d": _feature_trend_7d("copilot_ide_chat"),
            "color": _COLOR_BLUE,
        },
        {
            "feature": "Dotcom chat",
            "active_users": dotcom_chat_users,
            "total_seats": total_seats_count,
            "pct": round(dotcom_chat_users / latest_engaged * 100, 1),
            "trend_7d": _feature_trend_7d("copilot_dotcom_chat"),
            "color": _COLOR_PURPLE,
        },
        {
            "feature": "PR summaries",
            "active_users": pr_users,
            "total_seats": total_seats_count,
            "pct": round(pr_users / latest_engaged * 100, 1),
            "trend_7d": _feature_trend_7d("copilot_dotcom_pull_requests"),
            "color": _COLOR_ORANGE,
        },
    ]

    return {
        "tiers": tiers,
        "total_adoption": total_adoption,
        "power_users": power_users,
        "regular_users": regular_users,
        "feature_adoption": feature_adoption,
        "minimal_users": minimal_users,
        "inactive_users": inactive_users,
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
    """Data for the Models pane: model usage, feature counts, editors.

    Queries copilot_daily_metrics directly for reliable aggregates.
    """
    from app.models.copilot_metrics import CopilotDailyMetric

    err = await _check_feature_enabled(db)
    if err is not None:
        return err

    # ── Model usage from language_model rows ──────────────────────────────────
    from sqlalchemy import desc, func

    model_result = await db.execute(
        select(
            CopilotDailyMetric.model,
            func.sum(CopilotDailyMetric.total_suggestions).label("total_sugg"),
            func.sum(CopilotDailyMetric.engaged_users).label("total_engaged"),
        )
        .where(
            CopilotDailyMetric.model.isnot(None),
        )
        .group_by(CopilotDailyMetric.model)
        .order_by(desc("total_engaged"))
        .limit(10)
    )
    model_rows = list(model_result.all())
    total_model = sum(row.total_engaged for row in model_rows) or 1
    models_list: list[dict[str, Any]] = [
        {
            "model": row.model,
            "pct": round(row.total_engaged / total_model * 100, 1),
            "color": _MODEL_COLORS[i % len(_MODEL_COLORS)],
        }
        for i, row in enumerate(model_rows)
    ]

    # ── Editor breakdown ──────────────────────────────────────────────────────
    editor_result = await db.execute(
        select(
            CopilotDailyMetric.editor,
            func.sum(CopilotDailyMetric.total_suggestions).label("total_sugg"),
            func.sum(CopilotDailyMetric.total_acceptances).label("total_acc"),
        )
        .where(
            CopilotDailyMetric.metric_type == "completions",
            CopilotDailyMetric.editor.isnot(None),
        )
        .group_by(CopilotDailyMetric.editor)
        .order_by(desc("total_sugg"))
        .limit(10)
    )
    editor_rows = list(editor_result.all())
    total_editor = sum(row.total_sugg for row in editor_rows) or 1
    editors_list: list[dict[str, Any]] = [
        {
            "name": row.editor,
            "count": row.total_sugg,
            "pct": round(row.total_sugg / total_editor * 100, 1),
        }
        for row in editor_rows
    ]

    # ── Feature usage counts ──────────────────────────────────────────────────
    feature_type_map = {
        "completions": "IDE completions",
        "chat": "IDE chat",
        "dotcom_chat": "Dotcom chat",
        "pr": "PR summaries",
    }
    feature_result = await db.execute(
        select(
            CopilotDailyMetric.metric_type,
            func.sum(CopilotDailyMetric.engaged_users).label("total_engaged"),
        )
        .where(
            CopilotDailyMetric.metric_type.in_(list(feature_type_map.keys())),
            CopilotDailyMetric.language.is_(None),
            CopilotDailyMetric.editor.is_(None),
            CopilotDailyMetric.model.is_(None),
        )
        .group_by(CopilotDailyMetric.metric_type)
    )
    feature_rows = list(feature_result.all())
    features_list: list[dict[str, Any]] = []
    for i, row in enumerate(feature_rows):
        label = feature_type_map.get(row.metric_type, row.metric_type)
        features_list.append(
            {
                "feature": label,
                "count": row.total_engaged,
                "color": _FEATURE_COLORS[i % len(_FEATURE_COLORS)],
            }
        )
    features_list.sort(key=lambda x: int(str(x["count"])), reverse=True)

    # If DB has no data, fall back to cache
    if not models_list and not editors_list and not features_list:
        raw = await _read_metrics_from_store(db)
        if isinstance(raw, list) and raw:
            return _build_models_from_raw(raw)

    return {"models": models_list, "features": features_list, "editors": editors_list}


def _build_models_from_raw(days: list[dict[str, Any]]) -> dict[str, Any]:
    """Build models payload from raw NDJSON records (cache fallback).

    Handles both old nested format and new day_totals format.
    """
    # Flatten day_totals if present
    flat_days: list[dict[str, Any]] = []
    for record in days:
        day_totals = record.get("day_totals", [])
        if day_totals:
            flat_days.extend(day_totals)
        elif record.get("date") or record.get("day"):
            flat_days.append(record)

    if not flat_days:
        return {"models": [], "features": [], "editors": []}

    model_counts: dict[str, int] = {}
    editor_counts: dict[str, int] = {}
    feature_counts: dict[str, int] = {}

    for day_obj in flat_days:
        # New format: totals_by_model_feature
        for mf in day_obj.get("totals_by_model_feature", []):
            model_name = mf.get("model", "Unknown")
            interactions = mf.get("user_initiated_interaction_count", 0)
            model_counts[model_name] = model_counts.get(model_name, 0) + interactions

        # New format: totals_by_ide
        for ide in day_obj.get("totals_by_ide", []):
            ide_name = ide.get("ide", "Unknown")
            sugg = ide.get("code_generation_activity_count", 0)
            editor_counts[ide_name] = editor_counts.get(ide_name, 0) + sugg

        # New format: totals_by_feature
        for feat in day_obj.get("totals_by_feature", []):
            feat_name = feat.get("feature", "Unknown")
            interactions = feat.get("user_initiated_interaction_count", 0)
            feature_counts[feat_name] = feature_counts.get(feat_name, 0) + interactions

        # Old format fallback
        if not model_counts and not editor_counts:
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

        # Old format feature extraction
        if not feature_counts:
            old_feature_keys = [
                ("copilot_ide_code_completions", "code_completion"),
                ("copilot_ide_chat", "copilot_chat"),
                ("copilot_dotcom_chat", "dotcom_chat"),
                ("copilot_dotcom_pull_requests", "copilot_pull_request"),
            ]
            for key, feat_name in old_feature_keys:
                section = day_obj.get(key) or {}
                engaged = section.get("total_engaged_users", 0)
                if engaged:
                    feature_counts[feat_name] = feature_counts.get(feat_name, 0) + engaged

    # Build response
    total_model = sum(model_counts.values()) or 1
    models_list = [
        {
            "model": name,
            "pct": round(count / total_model * 100, 1),
            "color": _MODEL_COLORS[i % len(_MODEL_COLORS)],
        }
        for i, (name, count) in enumerate(
            sorted(model_counts.items(), key=lambda x: x[1], reverse=True)
        )
    ]

    total_editor = sum(editor_counts.values()) or 1
    editors_list = [
        {
            "name": name,
            "count": count,
            "pct": round(count / total_editor * 100, 1),
        }
        for name, count in sorted(editor_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    feature_label_map = {
        "code_completion": "IDE completions",
        "copilot_chat": "IDE chat",
        "copilot_cli": "CLI",
        "dotcom_chat": "Dotcom chat",
        "copilot_pull_request": "PR summaries",
    }
    features_list = [
        {
            "feature": feature_label_map.get(name, name),
            "count": count,
            "color": _FEATURE_COLORS[i % len(_FEATURE_COLORS)],
        }
        for i, (name, count) in enumerate(
            sorted(feature_counts.items(), key=lambda x: x[1], reverse=True)
        )
    ]

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

    # ── Sudden drop: daily active users drops >30% from 7-day average ─────────
    if len(days) >= 8:
        last_7_active = [d.get("total_active_users", 0) for d in days[-8:-1]]
        avg_7d = sum(last_7_active) / len(last_7_active) if last_7_active else 0
        latest_active = days[-1].get("total_active_users", 0)
        if avg_7d > 0:
            drop_pct = (avg_7d - latest_active) / avg_7d * 100
            if drop_pct > 30:
                anomaly_id += 1
                anomalies.append(
                    {
                        "id": anomaly_id,
                        "severity": "high",
                        "title": "Sudden active user drop",
                        "description": (
                            f"Daily active users dropped {drop_pct:.0f}% "
                            f"from 7-day average ({avg_7d:.0f} → {latest_active}). "
                            "This may indicate an outage, policy change, or tooling issue."
                        ),
                        "timestamp": days[-1].get("date", ""),
                        "team": "Enterprise-wide",
                        "affected_count": int(avg_7d - latest_active),
                    }
                )

    # ── Model switching: >20% of users switch to a different model in a day ──
    if len(days) >= 2:

        def _get_model_distribution(day_obj: dict[str, Any]) -> dict[str, int]:
            dist: dict[str, int] = {}
            for feature_key in ("copilot_ide_code_completions", "copilot_ide_chat"):
                feature = day_obj.get(feature_key) or {}
                for editor in feature.get("editors", []):
                    for model in editor.get("models", []):
                        model_name = model.get("name", "Unknown")
                        engaged = model.get("total_engaged_users", 0)
                        dist[model_name] = dist.get(model_name, 0) + engaged
            return dist

        prev_dist = _get_model_distribution(days[-2])
        curr_dist = _get_model_distribution(days[-1])
        all_models_set = set(prev_dist.keys()) | set(curr_dist.keys())
        total_prev = sum(prev_dist.values()) or 1
        total_curr = sum(curr_dist.values()) or 1

        max_share_change = 0.0
        switched_model = ""
        for m in all_models_set:
            prev_share = prev_dist.get(m, 0) / total_prev * 100
            curr_share = curr_dist.get(m, 0) / total_curr * 100
            change = abs(curr_share - prev_share)
            if change > max_share_change:
                max_share_change = change
                switched_model = m

        if max_share_change > 20:
            anomaly_id += 1
            anomalies.append(
                {
                    "id": anomaly_id,
                    "severity": "medium",
                    "title": "Significant model switching detected",
                    "description": (
                        f"Model '{switched_model}' usage share changed by "
                        f"{max_share_change:.0f}% in one day. This may indicate "
                        "a model rollout or configuration change."
                    ),
                    "timestamp": days[-1].get("date", ""),
                    "team": "Enterprise-wide",
                    "affected_count": abs(
                        curr_dist.get(switched_model, 0) - prev_dist.get(switched_model, 0)
                    ),
                }
            )

    # ── Bulk policy change detection ──────────────────────────────────────────
    try:
        from app.models.audit_event import AuditEvent

        now = datetime.now(UTC)
        one_day_ago = now.replace(hour=0, minute=0, second=0, microsecond=0)
        policy_result = await db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.action.like("copilot%"),
                AuditEvent.created_at >= one_day_ago,
            )
            .limit(100)
        )
        recent_policy_events = list(policy_result.scalars().all())
        if len(recent_policy_events) > 5:
            anomaly_id += 1
            anomalies.append(
                {
                    "id": anomaly_id,
                    "severity": "high",
                    "title": "Bulk policy changes detected",
                    "description": (
                        f"{len(recent_policy_events)} Copilot policy changes detected "
                        "in the last 24 hours. This unusual volume may indicate "
                        "unauthorized changes or a misconfigured automation."
                    ),
                    "timestamp": now.isoformat(),
                    "team": "Enterprise-wide",
                    "affected_count": len(recent_policy_events),
                }
            )
    except Exception:
        logger.debug("copilot_anomalies.policy_check_skipped", exc_info=True)

    # Sort anomalies by severity (high first) then recency
    severity_order = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda a: (severity_order.get(a["severity"], 3), a.get("id", 0)))

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
            seat_info = login_to_seat.get(login)
            if seat_info:
                tier = _classify_user(seat_info)
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

    # ── Enhanced ROI calculations ─────────────────────────────────────────────
    # Extract productivity metrics from daily data
    total_lines_accepted = 0
    total_days_with_data = 0
    total_chat_turns = 0
    total_pr_summaries = 0

    for day_obj in days:
        completions = day_obj.get("copilot_ide_code_completions") or {}
        day_lines = 0
        for editor in completions.get("editors", []):
            for model in editor.get("models", []):
                for lang in model.get("languages", []):
                    day_lines += lang.get("total_code_lines_accepted", 0)
        if day_lines > 0:
            total_lines_accepted += day_lines
            total_days_with_data += 1

        # Estimate chat turns from engaged users (each engaged user ≈ 5 turns/day)
        chat_engaged = (day_obj.get("copilot_ide_chat") or {}).get("total_engaged_users", 0)
        dotcom_chat_engaged = (day_obj.get("copilot_dotcom_chat") or {}).get(
            "total_engaged_users", 0
        )
        total_chat_turns += (chat_engaged + dotcom_chat_engaged) * 5

        # PR summaries from engaged users
        pr_engaged = (day_obj.get("copilot_dotcom_pull_requests") or {}).get(
            "total_engaged_users", 0
        )
        total_pr_summaries += pr_engaged

    avg_lines_per_day = total_lines_accepted / total_days_with_data if total_days_with_data else 0
    avg_chat_turns_per_day = total_chat_turns / len(days) if days else 0
    avg_pr_summaries_per_day = total_pr_summaries / len(days) if days else 0

    # Value stream calculations (monthly, 22 working days)
    working_days = 22
    completion_value = round(avg_lines_per_day * _AVG_DEV_COST_PER_LINE * working_days, 2)
    chat_savings = round(
        avg_chat_turns_per_day
        * _AVG_MINUTES_SAVED_PER_CHAT_TURN
        * _DEFAULT_HOURLY_RATE
        / 60
        * working_days,
        2,
    )
    pr_summary_savings = round(
        avg_pr_summaries_per_day
        * _AVG_MINUTES_SAVED_PER_PR_SUMMARY
        * _DEFAULT_HOURLY_RATE
        / 60
        * working_days,
        2,
    )

    total_value = round(completion_value + chat_savings + pr_summary_savings, 2)
    total_roi = round(total_value - total_monthly_cost, 2)
    roi_ratio = round(total_value / total_monthly_cost, 2) if total_monthly_cost > 0 else 0.0

    # Breakeven analysis
    breakeven_additional_users: int | None = None
    if roi_ratio < 1.0 and active_seats > 0 and total_value > 0:
        value_per_user = total_value / active_seats if active_seats > 0 else 0
        if value_per_user > 0:
            deficit = total_monthly_cost - total_value
            breakeven_additional_users = max(1, int(deficit / value_per_user) + 1)

    # Ghost members: seats with 0 activity in last 60+ days
    ghost_members: list[dict[str, Any]] = []
    for seat in seats:
        assignee = seat.get("assignee") or {}
        login = assignee.get("login", "unknown")
        last_activity = seat.get("last_activity_at", "")
        days_inactive = _days_since_last_activity(last_activity)
        if days_inactive >= 60:
            ghost_members.append(
                {
                    "user": login,
                    "last_activity": last_activity if last_activity else "Never",
                    "days_inactive": days_inactive,
                    "plan_type": seat.get("plan_type", "business"),
                }
            )

    # Growth forecast: linear projection
    daily_active_users = [d.get("total_active_users", 0) for d in days]
    growth_forecast: dict[str, Any] = {}
    if len(daily_active_users) >= 7:
        recent_avg = sum(daily_active_users[-7:]) / 7
        older_avg = sum(daily_active_users[:7]) / 7 if len(daily_active_users) >= 14 else recent_avg
        if older_avg > 0 and len(daily_active_users) >= 14:
            weekly_growth_rate = (recent_avg - older_avg) / older_avg
            monthly_growth_rate = weekly_growth_rate * 4
            projected_users_30d = int(recent_avg * (1 + monthly_growth_rate))
            projected_users_90d = int(recent_avg * (1 + monthly_growth_rate * 3))
            weeks_to_capacity: int | None = None
            if weekly_growth_rate > 0 and total_seats > 0 and recent_avg < total_seats:
                remaining = total_seats - recent_avg
                weeks_to_capacity = max(1, int(remaining / (recent_avg * weekly_growth_rate)))
            growth_forecast = {
                "current_active": int(recent_avg),
                "projected_30d": projected_users_30d,
                "projected_90d": projected_users_90d,
                "monthly_growth_pct": round(monthly_growth_rate * 100, 1),
                "weeks_to_capacity": weeks_to_capacity,
            }

    inactive_savings_monthly = round(
        len(ghost_members) * _cost_for_plan("business", cost_override), 2
    )
    inactive_savings_annual = round(inactive_savings_monthly * 12, 2)

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
        "value_streams": {
            "completion_value": completion_value,
            "chat_savings": chat_savings,
            "pr_summary_savings": pr_summary_savings,
            "total_value": total_value,
        },
        "roi": {
            "total_roi": total_roi,
            "roi_ratio": roi_ratio,
            "breakeven_additional_users": breakeven_additional_users,
        },
        "ghost_members": ghost_members,
        "license_optimization": {
            "inactive_savings_monthly": inactive_savings_monthly,
            "inactive_savings_annual": inactive_savings_annual,
            "ghost_member_count": len(ghost_members),
        },
        "growth_forecast": growth_forecast,
        "tier_breakdown": tier_counts,
        "plan_breakdown": plan_counts,
        "cost_trend": cost_trend,
        "recommendations": recommendations,
    }


# ── Billing / UBB service functions ──────────────────────────────────────────


async def get_copilot_billing_overview(db: AsyncSession) -> dict[str, Any]:
    """Pool overview: total AI credits, consumed this period, forecast, remaining."""
    from sqlalchemy import func

    from app.models.copilot_usage import CopilotUsageReport

    check = await _check_feature_enabled(db)
    if check:
        return check

    now = datetime.now(UTC)
    period_start = now.replace(day=1).date()

    # Aggregate total credits consumed this billing period
    result = await db.execute(
        select(
            func.coalesce(func.sum(CopilotUsageReport.total_credits_consumed), 0),
            func.coalesce(func.sum(CopilotUsageReport.budget_amount), 0),
            func.count(func.distinct(CopilotUsageReport.github_login)),
            func.count(func.distinct(CopilotUsageReport.report_date)),
        ).where(CopilotUsageReport.report_date >= period_start)
    )
    row = result.one()
    total_consumed = float(row[0])
    total_budgets = float(row[1])
    unique_users = int(row[2])
    days_reported = int(row[3])

    # Calculate projection
    days_in_month = 30
    if days_reported > 0:
        daily_rate = total_consumed / days_reported
        projected_eom = daily_rate * days_in_month
    else:
        daily_rate = 0.0
        projected_eom = 0.0

    # Pool total (default to sum of user budgets or enterprise setting)
    from app.services.settings_service import get_setting

    pool_total_str = await get_setting(db, "copilot_credit_pool_total")
    pool_total = float(pool_total_str) if pool_total_str else max(total_budgets, 10000.0)

    pool_remaining = max(0.0, pool_total - total_consumed)
    utilization_pct = round(total_consumed / pool_total * 100, 1) if pool_total > 0 else 0.0

    return {
        "pool_total": pool_total,
        "total_consumed": round(total_consumed, 2),
        "projected_eom": round(projected_eom, 2),
        "pool_remaining": round(pool_remaining, 2),
        "utilization_pct": utilization_pct,
        "unique_users": unique_users,
        "daily_rate": round(daily_rate, 2),
        "period_start": period_start.isoformat(),
        "days_reported": days_reported,
    }


async def get_copilot_user_budgets(db: AsyncSession) -> dict[str, Any]:
    """Per-user budget list with consumed/budget/status/utilization %."""
    from sqlalchemy import func

    from app.models.copilot_usage import CopilotUsageReport

    check = await _check_feature_enabled(db)
    if check:
        return check

    now = datetime.now(UTC)
    period_start = now.replace(day=1).date()

    # Aggregate per-user for current billing period
    result = await db.execute(
        select(
            CopilotUsageReport.github_login,
            CopilotUsageReport.org_slug,
            func.sum(CopilotUsageReport.total_credits_consumed).label("consumed"),
            func.max(CopilotUsageReport.budget_amount).label("budget"),
            func.max(CopilotUsageReport.budget_consumed).label("budget_consumed"),
            func.bool_or(CopilotUsageReport.is_blocked).label("is_blocked"),
        )
        .where(CopilotUsageReport.report_date >= period_start)
        .group_by(CopilotUsageReport.github_login, CopilotUsageReport.org_slug)
        .order_by(func.sum(CopilotUsageReport.total_credits_consumed).desc())
    )
    rows = result.fetchall()

    users: list[dict[str, Any]] = []
    buckets = {"0-50": 0, "50-80": 0, "80-90": 0, "90-100": 0, "100+": 0}

    for row in rows:
        login = row[0]
        org = row[1]
        consumed = float(row[2] or 0)
        budget = float(row[3]) if row[3] is not None else None
        is_blocked = bool(row[5])

        if budget and budget > 0:
            utilization = round(consumed / budget * 100, 1)
        else:
            utilization = 0.0

        # Determine status
        if is_blocked:
            status = "blocked"
        elif budget is not None and consumed >= budget:
            status = "over"
        elif budget is not None and utilization >= 90:
            status = "near"
        elif budget is not None and utilization >= 80:
            status = "warning"
        else:
            status = "ok"

        # Bucket classification
        if utilization > 100:
            buckets["100+"] += 1
        elif utilization >= 90:
            buckets["90-100"] += 1
        elif utilization >= 80:
            buckets["80-90"] += 1
        elif utilization >= 50:
            buckets["50-80"] += 1
        else:
            buckets["0-50"] += 1

        users.append(
            {
                "login": login,
                "org_slug": org,
                "consumed": round(consumed, 2),
                "budget": round(budget, 2) if budget is not None else None,
                "utilization_pct": utilization,
                "status": status,
                "is_blocked": is_blocked,
            }
        )

    return {
        "users": users,
        "total_users": len(users),
        "buckets": buckets,
    }


async def get_copilot_billing_trends(db: AsyncSession) -> dict[str, Any]:
    """Daily credit consumption trends over last 30 days."""
    from sqlalchemy import func

    from app.models.copilot_usage import CopilotUsageReport

    check = await _check_feature_enabled(db)
    if check:
        return check

    now = datetime.now(UTC)
    thirty_days_ago = (now - __import__("datetime").timedelta(days=30)).date()

    result = await db.execute(
        select(
            CopilotUsageReport.report_date,
            func.sum(CopilotUsageReport.total_credits_consumed).label("total"),
            func.sum(CopilotUsageReport.completions_credits).label("completions"),
            func.sum(CopilotUsageReport.chat_credits).label("chat"),
            func.sum(CopilotUsageReport.pr_credits).label("pr"),
            func.sum(CopilotUsageReport.other_credits).label("other"),
            func.count(func.distinct(CopilotUsageReport.github_login)).label("users"),
        )
        .where(CopilotUsageReport.report_date >= thirty_days_ago)
        .group_by(CopilotUsageReport.report_date)
        .order_by(CopilotUsageReport.report_date)
    )
    rows = result.fetchall()

    trends: list[dict[str, Any]] = []
    for row in rows:
        trends.append(
            {
                "date": row[0].isoformat(),
                "total": round(float(row[1] or 0), 2),
                "completions": round(float(row[2] or 0), 2),
                "chat": round(float(row[3] or 0), 2),
                "pr": round(float(row[4] or 0), 2),
                "other": round(float(row[5] or 0), 2),
                "active_users": int(row[6] or 0),
            }
        )

    return {
        "trends": trends,
        "period_days": 30,
    }
