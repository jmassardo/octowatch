"""SIEM export service: CEF/LEEF syslog, Splunk HEC, and SOAR outbound webhooks.

Dispatches detection alerts and raw events to configured SIEM/SOAR destinations.
Supports CEF (Splunk/Sentinel/ArcSight), LEEF (QRadar), Splunk HEC JSON, and
generic SOAR webhook with exponential-backoff retry.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import ssl
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.detection import Detection, RuleDefinition
from app.models.integration import SiemExportConfig

logger = structlog.get_logger(__name__)

# Severity mapping: detection severity → CEF integer (0-10)
_CEF_SEVERITY_MAP: dict[str, int] = {
    "critical": 10,
    "high": 8,
    "medium": 5,
    "low": 3,
    "info": 1,
}

# Severity mapping: detection severity → LEEF integer
_LEEF_SEVERITY_MAP: dict[str, int] = _CEF_SEVERITY_MAP

# Maximum retry attempts for outbound webhooks
_MAX_RETRIES = 3

# Base backoff delay in seconds
_BASE_BACKOFF = 1.0


# ── CEF / LEEF Formatting ───────────────────────────────────────────────────


def _escape_cef_value(value: str) -> str:
    """Escape special characters in CEF extension values."""
    return value.replace("\\", "\\\\").replace("=", "\\=").replace("\n", "\\n")


def _escape_cef_header(value: str) -> str:
    """Escape special characters in CEF header fields."""
    return value.replace("\\", "\\\\").replace("|", "\\|")


def format_cef(
    detection: Detection,
    rule: RuleDefinition | None = None,
    events: list[dict[str, Any]] | None = None,
) -> str:
    """Format a detection as a CEF (Common Event Format) syslog message.

    Format: CEF:0|OctoWatch|OctoWatch|1.0|signatureId|name|severity|extension

    Args:
        detection: The detection to format.
        rule: The associated rule definition (optional, for slug).
        events: Related event data (optional, for additional context).

    Returns:
        CEF-formatted string ready for syslog transport.
    """
    signature_id = rule.slug if rule else f"rule_{detection.rule_id}"
    name = _escape_cef_header(detection.title)
    severity = _CEF_SEVERITY_MAP.get(detection.severity, 5)

    # Build extension key=value pairs
    extensions: list[str] = []
    if detection.actor:
        extensions.append(f"src={_escape_cef_value(detection.actor)}")
    if detection.repo:
        extensions.append(f"dst={_escape_cef_value(detection.repo)}")
    if detection.org:
        extensions.append(f"cs1={_escape_cef_value(detection.org)}")
        extensions.append("cs1Label=Organization")
    if detection.description:
        msg = detection.description[:1023]
        extensions.append(f"msg={_escape_cef_value(msg)}")
    if detection.source_ip:
        extensions.append(f"sourceAddress={str(detection.source_ip)}")

    extensions.append(f"cs2={detection.severity}")
    extensions.append("cs2Label=DetectionSeverity")
    extensions.append(f"cs3={detection.confidence}")
    extensions.append("cs3Label=Confidence")
    extensions.append(f"cs4={detection.status}")
    extensions.append("cs4Label=DetectionStatus")

    # Detection timestamp
    triggered_at = detection.triggered_at
    if triggered_at:
        extensions.append(f"rt={int(triggered_at.timestamp() * 1000)}")

    extensions.append(f"externalId={detection.id}")

    # Event count
    if detection.event_ids:
        extensions.append(f"cnt={len(detection.event_ids)}")

    extension_str = " ".join(extensions)

    return (
        f"CEF:0|OctoWatch|OctoWatch|1.0"
        f"|{_escape_cef_header(signature_id)}"
        f"|{name}"
        f"|{severity}"
        f"|{extension_str}"
    )


def format_leef(
    detection: Detection,
    rule: RuleDefinition | None = None,
    events: list[dict[str, Any]] | None = None,
) -> str:
    """Format a detection as a LEEF 2.0 (QRadar) message.

    Format: LEEF:2.0|OctoWatch|OctoWatch|1.0|signatureId|key=value<TAB>key=value

    Args:
        detection: The detection to format.
        rule: The associated rule definition (optional, for slug).
        events: Related event data (optional, for additional context).

    Returns:
        LEEF-formatted string ready for syslog transport.
    """
    signature_id = rule.slug if rule else f"rule_{detection.rule_id}"

    # LEEF key=value pairs separated by tabs
    kv_pairs: list[str] = []
    kv_pairs.append(f"cat={detection.severity}")
    kv_pairs.append(f"sev={_LEEF_SEVERITY_MAP.get(detection.severity, 5)}")

    if detection.actor:
        kv_pairs.append(f"usrName={detection.actor}")
    if detection.repo:
        kv_pairs.append(f"resource={detection.repo}")
    if detection.org:
        kv_pairs.append(f"org={detection.org}")
    if detection.description:
        msg = detection.description[:1023].replace("\t", " ")
        kv_pairs.append(f"msg={msg}")
    if detection.source_ip:
        kv_pairs.append(f"src={detection.source_ip}")
    if detection.triggered_at:
        kv_pairs.append(f"devTime={detection.triggered_at.isoformat()}")

    kv_pairs.append(f"externalId={detection.id}")
    kv_pairs.append(f"status={detection.status}")
    kv_pairs.append(f"confidence={detection.confidence}")

    if detection.event_ids:
        kv_pairs.append(f"eventCount={len(detection.event_ids)}")

    kv_str = "\t".join(kv_pairs)

    return f"LEEF:2.0|OctoWatch|OctoWatch|1.0|{signature_id}|{kv_str}"


# ── Syslog Transport ────────────────────────────────────────────────────────


async def send_syslog(config: SiemExportConfig, message: str) -> bool:
    """Send a message via syslog (TCP, UDP, or TLS).

    Args:
        config: SIEM export config with syslog_host, syslog_port, syslog_protocol.
        message: Pre-formatted CEF or LEEF message.

    Returns:
        True if sent successfully, False otherwise.
    """
    host = config.syslog_host
    port = config.syslog_port or 514
    protocol = (config.syslog_protocol or "udp").lower()

    if not host:
        logger.error("siem_export.syslog.no_host", config_id=config.id)
        return False

    # Syslog framing: message + newline
    payload = (message + "\n").encode("utf-8")

    try:
        if protocol == "udp":
            transport, _ = await asyncio.get_event_loop().create_datagram_endpoint(
                asyncio.DatagramProtocol,
                remote_addr=(host, port),
            )
            transport.sendto(payload)
            transport.close()

        elif protocol in ("tcp", "tls"):
            ssl_context: ssl.SSLContext | None = None
            if protocol == "tls":
                ssl_context = ssl.create_default_context()

            reader, writer = await asyncio.open_connection(host, port, ssl=ssl_context)
            # Octet-counting framing for TCP syslog (RFC 5425)
            framed = f"{len(payload)} ".encode() + payload
            writer.write(framed)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        else:
            logger.error(
                "siem_export.syslog.invalid_protocol",
                config_id=config.id,
                protocol=protocol,
            )
            return False

        logger.info(
            "siem_export.syslog.sent",
            config_id=config.id,
            host=host,
            port=port,
            protocol=protocol,
        )
        return True

    except Exception as exc:
        logger.error(
            "siem_export.syslog.failed",
            config_id=config.id,
            host=host,
            port=port,
            error=str(exc),
        )
        return False


# ── Splunk HEC ──────────────────────────────────────────────────────────────


async def send_splunk_hec(
    config: SiemExportConfig,
    payload: dict[str, Any],
    sourcetype: str = "octowatch:detection",
) -> bool:
    """Post an event to Splunk HTTP Event Collector.

    Args:
        config: SIEM export config with splunk_hec_url and splunk_hec_token_env_var.
        payload: The event data to send.
        sourcetype: Splunk sourcetype (e.g. 'octowatch:detection' or 'octowatch:event').

    Returns:
        True if accepted by Splunk, False otherwise.
    """
    url = config.splunk_hec_url
    if not url:
        logger.error("siem_export.splunk_hec.no_url", config_id=config.id)
        return False

    token_env = config.splunk_hec_token_env_var or ""
    token = os.environ.get(token_env, "")
    if not token:
        logger.error(
            "siem_export.splunk_hec.no_token",
            config_id=config.id,
            env_var=token_env,
        )
        return False

    hec_payload = {
        "time": payload.get("time", int(datetime.now(UTC).timestamp())),
        "sourcetype": sourcetype,
        "source": "octowatch",
        "index": config.splunk_index or "main",
        "event": payload.get("event", payload),
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
            response = await client.post(
                url,
                json=hec_payload,
                headers={
                    "Authorization": f"Splunk {token}",
                    "Content-Type": "application/json",
                },
            )
            if response.status_code == 200:
                logger.info(
                    "siem_export.splunk_hec.sent",
                    config_id=config.id,
                    sourcetype=sourcetype,
                )
                return True

            logger.error(
                "siem_export.splunk_hec.rejected",
                config_id=config.id,
                status=response.status_code,
                body=response.text[:500],
            )
            return False

    except Exception as exc:
        logger.error(
            "siem_export.splunk_hec.failed",
            config_id=config.id,
            error=str(exc),
        )
        return False


# ── SOAR Webhook ────────────────────────────────────────────────────────────


def _build_webhook_payload(
    detection: Detection,
    rule: RuleDefinition | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the JSON payload for a SOAR webhook."""
    payload: dict[str, Any] = {
        "source": "octowatch",
        "version": "1.0",
        "event_type": "detection",
        "detection": {
            "id": detection.id,
            "title": detection.title,
            "description": detection.description,
            "severity": detection.severity,
            "confidence": detection.confidence,
            "confidence_score": detection.confidence_score,
            "status": detection.status,
            "actor": detection.actor,
            "org": detection.org,
            "repo": detection.repo,
            "source_ip": str(detection.source_ip) if detection.source_ip else None,
            "triggered_at": detection.triggered_at.isoformat() if detection.triggered_at else None,
            "event_count": len(detection.event_ids) if detection.event_ids else 0,
            "context_data": detection.context_data or {},
        },
    }

    if rule:
        payload["rule"] = {
            "id": rule.id,
            "name": rule.name,
            "slug": rule.slug,
            "category": rule.category,
            "description": rule.description,
        }

    if events:
        payload["related_events"] = events[:50]  # Cap at 50 events

    # Suggested actions based on severity
    actions: list[str] = []
    if detection.severity == "critical":
        actions.extend(
            [
                "Immediately investigate the actor's recent activity",
                "Consider suspending the actor's access",
                "Notify the security team lead",
            ]
        )
    elif detection.severity == "high":
        actions.extend(
            [
                "Review the actor's recent activity within 1 hour",
                "Check for related detections from the same actor",
            ]
        )
    elif detection.severity == "medium":
        actions.append("Investigate within 24 hours and assess risk")
    else:
        actions.append("Review during next triage cycle")

    payload["suggested_actions"] = actions

    return payload


def _compute_webhook_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


async def send_soar_webhook(
    config: SiemExportConfig,
    detection: Detection,
    rule: RuleDefinition | None = None,
    events: list[dict[str, Any]] | None = None,
) -> bool:
    """Send detection context to a SOAR webhook URL with exponential backoff retry.

    Args:
        config: SIEM export config with webhook_url and optional webhook_secret_env_var.
        detection: The detection that triggered the webhook.
        rule: The associated rule definition (optional).
        events: Related event data (optional).

    Returns:
        True if the webhook was delivered successfully, False after all retries exhausted.
    """
    url = config.webhook_url
    if not url:
        logger.error("siem_export.webhook.no_url", config_id=config.id)
        return False

    payload = _build_webhook_payload(detection, rule, events)
    payload_bytes = json.dumps(payload, default=str).encode("utf-8")

    # Build headers
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "OctoWatch/1.0",
        "X-OctoWatch-Event": "detection",
    }

    # Add HMAC signature if secret is configured
    secret_env = config.webhook_secret_env_var or ""
    secret = os.environ.get(secret_env, "")
    if secret:
        sig = _compute_webhook_signature(payload_bytes, secret)
        headers["X-OctoWatch-Signature-256"] = f"sha256={sig}"

    # Merge any custom headers from config
    if config.webhook_headers:
        headers.update(config.webhook_headers)

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=True) as client:
                response = await client.post(url, content=payload_bytes, headers=headers)

                if 200 <= response.status_code < 300:
                    logger.info(
                        "siem_export.webhook.sent",
                        config_id=config.id,
                        detection_id=detection.id,
                        attempt=attempt + 1,
                    )
                    return True

                logger.warning(
                    "siem_export.webhook.non_2xx",
                    config_id=config.id,
                    status=response.status_code,
                    attempt=attempt + 1,
                )

        except Exception as exc:
            logger.warning(
                "siem_export.webhook.error",
                config_id=config.id,
                attempt=attempt + 1,
                error=str(exc),
            )

        # Exponential backoff (skip sleep on last attempt)
        if attempt < _MAX_RETRIES - 1:
            backoff = _BASE_BACKOFF * (2**attempt)
            await asyncio.sleep(backoff)

    logger.error(
        "siem_export.webhook.exhausted",
        config_id=config.id,
        detection_id=detection.id,
        max_retries=_MAX_RETRIES,
    )
    return False


# ── Dispatch Orchestration ──────────────────────────────────────────────────


async def export_detection(
    db: AsyncSession,
    detection: Detection,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Export a detection to all enabled SIEM export destinations.

    Args:
        db: Database session.
        detection: The detection to export.
        events: Related event data (optional).

    Returns:
        Dict with counts of successful and failed exports.
    """
    result = await db.execute(
        select(SiemExportConfig).where(
            SiemExportConfig.enabled.is_(True),
            SiemExportConfig.export_detections.is_(True),
        )
    )
    configs = list(result.scalars().all())

    if not configs:
        return {"sent": 0, "failed": 0}

    # Load associated rule for CEF/LEEF formatting
    rule: RuleDefinition | None = None
    rule_result = await db.execute(
        select(RuleDefinition).where(RuleDefinition.id == detection.rule_id)
    )
    rule = rule_result.scalar_one_or_none()

    sent = 0
    failed = 0

    for config in configs:
        try:
            success = False

            if config.export_type == "syslog":
                fmt = (config.syslog_format or "cef").lower()
                if fmt == "leef":
                    message = format_leef(detection, rule, events)
                else:
                    message = format_cef(detection, rule, events)
                success = await send_syslog(config, message)

            elif config.export_type == "splunk_hec":
                payload = _build_splunk_detection_payload(detection, rule)
                success = await send_splunk_hec(config, payload, sourcetype="octowatch:detection")

            elif config.export_type == "webhook":
                success = await send_soar_webhook(config, detection, rule, events)

            else:
                logger.warning(
                    "siem_export.unknown_type",
                    config_id=config.id,
                    export_type=config.export_type,
                )
                failed += 1
                continue

            if success:
                sent += 1
            else:
                failed += 1

        except Exception as exc:
            logger.error(
                "siem_export.dispatch_error",
                config_id=config.id,
                detection_id=detection.id,
                error=str(exc),
            )
            failed += 1

    if sent or failed:
        logger.info(
            "siem_export.detection_dispatched",
            detection_id=detection.id,
            sent=sent,
            failed=failed,
        )

    return {"sent": sent, "failed": failed}


async def export_events_to_splunk(
    db: AsyncSession,
    events: list[dict[str, Any]],
) -> dict[str, int]:
    """Forward raw events to Splunk HEC destinations that have export_events enabled.

    Args:
        db: Database session.
        events: List of normalized event dicts.

    Returns:
        Dict with counts of successful and failed exports.
    """
    result = await db.execute(
        select(SiemExportConfig).where(
            SiemExportConfig.enabled.is_(True),
            SiemExportConfig.export_events.is_(True),
            SiemExportConfig.export_type == "splunk_hec",
        )
    )
    configs = list(result.scalars().all())

    if not configs:
        return {"sent": 0, "failed": 0}

    sent = 0
    failed = 0

    for config in configs:
        for event in events:
            try:
                payload = _build_splunk_event_payload(event)
                success = await send_splunk_hec(config, payload, sourcetype="octowatch:event")
                if success:
                    sent += 1
                else:
                    failed += 1
            except Exception as exc:
                logger.error(
                    "siem_export.event_forward_error",
                    config_id=config.id,
                    error=str(exc),
                )
                failed += 1

    return {"sent": sent, "failed": failed}


async def batch_export(
    db: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    config_id: int,
) -> dict[str, int]:
    """Export all detections in a date range to a specific SIEM config.

    Args:
        db: Database session.
        start_date: Start of the export window.
        end_date: End of the export window.
        config_id: The SIEM export config to use.

    Returns:
        Dict with counts of exported and failed detections.
    """
    config_result = await db.execute(
        select(SiemExportConfig).where(SiemExportConfig.id == config_id)
    )
    config = config_result.scalar_one_or_none()
    if not config:
        return {"exported": 0, "failed": 0, "error": "Config not found"}  # type: ignore[dict-item]

    # Load detections in the date range
    detections_result = await db.execute(
        select(Detection).where(
            Detection.triggered_at >= start_date,
            Detection.triggered_at <= end_date,
        )
    )
    detections = list(detections_result.scalars().all())

    if not detections:
        return {"exported": 0, "failed": 0}

    exported = 0
    failed = 0

    for detection in detections:
        # Load rule for each detection
        rule_result = await db.execute(
            select(RuleDefinition).where(RuleDefinition.id == detection.rule_id)
        )
        rule = rule_result.scalar_one_or_none()

        try:
            success = False

            if config.export_type == "syslog":
                fmt = (config.syslog_format or "cef").lower()
                if fmt == "leef":
                    message = format_leef(detection, rule)
                else:
                    message = format_cef(detection, rule)
                success = await send_syslog(config, message)

            elif config.export_type == "splunk_hec":
                payload = _build_splunk_detection_payload(detection, rule)
                success = await send_splunk_hec(config, payload, sourcetype="octowatch:detection")

            elif config.export_type == "webhook":
                success = await send_soar_webhook(config, detection, rule)

            if success:
                exported += 1
            else:
                failed += 1

        except Exception as exc:
            logger.error(
                "siem_export.batch_item_error",
                config_id=config.id,
                detection_id=detection.id,
                error=str(exc),
            )
            failed += 1

    logger.info(
        "siem_export.batch_complete",
        config_id=config_id,
        exported=exported,
        failed=failed,
        total=len(detections),
    )
    return {"exported": exported, "failed": failed}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_splunk_detection_payload(
    detection: Detection,
    rule: RuleDefinition | None = None,
) -> dict[str, Any]:
    """Build Splunk HEC JSON payload for a detection."""
    event_data: dict[str, Any] = {
        "detection_id": detection.id,
        "title": detection.title,
        "description": detection.description,
        "severity": detection.severity,
        "confidence": detection.confidence,
        "confidence_score": detection.confidence_score,
        "status": detection.status,
        "actor": detection.actor,
        "org": detection.org,
        "repo": detection.repo,
        "source_ip": str(detection.source_ip) if detection.source_ip else None,
        "event_ids": detection.event_ids,
        "context_data": detection.context_data,
    }

    if rule:
        event_data["rule_name"] = rule.name
        event_data["rule_slug"] = rule.slug
        event_data["rule_category"] = rule.category

    return {
        "time": int(detection.triggered_at.timestamp()) if detection.triggered_at else None,
        "event": event_data,
    }


def _build_splunk_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Build Splunk HEC JSON payload for a raw event."""
    ts = event.get("created_at")
    epoch: int | None = None
    if isinstance(ts, datetime):
        epoch = int(ts.timestamp())
    elif isinstance(ts, str):
        try:
            epoch = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass

    return {
        "time": epoch,
        "event": {
            "action": event.get("action"),
            "actor": event.get("actor"),
            "org": event.get("org"),
            "repo": event.get("repo"),
            "source_ip": event.get("source_ip"),
            "created_at": str(ts) if ts else None,
            "data": event.get("data"),
        },
    }
