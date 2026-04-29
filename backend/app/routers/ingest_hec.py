"""Splunk HEC-compatible receiver for GitHub audit log streaming.

GitHub Enterprise Cloud can stream audit logs to a Splunk HTTP Event
Collector endpoint.  This router implements a minimal HEC-compatible
receiver that accepts those events and funnels them into the standard
OctoWatch ingestion pipeline (dedup → normalize → insert → detect).

GitHub sends events as JSON to ``POST /services/collector`` with an
``Authorization: Splunk <token>`` header.  The token is configured via
the ``HEC_TOKEN`` app setting or ``HEC_TOKEN`` environment variable.

Register this router **without** the ``/api/v1`` prefix so the path
matches what GitHub expects (``https://<host>/services/collector``).
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/services", tags=["hec"])

# In-memory cache set by the admin endpoint and loaded at startup.
# DB-saved token takes precedence; env var is the fallback.
_cached_hec_token: str | None = None


def set_hec_token_cache(token: str) -> None:
    """Update the in-memory HEC token cache (called by admin endpoint)."""
    global _cached_hec_token
    _cached_hec_token = token


# NOTE: This function will be refactored in a future PR (Issue #135, Story 4+)
# to use SecretProvider directly:
#   secret_provider.get_secret("hec-token")
# For now, the in-memory cache + env var fallback remains for backward compatibility.
def _get_hec_token() -> str:
    """Return the expected HEC token.

    Priority: in-memory cache (set by admin UI / startup) → env var.
    """
    if _cached_hec_token:
        return _cached_hec_token
    return os.environ.get("HEC_TOKEN", "")


def _verify_splunk_auth(auth_header: str, expected_token: str) -> bool:
    """Validate ``Authorization: Splunk <token>`` header."""
    if not auth_header.startswith("Splunk "):
        return False
    provided = auth_header[7:]  # strip "Splunk " prefix
    import hmac

    return hmac.compare_digest(provided, expected_token)


@router.post(
    "/collector",
    status_code=status.HTTP_200_OK,
    response_class=JSONResponse,
)
@router.post(
    "/collector/event",
    status_code=status.HTTP_200_OK,
    response_class=JSONResponse,
    include_in_schema=False,
)
@router.post(
    "/collector/event/1.0",
    status_code=status.HTTP_200_OK,
    response_class=JSONResponse,
    include_in_schema=False,
)
async def receive_hec_event(request: Request) -> JSONResponse:
    """Receive Splunk HEC events from GitHub audit log streaming.

    GitHub sends one or more JSON events.  The HEC protocol supports:
      - A single JSON object per request
      - Multiple JSON objects concatenated (no delimiter)
      - Newline-delimited JSON (NDJSON)

    Each HEC event wraps the actual payload in ``{"event": {...}}``.
    """
    # 1. Verify token — mandatory. Reject all traffic if no token is configured.
    token = _get_hec_token()
    if not token:
        logger.error(
            "hec.no_token_configured",
            detail="HEC_TOKEN is not set. Configure it via the admin UI or HEC_TOKEN env var.",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HEC endpoint is not configured — contact the administrator",
        )

    auth = request.headers.get("Authorization", "")
    if not _verify_splunk_auth(auth, token):
        logger.warning("hec.auth_failed", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HEC token",
        )

    # 2. Read body and enforce size limit (5 MB uncompressed)
    body = await request.body()
    if not body:
        # Empty body with valid auth = connectivity health check (GitHub sends
        # these before resuming paused audit log streaming). Return success.
        logger.debug("hec.empty_body_health_check")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"text": "Success", "code": 0},
        )

    max_body_bytes = 5 * 1024 * 1024  # 5 MB
    if len(body) > max_body_bytes:
        logger.warning("hec.body_too_large", size=len(body), max=max_body_bytes)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Request body exceeds {max_body_bytes // (1024 * 1024)} MB limit",
        )

    # 3. Parse HEC payload(s)
    # GitHub may send a single JSON object or concatenated/NDJSON objects
    events = _parse_hec_body(body)
    if not events:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"text": "Success", "code": 0},
        )

    # 4. Cap events per request to prevent downstream amplification
    max_events = 1000
    if len(events) > max_events:
        logger.warning("hec.too_many_events", count=len(events), max=max_events)
        events = events[:max_events]

    # 5. Batch-enqueue events for ingestion
    enqueued = 0
    try:
        from app.workers.ingest_webhook_worker import ingest_webhook_event_task

        for event in events:
            ingest_webhook_event_task.delay(event)
            enqueued += 1
    except Exception as exc:
        logger.error("hec.enqueue_failed", error=str(exc), enqueued=enqueued)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue events",
        ) from exc

    logger.info("hec.accepted", events=enqueued)

    # Splunk HEC success response format
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"text": "Success", "code": 0},
    )


@router.get(
    "/collector/health",
    status_code=status.HTTP_200_OK,
    response_class=JSONResponse,
)
@router.get(
    "/collector/health/1.0",
    status_code=status.HTTP_200_OK,
    response_class=JSONResponse,
    include_in_schema=False,
)
async def hec_health() -> JSONResponse:
    """Health check for HEC endpoint. GitHub hits this to verify connectivity."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"text": "HEC is healthy", "code": 17},  # Splunk HEC health code
    )


def _parse_hec_body(body: bytes) -> list[dict[str, Any]]:
    """Parse HEC request body into a list of normalized audit log events.

    Handles:
      - Single JSON object: ``{"event": {...}}``
      - NDJSON: one ``{"event": {...}}`` per line
      - Concatenated JSON: ``{"event": {...}}{"event": {...}}``
      - Mixed: some lines NDJSON, some lines concatenated
    """
    text = body.decode("utf-8").strip()
    raw_objects: list[dict[str, Any]] = []

    # Try single JSON object first (covers single-event requests)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            raw_objects.append(obj)
        elif isinstance(obj, list):
            raw_objects.extend(obj)
        return _extract_events(raw_objects)
    except json.JSONDecodeError:
        pass

    # Process line-by-line; each line may be a single JSON object or
    # concatenated objects (e.g. ``{...}{...}``).
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Try the line as a single JSON object first (fast path)
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                raw_objects.append(obj)
            continue
        except json.JSONDecodeError:
            pass

        # If that fails, try splitting concatenated JSON on ``}{``
        if "}{" in line:
            parts = line.replace("}{", "}\n{").split("\n")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                try:
                    obj = json.loads(part)
                    if isinstance(obj, dict):
                        raw_objects.append(obj)
                except json.JSONDecodeError:
                    logger.warning("hec.parse_skip_part", part=part[:100])
        else:
            logger.warning("hec.parse_skip_line", line=line[:100])

    return _extract_events(raw_objects)


def _extract_events(hec_objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unwrap HEC envelopes and normalize into audit-log-format dicts.

    GitHub HEC streaming wraps audit log events as::

        {
            "time": 1705329600,
            "host": "github.com",
            "source": "audit_log",
            "event": { <actual audit log event> }
        }
    """
    events: list[dict[str, Any]] = []
    for obj in hec_objects:
        # Unwrap HEC envelope — the actual event is in "event"
        payload = obj.get("event", obj)
        if not isinstance(payload, dict):
            continue

        # GitHub audit log events must have an "action" field
        if "action" not in payload:
            logger.debug("hec.skip_no_action", keys=list(payload.keys())[:10])
            continue

        # Pass through as-is — the ingestion pipeline handles normalization
        events.append(payload)

    return events
