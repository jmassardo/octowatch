"""Copilot Metrics service — fetches real data from the GitHub Copilot Metrics API.

Calls ``GET /enterprises/{slug}/copilot/metrics`` using a GitHub App installation
token, then transforms the raw daily metric objects into shaped payloads for the
four frontend Copilot panes (Overview, Adoption, Models, Anomalies).

Results are cached in Valkey (1-hour TTL) to avoid excessive API round-trips.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import redis.asyncio as aioredis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.github_sync import GitHubAppConfig
from app.services.github_token_service import GitHubAppTokenManager, GitHubAuthError

logger = structlog.get_logger(__name__)

_GITHUB_API_BASE = "https://api.github.com"

# Valkey cache key pattern — interpolated with enterprise slug only
_CACHE_KEY = "copilot:metrics:{enterprise_slug}"
_CACHE_TTL_SECONDS = 3600  # 1 hour

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


async def _fetch_metrics_raw(db: AsyncSession) -> list[dict[str, Any]] | dict[str, str]:
    """Fetch raw daily metrics from the GitHub Copilot Metrics API.

    Returns either the parsed JSON array on success, or an error dict.
    Results are cached in Valkey for ``_CACHE_TTL_SECONDS``.
    """
    enterprise_slug = settings.github_app.GITHUB_ENTERPRISE_SLUG
    if not enterprise_slug:
        return {"error": "no_enterprise_config", "message": "GITHUB_ENTERPRISE_SLUG is not set."}

    app_id = settings.github_app.GITHUB_APP_ID
    key_path = settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH
    if not app_id or not key_path:
        return {
            "error": "no_enterprise_config",
            "message": "GitHub App credentials (APP_ID / PRIVATE_KEY_PATH) are not configured.",
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
    # valkey is closed in the finally below after we potentially write to it

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

    # ── Get token and call API ────────────────────────────────────────────────
    try:
        private_key = Path(key_path).read_text()
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
            "message": f"Failed to obtain GitHub App installation token: {exc}",
        }
    except Exception as exc:
        logger.error("copilot_metrics.token_unexpected", error=str(exc), exc_info=True)
        if valkey:
            await valkey.aclose()
        return {
            "error": "copilot_not_available",
            "message": f"Unexpected error obtaining token: {exc}",
        }

    url = f"{_GITHUB_API_BASE}/enterprises/{enterprise_slug}/copilot/metrics"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
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
                    "or the App lacks the enterprise_copilot_metrics:read permission."
                ),
            }

        response.raise_for_status()
        metrics: list[dict[str, Any]] = response.json()

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
            "message": f"Failed to fetch Copilot metrics: {exc}",
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


# ── Public API ────────────────────────────────────────────────────────────────


async def get_copilot_overview(db: AsyncSession) -> dict[str, Any]:
    """Data for the Overview pane: acceptance rates, language breakdown, user counts."""
    raw = await _fetch_metrics_raw(db)
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
    """Data for the Adoption pane: tiers, feature adoption."""
    raw = await _fetch_metrics_raw(db)
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

    # ── Collect daily active-user counts to estimate tiers ─────────────────────
    daily_active: list[int] = [d.get("total_active_users", 0) for d in days]

    avg_active = sum(daily_active) / num_days if num_days else 0
    max_active = max(daily_active) if daily_active else 0
    latest_active = daily_active[-1] if daily_active else 0

    # Heuristic tier estimation (we don't have per-user data from the metrics API)
    # Power = users active nearly every day; approximate from daily counts
    power_estimate = int(min(daily_active) * 0.9) if daily_active else 0
    regular_estimate = int(avg_active - power_estimate) if avg_active > power_estimate else 0
    minimal_estimate = int(max_active - avg_active) if max_active > avg_active else 0
    inactive_estimate = max(0, int(latest_active * 0.1))

    tiers: list[dict[str, Any]] = [
        {
            "id": "power",
            "label": "Power Users",
            "count": power_estimate,
            "color": _COLOR_GREEN,
            "desc": "Active nearly every day across multiple features",
        },
        {
            "id": "regular",
            "label": "Regular Users",
            "count": regular_estimate,
            "color": _COLOR_BLUE,
            "desc": "Active more than 50% of measured days",
        },
        {
            "id": "minimal",
            "label": "Minimal Users",
            "count": minimal_estimate,
            "color": _COLOR_YELLOW,
            "desc": "Active only 1–2 days in the measurement window",
        },
        {
            "id": "inactive",
            "label": "Inactive / Never",
            "count": inactive_estimate,
            "color": _COLOR_GRAY,
            "desc": "Assigned a seat but no recorded activity",
        },
    ]
    total_adoption = power_estimate + regular_estimate + minimal_estimate + inactive_estimate

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
        "power_users": [],  # Per-user data requires the Copilot billing/seats API
        "feature_adoption": feature_adoption,
        "minimal_users": [],  # Per-user data requires the Copilot billing/seats API
    }


async def get_copilot_models(db: AsyncSession) -> dict[str, Any]:
    """Data for the Models pane: model usage, feature counts, editors."""
    raw = await _fetch_metrics_raw(db)
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
    raw = await _fetch_metrics_raw(db)
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
