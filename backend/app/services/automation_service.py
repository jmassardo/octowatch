"""Detection-triggered automation service.

Handles building alert payloads, HMAC-SHA256 signing, webhook delivery,
GitHub repository_dispatch, rate limiting, and retry logic.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Rate limiter: in-memory sliding window (per target_id)
_rate_windows: dict[int, list[float]] = {}


def _check_rate_limit(target_id: int, max_per_minute: int) -> bool:
    """Return True if delivery is allowed, False if rate limited."""
    now = time.time()
    window = _rate_windows.setdefault(target_id, [])
    # Remove entries older than 60 seconds
    cutoff = now - 60
    _rate_windows[target_id] = [t for t in window if t > cutoff]
    if len(_rate_windows[target_id]) >= max_per_minute:
        return False
    _rate_windows[target_id].append(now)
    return True


def build_alert_payload(
    detection: dict[str, Any],
    rule: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the structured JSON payload for automation delivery.

    Payload includes:
    - alert: id, triggered_at, severity, confidence_score, status
    - rule: id, name, slug, category, logic_type
    - actor: login, org, repo
    - events: list of contributing event summaries (action, timestamp, source_ip)
    - meta: octowatch_version, delivered_at
    """
    return {
        "alert": {
            "id": detection.get("id"),
            "triggered_at": detection.get("triggered_at"),
            "severity": detection.get("severity"),
            "confidence": detection.get("confidence"),
            "confidence_score": detection.get("confidence_score"),
            "status": detection.get("status"),
        },
        "rule": {
            "id": rule.get("id"),
            "name": rule.get("name"),
            "slug": rule.get("slug"),
            "category": rule.get("category"),
            "logic_type": rule.get("logic_type"),
        },
        "actor": {
            "login": detection.get("actor"),
            "org": detection.get("org"),
            "repo": detection.get("repo"),
        },
        "events": [
            {
                "action": e.get("action"),
                "timestamp": e.get("created_at"),
                "source_ip": e.get("source_ip"),
                "repo": e.get("repo"),
            }
            for e in (events or [])
        ][:20],  # Cap at 20 events
        "meta": {
            "source": "octowatch",
            "version": "0.1.0",
            "delivered_at": datetime.now(UTC).isoformat(),
        },
    }


def sign_payload(payload_json: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook verification.

    Returns hex digest prefixed with 'sha256='.
    """
    mac = hmac.new(secret.encode(), payload_json.encode(), hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


async def get_matching_targets(
    db: AsyncSession,
    detection: dict[str, Any],
    rule: dict[str, Any],
) -> list[dict[str, Any]]:
    """Find all automation targets that match this detection.

    Matching logic:
    1. Target must be enabled
    2. Check filters (any match = include):
       - is_catch_all=True -> always matches
       - rule_ids contains this rule's id
       - rule_categories contains this rule's category
       - severity_filter contains this detection's severity
    3. If org_filter is set, detection org must match
    """
    result = await db.execute(
        text("""
            SELECT id, name, target_type, webhook_url, webhook_secret, webhook_headers,
                   dispatch_repo, dispatch_event_type, dispatch_token_env_var,
                   rule_ids, rule_categories, severity_filter, org_filter,
                   is_catch_all, rate_limit_per_minute, max_retries
            FROM automation_targets
            WHERE enabled = TRUE
        """)
    )
    rows = result.fetchall()

    matching: list[dict[str, Any]] = []
    rule_id = rule.get("id")
    rule_category = rule.get("category")
    severity = detection.get("severity")
    org = detection.get("org")

    for row in rows:
        target: dict[str, Any] = dict(row._mapping)

        # Check org filter first (if set, must match)
        if target["org_filter"] and org not in target["org_filter"]:
            continue

        # Check if target matches this detection
        if target["is_catch_all"]:
            matching.append(target)
            continue
        if target["rule_ids"] and rule_id in target["rule_ids"]:
            matching.append(target)
            continue
        if target["rule_categories"] and rule_category in target["rule_categories"]:
            matching.append(target)
            continue
        if target["severity_filter"] and severity in target["severity_filter"]:
            matching.append(target)
            continue

    return matching


async def deliver_webhook(
    target: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[int | None, str | None]:
    """POST payload to webhook URL with HMAC signature.

    Returns (status_code, error_message). status_code is None on connection failure.
    """
    url: str = target["webhook_url"]
    secret: str = target.get("webhook_secret") or ""
    custom_headers: dict[str, str] = target.get("webhook_headers") or {}

    payload_json = json.dumps(payload, default=str)

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "User-Agent": "OctoWatch/0.1.0",
        "X-OctoWatch-Event": "detection.triggered",
        **custom_headers,
    }

    if secret:
        signature = sign_payload(payload_json, secret)
        headers["X-OctoWatch-Signature-256"] = signature

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=payload_json, headers=headers)
            error_body: str | None = None if resp.status_code < 400 else resp.text[:1024]
            return resp.status_code, error_body
    except httpx.TimeoutException:
        return None, "Connection timeout"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:1024]


async def deliver_repository_dispatch(
    target: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[int | None, str | None]:
    """Trigger a GitHub repository_dispatch event.

    Returns (status_code, error_message).
    """
    repo: str = target["dispatch_repo"]
    event_type: str = target.get("dispatch_event_type") or "octowatch.detection"
    token_env_var: str = target.get("dispatch_token_env_var") or "GITHUB_AUTOMATION_TOKEN"

    token = os.environ.get(token_env_var)
    if not token:
        return None, f"Token env var {token_env_var} not set"

    url = f"https://api.github.com/repos/{repo}/dispatches"

    body: dict[str, Any] = {
        "event_type": event_type,
        "client_payload": payload,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "OctoWatch/0.1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            # 204 = success for repository_dispatch
            if resp.status_code == 204:
                return 204, None
            return resp.status_code, resp.text[:1024]
    except httpx.TimeoutException:
        return None, "Connection timeout"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:1024]


async def dispatch_automation(
    db: AsyncSession,
    detection_id: int,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Main entry point: dispatch all matching automation targets for a detection.

    Steps:
    1. Load detection + rule from DB
    2. Load contributing events
    3. Find matching targets
    4. For each target: check rate limit, build payload, deliver, record delivery

    Returns summary dict.
    """
    # 1. Load detection and rule
    det_result = await db.execute(
        text("""
            SELECT d.id, d.rule_id, d.triggered_at, d.severity, d.confidence,
                   d.confidence_score, d.status, d.actor, d.data,
                   d.event_ids,
                   r.id as rule_id, r.name as rule_name, r.slug as rule_slug,
                   r.category as rule_category, r.logic_type as rule_logic_type
            FROM detections d
            JOIN rule_definitions r ON d.rule_id = r.id
            WHERE d.id = :detection_id
        """),
        {"detection_id": detection_id},
    )
    row = det_result.fetchone()
    if not row:
        logger.warning("automation.detection_not_found", detection_id=detection_id)
        return {"dispatched": 0, "error": "detection not found"}

    detection: dict[str, Any] = dict(row._mapping)
    # Extract org/repo from detection data
    data = detection.get("data") or {}
    if isinstance(data, str):
        data = json.loads(data)
    detection["org"] = data.get("org") or detection.get("org")
    detection["repo"] = data.get("repo") or detection.get("repo")

    rule: dict[str, Any] = {
        "id": detection["rule_id"],
        "name": detection["rule_name"],
        "slug": detection["rule_slug"],
        "category": detection["rule_category"],
        "logic_type": detection["rule_logic_type"],
    }

    # 2. Load contributing events (up to 20)
    events: list[dict[str, Any]] = []
    event_ids = detection.get("event_ids") or []
    if event_ids:
        ev_result = await db.execute(
            text("""
                SELECT action, created_at, source_ip, repo
                FROM events
                WHERE id = ANY(:ids)
                ORDER BY created_at DESC
                LIMIT 20
            """),
            {"ids": event_ids[:20]},
        )
        events = [dict(r._mapping) for r in ev_result.fetchall()]

    # 3. Find matching targets
    targets = await get_matching_targets(db, detection, rule)

    if not targets:
        logger.debug("automation.no_matching_targets", detection_id=detection_id)
        return {"dispatched": 0, "targets_matched": 0}

    # 4. Build payload and deliver to each target
    payload = build_alert_payload(detection, rule, events)
    payload_hash = hashlib.sha256(json.dumps(payload, default=str).encode()).hexdigest()[:16]

    dispatched = 0
    rate_limited = 0
    failed = 0

    for target in targets:
        # Rate limit check
        if not _check_rate_limit(target["id"], target["rate_limit_per_minute"]):
            rate_limited += 1
            await _record_delivery(
                db, target["id"], detection_id, "rate_limited", payload_hash, dry_run=dry_run
            )
            continue

        if dry_run:
            await _record_delivery(
                db,
                target["id"],
                detection_id,
                "dry_run",
                payload_hash,
                dry_run=True,
                response_code=200,
            )
            dispatched += 1
            continue

        # Deliver based on type
        if target["target_type"] == "webhook":
            status_code, error = await deliver_webhook(target, payload)
        elif target["target_type"] == "repository_dispatch":
            status_code, error = await deliver_repository_dispatch(target, payload)
        else:
            error = f"Unknown target type: {target['target_type']}"
            status_code = None

        # Record delivery
        success = status_code is not None and status_code < 400
        status = "success" if success else "failed"

        await _record_delivery(
            db,
            target["id"],
            detection_id,
            status,
            payload_hash,
            dry_run=False,
            response_code=status_code,
            error_message=error,
        )

        if success:
            dispatched += 1
        else:
            failed += 1
            logger.warning(
                "automation.delivery_failed",
                target_id=target["id"],
                detection_id=detection_id,
                status_code=status_code,
                error=error,
            )

    await db.commit()

    logger.info(
        "automation.dispatch_complete",
        detection_id=detection_id,
        dispatched=dispatched,
        rate_limited=rate_limited,
        failed=failed,
    )

    return {
        "dispatched": dispatched,
        "targets_matched": len(targets),
        "rate_limited": rate_limited,
        "failed": failed,
    }


async def retry_failed_deliveries(db: AsyncSession) -> dict[str, Any]:
    """Retry deliveries that are in 'failed' status and eligible for retry.

    Called by a periodic task scheduler.
    """
    now = datetime.now(UTC)

    result = await db.execute(
        text("""
            SELECT ad.id, ad.target_id, ad.detection_id, ad.attempts,
                   at.max_retries, at.target_type, at.webhook_url, at.webhook_secret,
                   at.webhook_headers, at.dispatch_repo, at.dispatch_event_type,
                   at.dispatch_token_env_var, at.rate_limit_per_minute
            FROM automation_deliveries ad
            JOIN automation_targets at ON ad.target_id = at.id
            WHERE ad.status = 'failed'
              AND ad.attempts < at.max_retries
              AND (ad.next_retry_at IS NULL OR ad.next_retry_at <= :now)
              AND ad.is_dry_run = FALSE
            ORDER BY ad.created_at ASC
            LIMIT 100
        """),
        {"now": now},
    )
    rows = result.fetchall()

    retried = 0
    succeeded = 0

    for row in rows:
        delivery: dict[str, Any] = dict(row._mapping)

        # Rebuild payload from detection
        det_result = await db.execute(
            text("""
                SELECT d.id, d.rule_id, d.triggered_at, d.severity, d.confidence,
                       d.confidence_score, d.status, d.actor, d.data, d.event_ids,
                       r.name as rule_name, r.slug as rule_slug,
                       r.category as rule_category, r.logic_type as rule_logic_type
                FROM detections d
                JOIN rule_definitions r ON d.rule_id = r.id
                WHERE d.id = :det_id
            """),
            {"det_id": delivery["detection_id"]},
        )
        det_row = det_result.fetchone()
        if not det_row:
            continue

        det_data: dict[str, Any] = dict(det_row._mapping)
        rule: dict[str, Any] = {
            "id": det_data["rule_id"],
            "name": det_data["rule_name"],
            "slug": det_data["rule_slug"],
            "category": det_data["rule_category"],
            "logic_type": det_data["rule_logic_type"],
        }
        payload = build_alert_payload(det_data, rule)

        # Attempt delivery
        if delivery["target_type"] == "webhook":
            status_code, error = await deliver_webhook(delivery, payload)
        else:
            status_code, error = await deliver_repository_dispatch(delivery, payload)

        success = status_code is not None and status_code < 400
        new_attempts = delivery["attempts"] + 1

        if success:
            await db.execute(
                text("""
                    UPDATE automation_deliveries
                    SET status = 'success', attempts = :attempts,
                        last_attempt_at = :now, response_code = :code,
                        error_message = NULL
                    WHERE id = :id
                """),
                {
                    "id": delivery["id"],
                    "attempts": new_attempts,
                    "now": now,
                    "code": status_code,
                },
            )
            succeeded += 1
        else:
            # Calculate next retry with exponential backoff
            backoff_seconds = min(300, 30 * (2**new_attempts))
            next_retry = now + timedelta(seconds=backoff_seconds)
            final_status = "failed" if new_attempts < delivery["max_retries"] else "exhausted"

            await db.execute(
                text("""
                    UPDATE automation_deliveries
                    SET status = :status, attempts = :attempts,
                        last_attempt_at = :now, next_retry_at = :next_retry,
                        response_code = :code, error_message = :error
                    WHERE id = :id
                """),
                {
                    "id": delivery["id"],
                    "status": final_status,
                    "attempts": new_attempts,
                    "now": now,
                    "next_retry": next_retry,
                    "code": status_code,
                    "error": error,
                },
            )

        retried += 1

    await db.commit()
    return {"retried": retried, "succeeded": succeeded}


async def _record_delivery(
    db: AsyncSession,
    target_id: int,
    detection_id: int,
    status: str,
    payload_hash: str,
    *,
    dry_run: bool = False,
    response_code: int | None = None,
    error_message: str | None = None,
) -> None:
    """Insert a delivery record."""
    now = datetime.now(UTC)
    next_retry: datetime | None = None
    if status == "failed":
        next_retry = now + timedelta(seconds=30)  # First retry after 30s

    await db.execute(
        text("""
            INSERT INTO automation_deliveries
                (target_id, detection_id, status, attempts, last_attempt_at,
                 next_retry_at, response_code, response_body, error_message,
                 payload_hash, is_dry_run)
            VALUES
                (:target_id, :detection_id, :status, 1, :now,
                 :next_retry, :response_code, NULL, :error_message,
                 :payload_hash, :is_dry_run)
        """),
        {
            "target_id": target_id,
            "detection_id": detection_id,
            "status": status,
            "now": now,
            "next_retry": next_retry,
            "response_code": response_code,
            "error_message": error_message,
            "payload_hash": payload_hash,
            "is_dry_run": dry_run,
        },
    )
