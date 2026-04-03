"""GitHub IP allowlist middleware.

Restricts configurable path prefixes to traffic originating from GitHub's
published IP ranges.  When the allowlist is not loaded (e.g. on first boot
before the Celery refresh has run) the middleware fails open so that
legitimate traffic is not blocked during initial deployment.
"""

from __future__ import annotations

from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services.github_ip_allowlist import GitHubIPAllowlist
from app.utils.client_ip import get_client_ip

logger = structlog.get_logger(__name__)


class GitHubIPAllowlistMiddleware(BaseHTTPMiddleware):
    """Restrict specific path prefixes to GitHub's published IP ranges."""

    def __init__(self, app: Any, protected_prefixes: list[str] | None = None) -> None:
        super().__init__(app)
        # Paths that require GitHub IP verification
        self.protected_prefixes: list[str] = protected_prefixes or [
            "/api/v1/ingest/webhook",
            "/api/v1/admin/audit-stream",
        ]

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Filter requests to protected paths by client IP."""
        path = request.url.path

        # Only filter requests to protected paths
        if not any(path.startswith(prefix) for prefix in self.protected_prefixes):
            response: Response = await call_next(request)
            return response

        # Extract client IP using trusted-proxy-aware utility
        client_ip = get_client_ip(request) or ""

        if not client_ip or not GitHubIPAllowlist.is_allowed(client_ip):
            logger.warning(
                "github_ip_allowlist.blocked",
                ip=client_ip,
                path=path,
                method=request.method,
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Request origin not in GitHub IP allowlist"},
            )

        response = await call_next(request)
        return response
