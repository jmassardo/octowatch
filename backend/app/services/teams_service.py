"""Microsoft Teams integration service for admin configuration and webhook delivery."""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.settings_service import get_setting, set_setting

logger = structlog.get_logger(__name__)

_TEAMS_CONFIG_KEY = "teams_channel_webhooks"
_TEAMS_SOURCE_MAPPING_KEY = "teams_source_mappings"
_TEAMS_NOTIFICATION_SETTINGS_KEY = "teams_notification_settings"
_TEAMS_SOURCES = ("detections", "sync_errors", "system_health", "threat_intel")
_TEAMS_CHANNELS = ("default", "detections", "sync_errors", "system_health", "threat_intel")
_DEFAULT_SOURCE_MAPPINGS: dict[str, str] = {
    "detections": "detections",
    "sync_errors": "sync_errors",
    "system_health": "system_health",
    "threat_intel": "threat_intel",
}
_DEFAULT_NOTIFICATION_SETTINGS: dict[str, bool] = {
    "detections": True,
    "sync_errors": True,
    "system_health": True,
    "threat_intel": False,
}


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:8]}{'*' * max(len(value) - 16, 4)}{value[-8:]}"


async def _get_json_setting(db: AsyncSession, key: str) -> dict[str, Any]:
    raw = await get_setting(db, key)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("teams.settings_invalid_json", key=key)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_channel_webhooks(value: dict[str, Any] | None) -> dict[str, str]:
    channel_webhooks = dict.fromkeys(_TEAMS_CHANNELS, "")
    if value:
        for channel in _TEAMS_CHANNELS:
            raw = value.get(channel, "")
            channel_webhooks[channel] = str(raw).strip() if raw is not None else ""
    return channel_webhooks


def _normalize_source_mappings(value: dict[str, Any] | None) -> dict[str, str]:
    mappings = dict(_DEFAULT_SOURCE_MAPPINGS)
    if value:
        for source in _TEAMS_SOURCES:
            raw = str(value.get(source, mappings[source])).strip()
            mappings[source] = raw if raw in _TEAMS_CHANNELS else _DEFAULT_SOURCE_MAPPINGS[source]
    return mappings


def _normalize_notification_settings(value: dict[str, Any] | None) -> dict[str, bool]:
    normalized = dict(_DEFAULT_NOTIFICATION_SETTINGS)
    if value:
        for source in _TEAMS_SOURCES:
            if source in value:
                normalized[source] = bool(value[source])
    return normalized


async def get_teams_config(db: AsyncSession) -> dict[str, Any]:
    channel_webhooks = _normalize_channel_webhooks(await _get_json_setting(db, _TEAMS_CONFIG_KEY))
    source_mappings = _normalize_source_mappings(
        await _get_json_setting(db, _TEAMS_SOURCE_MAPPING_KEY)
    )
    notification_settings = _normalize_notification_settings(
        await _get_json_setting(db, _TEAMS_NOTIFICATION_SETTINGS_KEY)
    )
    return {
        "channel_webhook_configured": {
            channel: bool(url) for channel, url in channel_webhooks.items()
        },
        "channel_webhooks_masked": {
            channel: _mask_secret(url) for channel, url in channel_webhooks.items()
        },
        "source_mappings": source_mappings,
        "notification_settings": notification_settings,
    }


async def update_teams_config(
    db: AsyncSession,
    *,
    channel_webhooks: dict[str, Any],
    source_mappings: dict[str, Any],
    notification_settings: dict[str, Any],
    clear_channels: list[str],
    changed_by: str,
) -> dict[str, Any]:
    existing_webhooks = _normalize_channel_webhooks(await _get_json_setting(db, _TEAMS_CONFIG_KEY))
    updated_webhooks = dict(existing_webhooks)
    for channel in clear_channels:
        if channel in updated_webhooks:
            updated_webhooks[channel] = ""
    for channel, value in _normalize_channel_webhooks(channel_webhooks).items():
        if value:
            updated_webhooks[channel] = value

    await set_setting(
        db,
        _TEAMS_CONFIG_KEY,
        json.dumps(updated_webhooks),
        category="integrations",
        sensitivity="critical",
        description="Microsoft Teams incoming webhook URLs by channel",
        changed_by=changed_by,
    )
    await set_setting(
        db,
        _TEAMS_SOURCE_MAPPING_KEY,
        json.dumps(_normalize_source_mappings(source_mappings)),
        category="integrations",
        sensitivity="config",
        description="Microsoft Teams channel mapping by OctoWatch source",
        changed_by=changed_by,
    )
    await set_setting(
        db,
        _TEAMS_NOTIFICATION_SETTINGS_KEY,
        json.dumps(_normalize_notification_settings(notification_settings)),
        category="integrations",
        sensitivity="config",
        description="Microsoft Teams notification enablement by OctoWatch source",
        changed_by=changed_by,
    )
    await db.flush()
    return await get_teams_config(db)


async def get_runtime_notification_config(db: AsyncSession, source: str) -> dict[str, Any]:
    channel_webhooks = _normalize_channel_webhooks(await _get_json_setting(db, _TEAMS_CONFIG_KEY))
    source_mappings = _normalize_source_mappings(
        await _get_json_setting(db, _TEAMS_SOURCE_MAPPING_KEY)
    )
    notification_settings = _normalize_notification_settings(
        await _get_json_setting(db, _TEAMS_NOTIFICATION_SETTINGS_KEY)
    )
    return {
        "enabled": bool(notification_settings.get(source, False)),
        "channel_key": source_mappings.get(source, "default"),
        "channel_webhooks": channel_webhooks,
        "source_mappings": source_mappings,
        "base_url": settings.AUTH.APP_BASE_URL,
    }


async def send_adaptive_card(webhook_url: str, card: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(webhook_url, json=card)
        response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {"ok": True, "response": response.text or "ok"}


def format_notification_card(notification: Any, base_url: str | None = None) -> dict[str, Any]:
    severity = str(getattr(notification, "severity", "info")).lower()
    accent = {
        "critical": "attention",
        "high": "attention",
        "medium": "warning",
        "low": "accent",
        "info": "default",
    }.get(severity, "default")
    title = str(getattr(notification, "title", "OctoWatch notification"))
    description = str(getattr(notification, "description", "No description provided."))
    detection_id = getattr(notification, "id", None)
    action_url = f"{str(base_url).rstrip('/')}/threats" if base_url else None

    actions: list[dict[str, Any]] = []
    if action_url:
        actions.append(
            {
                "type": "Action.OpenUrl",
                "title": "Open in OctoWatch",
                "url": action_url,
            }
        )

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Large",
                            "weight": "Bolder",
                            "color": accent,
                            "text": title,
                            "wrap": True,
                        },
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "width": "stretch",
                                    "items": [
                                        {"type": "TextBlock", "text": "Severity", "isSubtle": True},
                                        {
                                            "type": "TextBlock",
                                            "text": severity.upper(),
                                            "weight": "Bolder",
                                            "color": accent,
                                        },
                                    ],
                                },
                                {
                                    "type": "Column",
                                    "width": "stretch",
                                    "items": [
                                        {"type": "TextBlock", "text": "Actor", "isSubtle": True},
                                        {
                                            "type": "TextBlock",
                                            "text": str(
                                                getattr(notification, "actor", None) or "N/A"
                                            ),
                                        },
                                    ],
                                },
                                {
                                    "type": "Column",
                                    "width": "stretch",
                                    "items": [
                                        {"type": "TextBlock", "text": "Org", "isSubtle": True},
                                        {
                                            "type": "TextBlock",
                                            "text": str(
                                                getattr(notification, "org", None) or "N/A"
                                            ),
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": description,
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Detection ID", "value": str(detection_id or "N/A")},
                                {
                                    "title": "Triggered",
                                    "value": str(
                                        getattr(notification, "triggered_at", None) or "N/A"
                                    ),
                                },
                            ],
                        },
                    ],
                    "actions": actions,
                },
            }
        ],
    }


async def send_teams_notification(
    notification: Any, config: dict[str, Any]
) -> dict[str, Any] | None:
    if not config.get("enabled", True):
        return None

    channel_key = str(config.get("channel_key") or "default")
    channel_webhooks = _normalize_channel_webhooks(config.get("channel_webhooks"))
    webhook_url = channel_webhooks.get(channel_key) or channel_webhooks.get("default", "")
    if not webhook_url:
        logger.debug(
            "teams.notification_skipped", reason="missing_webhook", channel_key=channel_key
        )
        return None

    card = format_notification_card(notification, base_url=config.get("base_url"))
    response = await send_adaptive_card(webhook_url, card)
    logger.info(
        "teams.notification_sent",
        detection_id=getattr(notification, "id", None),
        channel_key=channel_key,
    )
    return response
