"""Notification service: Slack + SMTP with Jinja2 templates and alert dedup."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib
import structlog
from jinja2 import Environment, PackageLoader, select_autoescape
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.detection import Detection
from app.models.integration import NotificationConfig

logger = structlog.get_logger(__name__)

_DEDUP_TTL_DEFAULT = 3600  # 1 hour

# Jinja2 environment for notification templates
_jinja_env = Environment(
    loader=PackageLoader("app", "templates"),
    autoescape=select_autoescape(["html"]),
)


def _alert_dedup_key(
    rule_id: int,
    actor: str | None,
    org: str | None,
    bucket: str,
) -> str:
    """Build deterministic Valkey dedup key (§notification dedup)."""
    parts = f"alert:dedup:{rule_id}:{actor or ''}:{org or ''}:{bucket}"
    return hashlib.sha256(parts.encode()).hexdigest()


async def _is_duplicate(
    valkey: Any,
    rule_id: int,
    detection: Detection,
    ttl: int = _DEDUP_TTL_DEFAULT,
) -> bool:
    """Return True if this alert has already been sent within the TTL window."""
    bucket = datetime.now(UTC).strftime("%Y-%m-%dT%H")
    key = _alert_dedup_key(rule_id, detection.actor, detection.org, bucket)
    existed = await valkey.set(key, "1", ex=ttl, nx=True)
    # nx=True: set only if not exists; returns None if key already existed
    return existed is None


async def send_detection_notifications(
    session: AsyncSession,
    valkey: Any,
    detection: Detection,
) -> None:
    """Dispatch notifications for a detection to all configured channels."""
    if not detection.rule_id:
        return

    # Load notification configs for enabled channels
    stmt = select(NotificationConfig).where(
        NotificationConfig.enabled.is_(True),
    )
    result = await session.execute(stmt)
    configs = result.scalars().all()

    if not configs:
        return

    # Check global dedup
    if await _is_duplicate(valkey, detection.rule_id, detection):
        logger.debug(
            "notification.deduped",
            rule_id=detection.rule_id,
            detection_id=detection.id,
        )
        return

    for config in configs:
        if detection.severity not in (config.notify_severities or []):
            continue
        try:
            if config.channel_type == "slack":
                await _send_slack_notification(config, detection)
            elif config.channel_type == "email":
                await _send_email_notification(config, detection)
            else:
                logger.warning(
                    "notification.unknown_channel",
                    channel_type=config.channel_type,
                )
        except Exception as exc:
            logger.error(
                "notification.send_failed",
                channel_type=config.channel_type,
                config_id=config.id,
                error=str(exc),
            )


def _render_slack_blocks(detection: Detection) -> list[dict]:
    """Build Slack Block Kit message for a detection."""
    severity_emoji = {
        "critical": ":rotating_light:",
        "high": ":red_circle:",
        "medium": ":large_yellow_circle:",
        "low": ":large_blue_circle:",
        "info": ":information_source:",
    }.get(detection.severity, ":warning:")

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{severity_emoji} {detection.title}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Severity:*\n{detection.severity}"},
                {"type": "mrkdwn", "text": f"*Confidence:*\n{detection.confidence}"},
                {"type": "mrkdwn", "text": f"*Actor:*\n{detection.actor or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*Org:*\n{detection.org or 'N/A'}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Description:*\n{detection.description}"},
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Detection ID: {detection.id} | Triggered: "
                        f"{detection.triggered_at.isoformat() if detection.triggered_at else 'N/A'}"
                    ),
                }
            ],
        },
    ]


async def _send_slack_notification(
    config: NotificationConfig,
    detection: Detection,
) -> None:
    """Send Slack notification via Slack Web API."""
    token = config.credentials.get("bot_token", "") if config.credentials else ""
    if not token:
        logger.warning("notification.slack_no_token", config_id=config.id)
        return

    channel = config.destination or config.credentials.get("channel", "#security-alerts")
    client = AsyncWebClient(token=token)

    try:
        await client.chat_postMessage(
            channel=channel,
            text=f"[{detection.severity.upper()}] {detection.title}",
            blocks=_render_slack_blocks(detection),
        )
        logger.info(
            "notification.slack_sent",
            config_id=config.id,
            detection_id=detection.id,
        )
    except SlackApiError as exc:
        logger.error(
            "notification.slack_error",
            config_id=config.id,
            error=exc.response.get("error", str(exc)),
        )
        raise


async def _send_email_notification(
    config: NotificationConfig,
    detection: Detection,
) -> None:
    """Send email notification via SMTP (aiosmtplib)."""
    smtp_cfg = settings.INTEGRATIONS

    recipients = config.destination.split(",") if config.destination else []
    if not recipients:
        logger.warning("notification.email_no_recipients", config_id=config.id)
        return

    subject = f"[{detection.severity.upper()}] Security Alert: {detection.title}"

    # Build plain-text body
    body_text = (
        f"Severity: {detection.severity}\n"
        f"Confidence: {detection.confidence} ({detection.confidence_score:.2f})\n"
        f"Actor: {detection.actor or 'N/A'}\n"
        f"Org: {detection.org or 'N/A'}\n\n"
        f"Description:\n{detection.description}\n\n"
        f"Detection ID: {detection.id}\n"
        f"Triggered at: {detection.triggered_at}\n"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_cfg.SMTP_FROM_ADDRESS or ""
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body_text, "plain"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_cfg.SMTP_HOST or "localhost",
            port=smtp_cfg.SMTP_PORT,
            username=smtp_cfg.SMTP_USERNAME if smtp_cfg.SMTP_USERNAME else None,
            password=smtp_cfg.SMTP_PASSWORD if smtp_cfg.SMTP_PASSWORD else None,
            use_tls=smtp_cfg.SMTP_USE_TLS,
        )
        logger.info(
            "notification.email_sent",
            config_id=config.id,
            recipients=recipients,
            detection_id=detection.id,
        )
    except aiosmtplib.SMTPException as exc:
        logger.error("notification.smtp_error", config_id=config.id, error=str(exc))
        raise
