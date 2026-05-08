"""Maintenance mode middleware."""

from __future__ import annotations

import json
from typing import Any

import jwt as pyjwt
import redis.asyncio as redis_client
import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.deps import get_valkey_pool
from app.services.maintenance_service import MaintenanceStatus, get_maintenance_status

logger = structlog.get_logger(__name__)

_EXEMPT_PATH_PREFIXES = (
    "/health",
    "/ready",
    "/api/v1/auth/",
    "/api/v1/admin/maintenance",
)
_EXEMPT_PATHS = {"/health", "/ready"}
_BLOCKED_METHODS = frozenset({"POST", "PUT", "DELETE"})
_ADMIN_ROLES = frozenset({"admin", "sys_admin", "super_admin"})


async def _get_active_maintenance_status(request: Request) -> MaintenanceStatus | None:
    """Fetch the current maintenance mode state when the DB pool is available."""

    if not getattr(request.app.state, "db_pool_ready", False):
        return None

    try:
        async with AsyncSessionLocal() as db_session:
            status = await get_maintenance_status(db_session)
    except Exception as exc:
        logger.warning("maintenance.status_lookup_failed", error=str(exc), path=request.url.path)
        return None

    if not status.enabled:
        return None
    return status


async def _is_admin_request(request: Request) -> bool:
    """Best-effort check for admin users based on the authenticated session."""

    token = request.cookies.get("access_token")
    if not token:
        return False

    try:
        payload = pyjwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
    except pyjwt.InvalidTokenError:
        return False

    jti = payload.get("jti")
    if not jti:
        return False

    valkey = redis_client.Redis(connection_pool=get_valkey_pool())
    try:
        session_data_raw = await valkey.get(f"session:{jti}")
    except Exception as exc:
        logger.warning("maintenance.valkey_lookup_failed", error=str(exc))
        return False
    finally:
        await valkey.aclose()

    if not session_data_raw:
        return False

    try:
        session_data: dict[str, Any] = json.loads(session_data_raw)
    except json.JSONDecodeError:
        logger.warning("maintenance.invalid_session_payload")
        return False

    roles = session_data.get("roles", []) or []
    return any(role in _ADMIN_ROLES for role in roles)


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    """Add maintenance headers and optionally block writes for non-admin users."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        status = await _get_active_maintenance_status(request)
        if status is None:
            return await call_next(request)

        is_exempt = request.url.path in _EXEMPT_PATHS or request.url.path.startswith(
            _EXEMPT_PATH_PREFIXES,
        )
        if (
            status.block_writes
            and request.method in _BLOCKED_METHODS
            and not is_exempt
            and not await _is_admin_request(request)
        ):
            logger.info(
                "maintenance.write_blocked",
                path=request.url.path,
                method=request.method,
                severity=status.severity,
            )
            response = JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "service_unavailable",
                        "message": (
                            "Write operations are temporarily disabled while maintenance is active."
                        ),
                    }
                },
            )
            response.headers["X-Maintenance-Mode"] = "true"
            return response

        response = await call_next(request)
        response.headers["X-Maintenance-Mode"] = "true"
        return response
