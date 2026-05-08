"""PagerDuty integration service for admin configuration and incident delivery."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.settings_service import get_setting, set_setting

logger = structlog.get_logger(__name__)

_PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"
_PAGERDUTY_ROUTING_KEY_KEY = "pagerduty_routing_key"
_PAGERDUTY_SEVERITY_MAPPING_KEY = "pagerduty_severity_mapping"
_PAGERDUTY_NOTIFICATION_SETTINGS_KEY = "pagerduty_notification_settings"
_PAGERDUTY_AUTO_RESOLVE_KEY = "pagerduty_auto_resolve"
_PAGERDUTY_SOURCES = ("detections", "sync_errors", "system_health", "threat_intel")
_DEFAULT_NOTIFICATION_SETTINGS: dict[str, bool] = {
    "detections": True,
    "sync_errors": True,
    "system_health": True,
    "threat_intel": False,
}
_DEFAULT_SEVERITY_MAPPING: dict[str, str] = {
    "critical": "critical",
    "high": "error",
    "medium": "warning",
    "low": "info",
    "info": "info",
}
_VALID_PAGERDUTY_SEVERITIES = {"critical", "error", "warning", "info"}


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(len(value) - 8, 4)}{value[-4:]}"


def _normalize_notification_settings(value: dict[str, Any] | None) -> dict[str, bool]:
    normalized = dict(_DEFAULT_NOTIFICATION_SETTINGS)
    if value:
        for source in _PAGERDUTY_SOURCES:
            if source in value:
                normalized[source] = bool(value[source])
    return normalized


def _normalize_severity_mapping(value: dict[str, Any] | None) -> dict[str, str]:
    normalized = dict(_DEFAULT_SEVERITY_MAPPING)
    if value:
        for severity in _DEFAULT_SEVERITY_MAPPING:
            raw = str(value.get(severity, normalized[severity])).strip().lower()
            normalized[severity] = (
                raw if raw in _VALID_PAGERDUTY_SEVERITIES else _DEFAULT_SEVERITY_MAPPING[severity]
            )
    return normalized


async def _get_json_setting(db: AsyncSession, key: str) -> dict[str, Any]:
    raw = await get_setting(db, key)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("pagerduty.settings_invalid_json", key=key)
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def get_pagerduty_config(db: AsyncSession) -> dict[str, Any]:
    routing_key = await get_setting(db, _PAGERDUTY_ROUTING_KEY_KEY)
    severity_mapping = _normalize_severity_mapping(
        await _get_json_setting(db, _PAGERDUTY_SEVERITY_MAPPING_KEY)
    )
    notification_settings = _normalize_notification_settings(
        await _get_json_setting(db, _PAGERDUTY_NOTIFICATION_SETTINGS_KEY)
    )
    auto_resolve = (await get_setting(db, _PAGERDUTY_AUTO_RESOLVE_KEY) or "false").lower() == "true"
    return {
        "routing_key_configured": bool(routing_key),
        "routing_key_masked": _mask_secret(routing_key),
        "severity_mapping": severity_mapping,
        "notification_settings": notification_settings,
        "auto_resolve": auto_resolve,
    }


async def update_pagerduty_config(
    db: AsyncSession,
    *,
    routing_key: str | None,
    severity_mapping: dict[str, Any],
    notification_settings: dict[str, Any],
    auto_resolve: bool,
    changed_by: str,
) -> dict[str, Any]:
    if routing_key:
        await set_setting(
            db,
            _PAGERDUTY_ROUTING_KEY_KEY,
            routing_key,
            category="integrations",
            sensitivity="critical",
            description="PagerDuty Events API routing key",
            changed_by=changed_by,
        )

    await set_setting(
        db,
        _PAGERDUTY_SEVERITY_MAPPING_KEY,
        json.dumps(_normalize_severity_mapping(severity_mapping)),
        category="integrations",
        sensitivity="config",
        description="PagerDuty severity mapping by OctoWatch severity",
        changed_by=changed_by,
    )
    await set_setting(
        db,
        _PAGERDUTY_NOTIFICATION_SETTINGS_KEY,
        json.dumps(_normalize_notification_settings(notification_settings)),
        category="integrations",
        sensitivity="config",
        description="PagerDuty notification enablement by OctoWatch source",
        changed_by=changed_by,
    )
    await set_setting(
        db,
        _PAGERDUTY_AUTO_RESOLVE_KEY,
        "true" if auto_resolve else "false",
        category="integrations",
        sensitivity="config",
        description="Automatically resolve PagerDuty incidents when detections are resolved",
        changed_by=changed_by,
    )
    await db.flush()
    return await get_pagerduty_config(db)


async def get_runtime_notification_config(db: AsyncSession, source: str) -> dict[str, Any]:
    config = await get_pagerduty_config(db)
    return {
        "enabled": bool(config["notification_settings"].get(source, False)),
        "routing_key": await get_setting(db, _PAGERDUTY_ROUTING_KEY_KEY),
        "severity_mapping": config["severity_mapping"],
        "auto_resolve": config["auto_resolve"],
        "source": source,
    }


async def _post_event(payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(_PAGERDUTY_EVENTS_URL, json=payload)
        response.raise_for_status()
    data = response.json()
    if data.get("status") != "success":
        raise RuntimeError(data.get("message", "pagerduty_api_error"))
    return data


async def create_incident(
    title: str,
    description: str,
    severity: str,
    source: str,
    *,
    routing_key: str | None = None,
    dedup_key: str | None = None,
    custom_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = routing_key or getattr(settings.INTEGRATIONS, "PAGERDUTY_ROUTING_KEY", None)
    if not key:
        raise ValueError("PagerDuty routing key is not configured")

    payload: dict[str, Any] = {
        "routing_key": key,
        "event_action": "trigger",
        "payload": {
            "summary": title,
            "source": source,
            "severity": severity,
            "timestamp": datetime.now(UTC).isoformat(),
            "custom_details": {
                "description": description,
                **(custom_details or {}),
            },
        },
    }
    if dedup_key:
        payload["dedup_key"] = dedup_key
    return await _post_event(payload)


async def resolve_incident(
    dedup_key: str,
    *,
    routing_key: str | None = None,
    source: str = "octowatch",
) -> dict[str, Any]:
    key = routing_key or getattr(settings.INTEGRATIONS, "PAGERDUTY_ROUTING_KEY", None)
    if not key:
        raise ValueError("PagerDuty routing key is not configured")

    return await _post_event(
        {
            "routing_key": key,
            "event_action": "resolve",
            "dedup_key": dedup_key,
            "payload": {
                "summary": f"Resolved: {dedup_key}",
                "source": source,
                "severity": "info",
            },
        }
    )


async def send_change_event(
    summary: str,
    source: str,
    *,
    routing_key: str | None = None,
    custom_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = routing_key or getattr(settings.INTEGRATIONS, "PAGERDUTY_ROUTING_KEY", None)
    if not key:
        raise ValueError("PagerDuty routing key is not configured")

    return await _post_event(
        {
            "routing_key": key,
            "event_action": "change",
            "payload": {
                "summary": summary,
                "source": source,
                "timestamp": datetime.now(UTC).isoformat(),
                "custom_details": custom_details or {},
            },
        }
    )


async def send_pagerduty_notification(
    notification: Any,
    config: dict[str, Any],
    valkey: Any | None = None,
) -> dict[str, Any] | None:
    if not config.get("enabled", True):
        return None

    routing_key = str(config.get("routing_key") or "").strip()
    if not routing_key:
        logger.debug("pagerduty.notification_skipped", reason="missing_routing_key")
        return None

    severity_mapping = _normalize_severity_mapping(config.get("severity_mapping"))
    notification_severity = str(getattr(notification, "severity", "info")).lower()
    pagerduty_severity = severity_mapping.get(notification_severity, "info")
    dedup_key = f"octowatch-detection-{getattr(notification, 'id', 'notification')}"
    custom_details = {
        "detection_id": getattr(notification, "id", None),
        "confidence": getattr(notification, "confidence", None),
        "actor": getattr(notification, "actor", None),
        "org": getattr(notification, "org", None),
        "repo": getattr(notification, "repo", None),
    }
    response = await create_incident(
        title=(
            f"[{notification_severity.upper()}] "
            f"{getattr(notification, 'title', 'OctoWatch notification')}"
        ),
        description=str(getattr(notification, "description", "No description provided.")),
        severity=pagerduty_severity,
        source="octowatch",
        routing_key=routing_key,
        dedup_key=dedup_key,
        custom_details=custom_details,
    )
    if valkey is not None and getattr(notification, "id", None) is not None:
        await valkey.set(f"pagerduty:dedup:{notification.id}", dedup_key, ex=86400 * 30)
    logger.info(
        "pagerduty.notification_sent",
        dedup_key=dedup_key,
        detection_id=getattr(notification, "id", None),
    )
    return response


async def resolve_detection_incident(db: AsyncSession, valkey: Any, detection_id: int) -> bool:
    config = await get_runtime_notification_config(db, "detections")
    if not config.get("enabled") or not config.get("auto_resolve"):
        return False

    routing_key = str(config.get("routing_key") or "").strip()
    if not routing_key:
        return False

    dedup_key = await valkey.get(f"pagerduty:dedup:{detection_id}")
    if not dedup_key:
        return False

    await resolve_incident(str(dedup_key), routing_key=routing_key)
    await valkey.delete(f"pagerduty:dedup:{detection_id}")
    logger.info("pagerduty.incident_resolved", detection_id=detection_id, dedup_key=dedup_key)
    return True
