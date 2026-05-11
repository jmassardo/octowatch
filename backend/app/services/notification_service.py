"""Notification service: Slack, Email, PagerDuty, Teams with routing rules and digest mode.

Dispatches detection alerts to configured channels based on routing rules
(severity, rule category, org). Supports real-time and digest delivery modes.
Integrates with PagerDuty Events API v2 and Microsoft Teams Adaptive Cards.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib
import httpx
import structlog
from jinja2 import Environment, PackageLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.detection import Detection, RuleDefinition
from app.models.integration import NotificationConfig
from app.services.slack_service import (
    get_runtime_notification_config,
)
from app.services.slack_service import (
    send_slack_notification as send_octowatch_slack_notification,
)

logger = structlog.get_logger(__name__)

_DEDUP_TTL_DEFAULT = 3600  # 1 hour
_PAGERDUTY_EVENTS_URL = "https://events.pagerduty.com/v2/enqueue"

# PagerDuty severity mapping (detection severity → PD severity)
_PD_SEVERITY_MAP: dict[str, str] = {
    "critical": "critical",
    "high": "error",
    "medium": "warning",
    "low": "info",
    "info": "info",
}

# Jinja2 environment for notification templates
_jinja_env = Environment(
    loader=PackageLoader("app", "templates"),
    autoescape=select_autoescape(["html"]),
)


# ── Deduplication ────────────────────────────────────────────────────────────


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


# ── Routing ──────────────────────────────────────────────────────────────────


def _matches_config(
    config: NotificationConfig,
    detection: Detection,
    rule_category: str | None,
) -> bool:
    """Check if a detection matches a notification config's routing rules.

    Evaluates three filter dimensions in order: severity (required),
    rule category (optional), and org (optional). All specified filters
    must match for the config to be considered a match.
    """
    # Severity check (always required)
    if detection.severity not in (config.notify_severities or []):
        return False

    # Category check — only applied when the config specifies categories
    if config.rule_categories and rule_category not in config.rule_categories:
        return False

    # Org check — only applied when the config specifies org filter
    if config.org_filter and detection.org not in (config.org_filter or []):
        return False

    return True


# ── Main dispatch ────────────────────────────────────────────────────────────


async def send_detection_notifications(
    session: AsyncSession,
    valkey: Any,
    detection: Detection,
) -> None:
    """Dispatch notifications for a detection to all matching configured channels.

    Evaluates routing rules to determine which channels receive the alert.
    Falls back to catch-all configs when no specific rules match.
    """
    if not detection.rule_id:
        return

    # Load all enabled notification configs
    stmt = select(NotificationConfig).where(
        NotificationConfig.enabled.is_(True),
    )
    result = await session.execute(stmt)
    configs = list(result.scalars().all())

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

    # Load rule category for routing
    rule_category: str | None = None
    rule_result = await session.execute(
        select(RuleDefinition.category).where(RuleDefinition.id == detection.rule_id)
    )
    rule_category = rule_result.scalar_one_or_none()

    # Separate catch-all from specific configs
    specific_configs = [c for c in configs if not c.is_catch_all]
    catch_all_configs = [c for c in configs if c.is_catch_all]

    # Find matching specific configs
    matched_configs = [c for c in specific_configs if _matches_config(c, detection, rule_category)]

    # Fallback to catch-all if no specific configs matched
    if not matched_configs:
        matched_configs = [
            c for c in catch_all_configs if _matches_config(c, detection, rule_category)
        ]

    has_legacy_slack = any(c.channel_type == "slack" for c in matched_configs)
    if not has_legacy_slack:
        try:
            slack_config = await get_runtime_notification_config(session, "detections")
            if (
                slack_config.get("enabled")
                and slack_config.get("channel")
                and slack_config.get("bot_token")
            ):
                await send_octowatch_slack_notification(detection, slack_config)
        except Exception as exc:
            logger.error(
                "notification.slack_global_failed",
                detection_id=detection.id,
                error=str(exc),
            )

    for config in matched_configs:
        try:
            if config.channel_type == "slack":
                await _send_slack_notification(config, detection)
            elif config.channel_type == "email":
                await _send_email_notification(config, detection)
            elif config.channel_type == "pagerduty":
                await _send_pagerduty_notification(config, detection, valkey)
            elif config.channel_type == "teams":
                await _send_teams_notification(config, detection)
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


# ── Slack ────────────────────────────────────────────────────────────────────


def _render_slack_blocks(detection: Detection) -> list[dict[str, Any]]:
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
    """Send Slack notification via the shared Slack integration service."""
    token = settings.INTEGRATIONS.SLACK_BOT_TOKEN or (
        os.environ.get(config.credential_env_var, "") if config.credential_env_var else ""
    )
    if not token:
        logger.warning("notification.slack_no_token", config_id=config.id)
        return
    if not config.target:
        logger.warning("notification.slack_no_channel", config_id=config.id)
        return

    await send_octowatch_slack_notification(
        detection,
        {
            "enabled": True,
            "channel": config.target,
            "bot_token": token,
            "base_url": settings.AUTH.APP_BASE_URL,
        },
    )
    logger.info(
        "notification.slack_sent",
        config_id=config.id,
        detection_id=detection.id,
    )


# ── Email ────────────────────────────────────────────────────────────────────


async def _send_email_notification(
    config: NotificationConfig,
    detection: Detection,
) -> None:
    """Send email notification via SMTP (aiosmtplib).

    Recipients are read from ``config.target`` as a comma-separated list.
    """
    smtp_cfg = settings.INTEGRATIONS

    recipients = config.target.split(",") if config.target else []
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


# ── PagerDuty ────────────────────────────────────────────────────────────────


async def _send_pagerduty_notification(
    config: NotificationConfig,
    detection: Detection,
    valkey: Any,
) -> None:
    """Send PagerDuty alert via Events API v2.

    Reads the routing/integration key from the environment variable named
    by ``config.credential_env_var``. Stores the dedup_key in Valkey so
    the incident can later be auto-resolved.
    """
    routing_key = os.environ.get(config.credential_env_var, "") if config.credential_env_var else ""
    if not routing_key:
        logger.warning("notification.pagerduty_no_routing_key", config_id=config.id)
        return

    dedup_key = f"octowatch-detection-{detection.id}"
    pd_severity = _PD_SEVERITY_MAP.get(detection.severity, "info")

    payload: dict[str, Any] = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": dedup_key,
        "payload": {
            "summary": f"[{detection.severity.upper()}] {detection.title}",
            "source": "octowatch",
            "severity": pd_severity,
            "timestamp": (
                detection.triggered_at.isoformat()
                if detection.triggered_at
                else datetime.now(UTC).isoformat()
            ),
            "custom_details": {
                "detection_id": detection.id,
                "rule_id": detection.rule_id,
                "actor": detection.actor,
                "org": detection.org,
                "repo": detection.repo,
                "description": detection.description,
                "confidence": detection.confidence,
                "confidence_score": detection.confidence_score,
            },
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_PAGERDUTY_EVENTS_URL, json=payload)
        response.raise_for_status()

    # Store dedup_key → routing_key mapping for auto-resolve correlation
    await valkey.set(
        f"pagerduty:dedup:{detection.id}",
        routing_key,
        ex=86400 * 30,  # 30-day TTL
    )

    logger.info(
        "notification.pagerduty_sent",
        config_id=config.id,
        detection_id=detection.id,
        dedup_key=dedup_key,
    )


async def resolve_pagerduty_incident(
    valkey: Any,
    detection_id: int,
) -> bool:
    """Send a PagerDuty resolve event for a previously triggered detection.

    Retrieves the routing key from Valkey (stored during trigger) and sends
    a resolve event with the same dedup_key.

    Returns:
        True if a resolve was sent, False if no routing key was found.
    """
    routing_key = await valkey.get(f"pagerduty:dedup:{detection_id}")
    if not routing_key:
        logger.debug(
            "notification.pagerduty_no_resolve_key",
            detection_id=detection_id,
        )
        return False

    dedup_key = f"octowatch-detection-{detection_id}"
    payload: dict[str, Any] = {
        "routing_key": routing_key,
        "event_action": "resolve",
        "dedup_key": dedup_key,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_PAGERDUTY_EVENTS_URL, json=payload)
        response.raise_for_status()

    await valkey.delete(f"pagerduty:dedup:{detection_id}")

    logger.info(
        "notification.pagerduty_resolved",
        detection_id=detection_id,
        dedup_key=dedup_key,
    )
    return True


# ── Microsoft Teams ──────────────────────────────────────────────────────────


def _build_teams_adaptive_card(detection: Detection) -> dict[str, Any]:
    """Build a Microsoft Teams Adaptive Card payload for a detection."""
    severity_color = {
        "critical": "attention",
        "high": "attention",
        "medium": "warning",
        "low": "accent",
        "info": "default",
    }.get(detection.severity, "default")

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
                            "text": f"\U0001f512 {detection.title}",
                            "style": "heading",
                        },
                        {
                            "type": "ColumnSet",
                            "columns": [
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "Severity",
                                            "weight": "Bolder",
                                            "isSubtle": True,
                                        },
                                        {
                                            "type": "TextBlock",
                                            "text": detection.severity.upper(),
                                            "color": severity_color,
                                            "weight": "Bolder",
                                        },
                                    ],
                                },
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "Confidence",
                                            "weight": "Bolder",
                                            "isSubtle": True,
                                        },
                                        {
                                            "type": "TextBlock",
                                            "text": detection.confidence,
                                        },
                                    ],
                                },
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "Actor",
                                            "weight": "Bolder",
                                            "isSubtle": True,
                                        },
                                        {
                                            "type": "TextBlock",
                                            "text": detection.actor or "N/A",
                                        },
                                    ],
                                },
                                {
                                    "type": "Column",
                                    "width": "auto",
                                    "items": [
                                        {
                                            "type": "TextBlock",
                                            "text": "Org",
                                            "weight": "Bolder",
                                            "isSubtle": True,
                                        },
                                        {
                                            "type": "TextBlock",
                                            "text": detection.org or "N/A",
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": detection.description,
                            "wrap": True,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {
                                    "title": "Detection ID",
                                    "value": str(detection.id),
                                },
                                {
                                    "title": "Triggered",
                                    "value": (
                                        detection.triggered_at.isoformat()
                                        if detection.triggered_at
                                        else "N/A"
                                    ),
                                },
                            ],
                        },
                    ],
                },
            }
        ],
    }


async def _send_teams_notification(
    config: NotificationConfig,
    detection: Detection,
) -> None:
    """Send Microsoft Teams notification via incoming webhook.

    The webhook URL is stored in ``config.target``. No additional
    credentials are needed as the webhook URL contains the auth token.
    """
    webhook_url = config.target
    if not webhook_url:
        logger.warning("notification.teams_no_webhook", config_id=config.id)
        return

    card = _build_teams_adaptive_card(detection)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(webhook_url, json=card)
        response.raise_for_status()

    logger.info(
        "notification.teams_sent",
        config_id=config.id,
        detection_id=detection.id,
    )


# ── Digest mode ──────────────────────────────────────────────────────────────


async def build_and_send_digest(
    session: AsyncSession,
    valkey: Any,
    config: NotificationConfig,
) -> dict[str, object]:
    """Build and send a digest email summarising detections since the last digest.

    Queries all detections created since the last digest timestamp (tracked
    in Valkey), groups them by severity, renders Jinja2 templates, and
    sends via SMTP.  Skips if there are no detections (no empty digests).

    Returns:
        A dict with ``status`` ("sent" or "skipped") and ``count``.
    """
    # Determine period start from last digest timestamp
    last_sent_raw = await valkey.get(f"digest:last_sent:{config.id}")
    if last_sent_raw:
        last_sent = datetime.fromisoformat(last_sent_raw)
    else:
        last_sent = datetime.now(UTC) - timedelta(hours=24)

    # Query detections since last digest
    stmt = (
        select(Detection)
        .where(Detection.triggered_at > last_sent)
        .order_by(Detection.triggered_at.desc())
    )
    result = await session.execute(stmt)
    detections = list(result.scalars().all())

    if not detections:
        return {"status": "skipped", "reason": "no_detections", "count": 0}

    # Group detections by severity in priority order
    grouped: dict[str, list[Detection]] = defaultdict(list)
    for d in detections:
        grouped[d.severity].append(d)

    severity_order = ["critical", "high", "medium", "low", "info"]
    ordered_grouped: dict[str, list[Detection]] = {}
    for sev in severity_order:
        if sev in grouped:
            ordered_grouped[sev] = grouped[sev]

    severity_counts = {sev: len(dets) for sev, dets in ordered_grouped.items()}
    now = datetime.now(UTC)

    template_context = {
        "period_start": last_sent.strftime("%Y-%m-%d %H:%M UTC"),
        "period_end": now.strftime("%Y-%m-%d %H:%M UTC"),
        "total_count": len(detections),
        "severity_counts": severity_counts,
        "grouped_detections": ordered_grouped,
    }

    # Render templates
    html_template = _jinja_env.get_template("digest_email.html")
    text_template = _jinja_env.get_template("digest_email.txt")
    html_body = html_template.render(**template_context)
    text_body = text_template.render(**template_context)

    # Build email
    recipients = config.target.split(",") if config.target else []
    if not recipients:
        logger.warning("notification.digest_no_recipients", config_id=config.id)
        return {"status": "skipped", "reason": "no_recipients", "count": 0}

    smtp_cfg = settings.INTEGRATIONS
    count = len(detections)
    subject = f"OctoWatch Security Digest \u2014 {count} detection{'s' if count != 1 else ''}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_cfg.SMTP_FROM_ADDRESS or ""
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    await aiosmtplib.send(
        msg,
        hostname=smtp_cfg.SMTP_HOST or "localhost",
        port=smtp_cfg.SMTP_PORT,
        username=smtp_cfg.SMTP_USERNAME if smtp_cfg.SMTP_USERNAME else None,
        password=smtp_cfg.SMTP_PASSWORD if smtp_cfg.SMTP_PASSWORD else None,
        use_tls=smtp_cfg.SMTP_USE_TLS,
    )

    # Record last digest timestamp
    await valkey.set(f"digest:last_sent:{config.id}", now.isoformat())

    logger.info(
        "notification.digest_sent",
        config_id=config.id,
        detection_count=count,
        recipients=recipients,
    )

    return {"status": "sent", "count": count}
