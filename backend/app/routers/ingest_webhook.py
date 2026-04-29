"""Ingest webhook receiver: accept GitHub organization webhooks for near-real-time ingestion.

Validates HMAC-SHA256 signatures, parses event payloads, and enqueues them
for ingestion via the existing dedup + insert pipeline. The GitHub IP
allowlist middleware (applied in main.py) already protects this path.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


# NOTE: This function will be refactored in a future PR (Issue #135, Story 4+)
# to use SecretProvider directly:
#   secret_provider.get_secret("github-webhook-secret")
# For now, the env var approach remains for backward compatibility.
def _get_webhook_secret() -> str:
    """Retrieve the GitHub webhook secret from environment.

    The environment variable name is ``GITHUB_WEBHOOK_SECRET``.  The value
    itself is never hardcoded — only fetched at runtime from the process env.
    """
    return os.environ.get("GITHUB_WEBHOOK_SECRET", "")


def _verify_signature(payload: bytes, signature_header: str, secret: str) -> bool:
    """Validate the GitHub HMAC-SHA256 webhook signature.

    GitHub sends the header as ``X-Hub-Signature-256: sha256=<hex>``.

    Args:
        payload: Raw request body bytes.
        signature_header: Value of X-Hub-Signature-256 header.
        secret: The shared webhook secret.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not signature_header.startswith("sha256="):
        return False

    expected_sig = signature_header[7:]  # strip "sha256=" prefix
    computed = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_sig)


@router.post(
    "/webhook",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=JSONResponse,
)
async def receive_github_webhook(request: Request) -> JSONResponse:
    """Receive a GitHub webhook payload and enqueue it for ingestion.

    Validates HMAC-SHA256 signature, extracts the event type from headers,
    and hands off to the Celery ingestion pipeline. Returns 202 Accepted
    immediately to keep response times low.

    The GitHub IP allowlist middleware already protects this endpoint against
    non-GitHub sources (returns 403).
    """
    # 1. Verify webhook secret is configured — mandatory in production.
    secret = _get_webhook_secret()
    if not secret:
        logger.error(
            "webhook.no_secret_configured",
            detail="GITHUB_WEBHOOK_SECRET is not set. Configure it to accept webhooks.",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook endpoint is not configured — contact the administrator",
        )

    # 2. Read raw body
    body = await request.body()
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty request body",
        )

    # 3. Validate HMAC-SHA256 signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature:
        logger.warning("webhook.missing_signature", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )

    if not _verify_signature(body, signature, secret):
        logger.warning("webhook.invalid_signature", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # 4. Parse event type
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    # 5. Parse JSON payload
    try:
        import json

        payload: dict[str, Any] = json.loads(body)
    except (ValueError, TypeError) as exc:
        logger.warning("webhook.invalid_json", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    # 6. Normalize into audit-log-like event format
    event = _normalize_webhook_event(payload, event_type, delivery_id)

    if not event:
        # Some event types (like ping) don't produce audit events
        logger.info("webhook.skipped", event_type=event_type)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "skipped", "event_type": event_type},
        )

    # 7. Enqueue for ingestion via Celery
    try:
        from app.workers.ingest_webhook_worker import ingest_webhook_event_task

        ingest_webhook_event_task.delay(event)
        logger.info(
            "webhook.enqueued",
            event_type=event_type,
            delivery_id=delivery_id,
            action=event.get("action"),
        )
    except Exception as exc:
        logger.error("webhook.enqueue_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue event for processing",
        ) from exc

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "status": "accepted",
            "event_type": event_type,
            "delivery_id": delivery_id,
        },
    )


def _normalize_webhook_event(
    payload: dict[str, Any],
    event_type: str,
    delivery_id: str,
) -> dict[str, Any] | None:
    """Transform a GitHub webhook payload into an audit-log-like event dict.

    GitHub webhooks have a different schema from audit log entries. This function
    maps common fields so the event can be processed by the standard ingestion
    pipeline (dedup hash, normalization, DB insert).

    Args:
        payload: Parsed JSON payload from GitHub.
        event_type: Value of X-GitHub-Event header.
        delivery_id: Value of X-GitHub-Delivery header (unique per delivery).

    Returns:
        Normalized event dict, or None if the event should be skipped.
    """
    # Skip ping events (used to verify webhook connectivity)
    if event_type == "ping":
        return None

    # Build action string similar to audit log format
    action_suffix = payload.get("action", event_type)
    action = f"{event_type}.{action_suffix}" if action_suffix != event_type else event_type

    # Extract common fields
    sender = payload.get("sender", {})
    actor = sender.get("login") if isinstance(sender, dict) else None

    org_data = payload.get("organization", {})
    org = org_data.get("login") if isinstance(org_data, dict) else None

    repo_data = payload.get("repository", {})
    repo_full_name = repo_data.get("full_name") if isinstance(repo_data, dict) else None

    return {
        "action": action,
        "actor": actor,
        "actor_id": sender.get("id") if isinstance(sender, dict) else None,
        "org": org,
        "repo": repo_full_name,
        "created_at": payload.get("created_at") or payload.get("updated_at"),
        "_document_id": delivery_id or None,
        "webhook_event_type": event_type,
        "data": payload,
    }
