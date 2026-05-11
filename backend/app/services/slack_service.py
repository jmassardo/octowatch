"""Slack integration service for notifications and bot commands."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.audit_event import AuditEvent
from app.models.detection import Detection
from app.models.system_health import SystemHealthEvent
from app.services.settings_service import get_setting, set_setting

logger = structlog.get_logger(__name__)

_SLACK_API_URL = "https://slack.com/api/chat.postMessage"
_SLACK_BOT_TOKEN_KEY = "slack_bot_token"  # noqa: S105
_SLACK_SIGNING_SECRET_KEY = "slack_signing_secret"  # noqa: S105
_SLACK_DEFAULT_CHANNEL_KEY = "slack_default_channel"
_SLACK_CHANNEL_MAPPINGS_KEY = "slack_channel_mappings"
_SLACK_NOTIFICATION_SETTINGS_KEY = "slack_notification_settings"
_SLACK_SOURCES = ("detections", "sync_errors", "system_health", "threat_intel")
_DEFAULT_NOTIFICATION_SETTINGS: dict[str, bool] = {
    "detections": True,
    "sync_errors": True,
    "system_health": True,
    "threat_intel": False,
}


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(len(value) - 8, 4)}{value[-4:]}"


def _normalize_channel_mappings(value: dict[str, Any] | None) -> dict[str, str]:
    mappings = dict.fromkeys(_SLACK_SOURCES, "")
    if value:
        for source in _SLACK_SOURCES:
            raw = value.get(source, "")
            mappings[source] = str(raw).strip() if raw is not None else ""
    return mappings


def _normalize_notification_settings(value: dict[str, Any] | None) -> dict[str, bool]:
    normalized = dict(_DEFAULT_NOTIFICATION_SETTINGS)
    if value:
        for source in _SLACK_SOURCES:
            if source in value:
                normalized[source] = bool(value[source])
    return normalized


async def _get_json_setting(db: AsyncSession, key: str) -> dict[str, Any]:
    raw = await get_setting(db, key)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("slack.settings_invalid_json", key=key)
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def get_slack_config(db: AsyncSession) -> dict[str, Any]:
    bot_token = await get_setting(db, _SLACK_BOT_TOKEN_KEY)
    signing_secret = await get_setting(db, _SLACK_SIGNING_SECRET_KEY)
    default_channel = await get_setting(db, _SLACK_DEFAULT_CHANNEL_KEY)
    channel_mappings = _normalize_channel_mappings(
        await _get_json_setting(db, _SLACK_CHANNEL_MAPPINGS_KEY)
    )
    notification_settings = _normalize_notification_settings(
        await _get_json_setting(db, _SLACK_NOTIFICATION_SETTINGS_KEY)
    )

    return {
        "bot_token_configured": bool(bot_token),
        "signing_secret_configured": bool(signing_secret),
        "bot_token_masked": _mask_secret(bot_token),
        "signing_secret_masked": _mask_secret(signing_secret),
        "default_channel": default_channel or "",
        "channel_mappings": channel_mappings,
        "notification_settings": notification_settings,
        "installation_url": "https://api.slack.com/apps",
        "installation_instructions": [
            "Create or update your Slack app with chat:write, "
            "commands, and incoming webhook scopes.",
            "Set the slash command request URL to /api/v1/integrations/slack/commands.",
            "Set the interactive components and event request URL to "
            "/api/v1/integrations/slack/events and /interactions.",
        ],
        "commands": ["/octowatch status", "/octowatch threats", "/octowatch search <query>"],
    }


async def update_slack_config(
    db: AsyncSession,
    *,
    bot_token: str | None,
    signing_secret: str | None,
    default_channel: str,
    channel_mappings: dict[str, Any],
    notification_settings: dict[str, Any],
    changed_by: str,
) -> dict[str, Any]:
    if bot_token:
        await set_setting(
            db,
            _SLACK_BOT_TOKEN_KEY,
            bot_token,
            category="integrations",
            sensitivity="critical",
            description="Slack bot token for Web API calls",
            changed_by=changed_by,
        )
        object.__setattr__(settings.INTEGRATIONS, "SLACK_BOT_TOKEN", bot_token)

    if signing_secret:
        await set_setting(
            db,
            _SLACK_SIGNING_SECRET_KEY,
            signing_secret,
            category="integrations",
            sensitivity="critical",
            description="Slack signing secret for webhook verification",
            changed_by=changed_by,
        )

    await set_setting(
        db,
        _SLACK_DEFAULT_CHANNEL_KEY,
        default_channel.strip(),
        category="integrations",
        sensitivity="config",
        description="Default Slack channel for OctoWatch notifications",
        changed_by=changed_by,
    )
    await set_setting(
        db,
        _SLACK_CHANNEL_MAPPINGS_KEY,
        json.dumps(_normalize_channel_mappings(channel_mappings)),
        category="integrations",
        sensitivity="config",
        description="Slack channel mapping by OctoWatch notification source",
        changed_by=changed_by,
    )
    await set_setting(
        db,
        _SLACK_NOTIFICATION_SETTINGS_KEY,
        json.dumps(_normalize_notification_settings(notification_settings)),
        category="integrations",
        sensitivity="config",
        description="Slack notification enablement by OctoWatch source",
        changed_by=changed_by,
    )

    await db.flush()
    return await get_slack_config(db)


async def get_runtime_notification_config(db: AsyncSession, source: str) -> dict[str, Any]:
    config = await get_slack_config(db)
    channel_mappings = config["channel_mappings"]
    notification_settings = config["notification_settings"]
    return {
        "enabled": bool(notification_settings.get(source, False)),
        "channel": channel_mappings.get(source) or config["default_channel"],
        "bot_token": await get_setting(db, _SLACK_BOT_TOKEN_KEY)
        or settings.INTEGRATIONS.SLACK_BOT_TOKEN,
        "base_url": settings.AUTH.APP_BASE_URL,
    }


async def send_slack_message(
    channel: str,
    text: str,
    blocks: list[dict[str, Any]] | None = None,
    *,
    bot_token: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    token = bot_token or settings.INTEGRATIONS.SLACK_BOT_TOKEN
    if not token:
        raise ValueError("Slack bot token is not configured")

    payload: dict[str, Any] = {
        "channel": channel,
        "text": text,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if blocks:
        payload["blocks"] = blocks
    if attachments:
        payload["attachments"] = attachments

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            _SLACK_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        response.raise_for_status()

    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "slack_api_error"))

    logger.info("slack.message_sent", channel=channel)
    return data


async def send_slack_notification(
    notification: Any, config: dict[str, Any]
) -> dict[str, Any] | None:
    if not config.get("enabled", True):
        return None

    channel = str(config.get("channel") or "").strip()
    if not channel:
        logger.debug("slack.notification_skipped", reason="missing_channel")
        return None

    severity = str(getattr(notification, "severity", "info")).lower()
    color = {
        "critical": "#d92d20",
        "high": "#f04438",
        "medium": "#f79009",
        "low": "#1570ef",
        "info": "#667085",
    }.get(severity, "#667085")
    emoji = {
        "critical": ":rotating_light:",
        "high": ":red_circle:",
        "medium": ":large_yellow_circle:",
        "low": ":large_blue_circle:",
        "info": ":information_source:",
    }.get(severity, ":warning:")

    title = str(getattr(notification, "title", "OctoWatch notification"))
    description = str(getattr(notification, "description", "No description provided."))
    detection_id = getattr(notification, "id", None)
    base_url = str(config.get("base_url") or settings.AUTH.APP_BASE_URL or "").rstrip("/")
    action_url = f"{base_url}/threats" if base_url else None

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Severity*\n{severity.upper()}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Confidence*\n{getattr(notification, 'confidence', 'n/a')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Actor*\n{getattr(notification, 'actor', None) or 'N/A'}",
                },
                {"type": "mrkdwn", "text": f"*Org*\n{getattr(notification, 'org', None) or 'N/A'}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": description},
        },
    ]

    if action_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open in OctoWatch"},
                        "url": action_url,
                    }
                ],
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Detection ID: {detection_id or 'N/A'} • "
                        f"Triggered: {getattr(notification, 'triggered_at', None) or 'N/A'}"
                    ),
                }
            ],
        }
    )

    return await send_slack_message(
        channel,
        f"[{severity.upper()}] {title}",
        blocks=None,
        bot_token=config.get("bot_token"),
        attachments=[{"color": color, "blocks": blocks}],
    )


def verify_slack_signature(
    *,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    signing_secret: str | None,
) -> bool:
    if not signing_secret or not timestamp or not signature:
        return False

    try:
        request_ts = int(timestamp)
    except (TypeError, ValueError):
        return False

    if abs(int(time.time()) - request_ts) > 60 * 5:
        return False

    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = (
        "v0="
        + hmac.new(
            signing_secret.encode("utf-8"),
            basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def _command_action(label: str, command_text: str) -> dict[str, Any]:
    return {
        "type": "button",
        "action_id": "octowatch_command",
        "text": {"type": "plain_text", "text": label},
        "value": json.dumps({"text": command_text}),
    }


async def _status_blocks(user_id: str) -> tuple[str, list[dict[str, Any]]]:
    async with AsyncSessionLocal() as db:
        now = datetime.now(UTC)
        since = now - timedelta(hours=24)
        events_24h = await db.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.created_at >= since)
        )
        detections_24h = await db.scalar(
            select(func.count()).select_from(Detection).where(Detection.triggered_at >= since)
        )
        unresolved_health = await db.scalar(
            select(func.count())
            .select_from(SystemHealthEvent)
            .where(SystemHealthEvent.resolved_at.is_(None))
        )

    summary = "healthy" if not unresolved_health else "attention needed"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "OctoWatch status"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Platform*\n{summary}"},
                {"type": "mrkdwn", "text": f"*Events (24h)*\n{int(events_24h or 0):,}"},
                {"type": "mrkdwn", "text": f"*Detections (24h)*\n{int(detections_24h or 0):,}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Open health events*\n{int(unresolved_health or 0):,}",
                },
            ],
        },
        {
            "type": "actions",
            "elements": [
                _command_action("Refresh", "status"),
                _command_action("View threats", "threats"),
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Requested by <@{user_id}>"}],
        },
    ]
    return "OctoWatch status summary", blocks


async def _threat_blocks(user_id: str) -> tuple[str, list[dict[str, Any]]]:
    async with AsyncSessionLocal() as db:
        since = datetime.now(UTC) - timedelta(hours=24)
        critical_count = await db.scalar(
            select(func.count())
            .select_from(Detection)
            .where(Detection.triggered_at >= since, Detection.severity == "critical")
        )
        high_count = await db.scalar(
            select(func.count())
            .select_from(Detection)
            .where(Detection.triggered_at >= since, Detection.severity == "high")
        )
        recent = (
            (
                await db.execute(
                    select(Detection)
                    .where(Detection.severity.in_(["critical", "high"]))
                    .order_by(desc(Detection.triggered_at))
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "Recent threats"}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Critical (24h)*\n{int(critical_count or 0):,}"},
                {"type": "mrkdwn", "text": f"*High (24h)*\n{int(high_count or 0):,}"},
            ],
        },
    ]

    if recent:
        lines = [
            f"• *{row.severity.upper()}* — {row.title} "
            f"({row.org or 'global'} / {row.actor or 'unknown'})"
            for row in recent
        ]
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Latest detections*\n" + "\n".join(lines)},
            }
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "No critical or high detections found."},
            }
        )

    blocks.extend(
        [
            {
                "type": "actions",
                "elements": [
                    _command_action("Refresh", "threats"),
                    _command_action("Status", "status"),
                ],
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"Requested by <@{user_id}>"}],
            },
        ]
    )
    return "Recent OctoWatch threats", blocks


async def _search_blocks(query: str, user_id: str) -> tuple[str, list[dict[str, Any]]]:
    pattern = f"%{query}%"
    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(AuditEvent)
                    .where(
                        or_(
                            AuditEvent.action.ilike(pattern),
                            AuditEvent.actor.ilike(pattern),
                            AuditEvent.org.ilike(pattern),
                            AuditEvent.repo.ilike(pattern),
                        )
                    )
                    .order_by(desc(AuditEvent.created_at))
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

    if rows:
        results = [
            f"• `{row.created_at.strftime('%Y-%m-%d %H:%M')}` "
            f"— *{row.action}* · {row.actor or 'unknown'} "
            f"· {row.org or 'global'}"
            f"{f'/{row.repo}' if row.repo else ''}"
            for row in rows
        ]
        text = "\n".join(results)
    else:
        text = "No recent events matched your search."

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Search: {query}"}},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        },
        {
            "type": "actions",
            "elements": [
                _command_action("Run again", f"search {query}"),
                _command_action("Status", "status"),
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Requested by <@{user_id}>"}],
        },
    ]
    return f"Search results for {query}", blocks


def _help_response() -> dict[str, Any]:
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "OctoWatch Slack commands"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "• `/octowatch status` — system health summary\n"
                    "• `/octowatch threats` — recent critical/high detections\n"
                    "• `/octowatch search <query>` — quick event lookup"
                ),
            },
        },
    ]
    return {"response_type": "ephemeral", "text": "OctoWatch Slack commands", "blocks": blocks}


async def handle_slack_command(command: str, text: str, user_id: str) -> dict[str, Any]:
    if command != "/octowatch":
        return _help_response()

    normalized = (text or "").strip()
    if not normalized:
        return _help_response()

    head, _, tail = normalized.partition(" ")
    subcommand = head.lower()

    if subcommand == "status":
        response_text, blocks = await _status_blocks(user_id)
    elif subcommand == "threats":
        response_text, blocks = await _threat_blocks(user_id)
    elif subcommand == "search" and tail.strip():
        response_text, blocks = await _search_blocks(tail.strip(), user_id)
    else:
        return _help_response()

    return {"response_type": "ephemeral", "text": response_text, "blocks": blocks}


async def handle_slack_interaction(payload: dict[str, Any]) -> dict[str, Any]:
    payload_type = payload.get("type")
    if payload_type == "view_submission":
        return {"response_action": "clear"}

    if payload_type == "block_actions":
        actions = payload.get("actions") or []
        action = actions[0] if actions else {}
        value = action.get("value")
        try:
            parsed_value = json.loads(value) if value else {}
        except json.JSONDecodeError:
            parsed_value = {}
        user_id = payload.get("user", {}).get("id", "unknown")
        return await handle_slack_command("/octowatch", parsed_value.get("text", ""), user_id)

    return {"text": "Slack interaction received."}
