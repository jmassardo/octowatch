"""FastAPI application factory with all middleware, routers, and lifespan events."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import dispose_pool, warm_up_pool
from app.middleware.maintenance import MaintenanceModeMiddleware
from app.rate_limit import limiter
from app.routers import (
    actors,
    admin,
    admin_audit_log,
    admin_auth,
    admin_retention,
    admin_roles,
    admin_settings,
    admin_teams,
    auth,
    copilot,
    copilot_governance,
    correlations,
    cross_org,
    detections,
    dev_activity,
    enterprise_pat,
    events,
    features,
    health,
    health_signals,
    ingest_hec,
    ingest_webhook,
    integrations,
    maintenance,
    notifications,
    org_config,
    pagerduty,
    playbooks,
    posture,
    query,
    reports,
    rule_library,
    rules,
    secret_scanning,
    setup,
    slack,
    suggestions,
    supply_chain,
    sync,
    teams,
    threat_intel,
    user_preferences,
    workflow_metrics,
    workflow_scanner,
)
from app.services.geoip_service import close_geoip_db, load_geoip_db
from app.services.secret_provider import create_secret_provider
from app.utils.client_ip import get_client_ip

logger = structlog.get_logger(__name__)


# ─── Rate limiter ───────────────────────────────────────────────────────────────
# The shared limiter instance lives in app.rate_limit to avoid circular imports
# between main.py and routers. Re-exported here for backward compatibility.


# ─── Custom middleware ──────────────────────────────────────────────────────────


class MetricsIPRestrictionMiddleware(BaseHTTPMiddleware):
    """Restrict /metrics endpoint to localhost and internal pod network in production."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path == "/metrics":
            from app.config import settings

            if settings.ENVIRONMENT in ("production", "staging"):
                client_host = request.client.host if request.client else ""
                allowed = (
                    client_host in ("127.0.0.1", "::1")
                    or client_host.startswith("10.")
                    or client_host.startswith("172.16.")
                    or client_host.startswith("192.168.")
                )
                if not allowed:
                    return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        return await call_next(request)


class CsrfEchoMiddleware(BaseHTTPMiddleware):
    """Echo the csrf_token cookie value as the X-CSRF-Token response header.

    The frontend captures this header on every response so it always has a
    fresh CSRF token to use on state-changing requests (double-submit pattern).
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        csrf_token = request.cookies.get("csrf_token")
        if csrf_token:
            response.headers["X-CSRF-Token"] = csrf_token
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-recommended security headers to every response."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response


class AuditTrailMiddleware(BaseHTTPMiddleware):
    """Log all mutating requests (POST/PUT/PATCH/DELETE) to audit_trail table."""

    _MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start_time = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        if request.method in self._MUTATION_METHODS:
            actor = None
            try:
                # Extract actor from JWT cookie without full dep injection
                from app.deps import _extract_jwt_payload

                payload = _extract_jwt_payload(request)
                actor = payload.get("sub") if payload else None
            except Exception:  # best-effort; must not block audit trail logging
                logger.debug("audit_trail.actor_extract_failed")

            logger.info(
                "audit_trail.request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                actor=actor,
                elapsed_ms=elapsed_ms,
                client_ip=get_client_ip(request),
            )

            # Async DB write is done in background to avoid blocking the response
            if actor and request.app.state.db_pool_ready:
                try:
                    from app.database import AsyncSessionLocal
                    from app.models.audit_trail import AuditTrail

                    is_error = response.status_code >= 400
                    async with AsyncSessionLocal() as db_session:
                        trail = AuditTrail(
                            user_login=actor,
                            action_type=(
                                f"api.{request.method.lower()}"
                                f".{request.url.path.replace('/', '_').strip('_')}"
                            ),
                            resource_type="api_endpoint",
                            resource_id=None,
                            ip_address=get_client_ip(request),
                            user_agent=request.headers.get("user-agent"),
                            outcome="error" if is_error else "success",
                            error_detail=(f"HTTP {response.status_code}" if is_error else None),
                            parameters={
                                "method": request.method,
                                "path": request.url.path,
                                "status_code": response.status_code,
                                "elapsed_ms": elapsed_ms,
                            },
                        )
                        db_session.add(trail)
                        await db_session.commit()
                except Exception as exc:
                    logger.warning("audit_trail.write_failed", error=str(exc))

        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to each request for correlation."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        import uuid

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.unbind_contextvars("request_id")
        return response


# ─── Lifespan ───────────────────────────────────────────────────────────────────


async def _retry_hec_token_load() -> None:
    """Background task: retry loading HEC token with exponential backoff.

    Tries Key Vault first, then falls back to DB. This handles the case where
    PostgreSQL starts after the API pod. Retries up to 10 times (total ~8.5
    minutes of waiting) before giving up.
    """
    import asyncio

    max_retries = 10
    base_delay = 5.0  # seconds

    for attempt in range(1, max_retries + 1):
        delay = base_delay * (2 ** (attempt - 1))  # 5, 10, 20, 40, ...
        delay = min(delay, 60.0)  # cap at 60s
        await asyncio.sleep(delay)

        try:
            from app.routers.ingest_hec import set_hec_token_cache

            # Try Key Vault first
            if hasattr(app, "state") and hasattr(app.state, "secret_provider"):
                try:
                    token = await app.state.secret_provider.get_secret("octowatch--hec--token")
                    if token:
                        set_hec_token_cache(token)
                        logger.info(
                            "hec.token_loaded_from_kv_retry",
                            attempt=attempt,
                        )
                        return
                except Exception as exc:
                    logger.debug("hec.token_kv_retry_failed", attempt=attempt, error=str(exc))

            # Fall back to DB
            from app.database import AsyncSessionLocal
            from app.services.settings_service import get_setting

            async with AsyncSessionLocal() as db_session:
                db_hec_token = await get_setting(db_session, "hec_token")
                if db_hec_token:
                    set_hec_token_cache(db_hec_token)
                    logger.info(
                        "hec.token_loaded_from_db_retry",
                        attempt=attempt,
                    )
                    return
                else:
                    logger.debug(
                        "hec.token_retry_no_token",
                        attempt=attempt,
                    )
        except Exception as exc:
            logger.debug(
                "hec.token_retry_failed",
                attempt=attempt,
                error=str(exc),
            )

    logger.error(
        "hec.token_retry_exhausted",
        message="Failed to load HEC token after all retries. Manual pod restart required.",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown events."""
    logger.info("app.startup", environment=settings.environment)

    # Mark pool as not ready initially
    app.state.db_pool_ready = False

    # 1. Warm up database connection pool
    try:
        await warm_up_pool()
        app.state.db_pool_ready = True
        logger.info("app.db_pool_warmed_up")
    except Exception as exc:
        logger.error("app.db_pool_failed", error=str(exc))

    # 1.5. Initialize secret provider
    try:
        app.state.secret_provider = create_secret_provider()
        logger.info("app.secret_provider_initialized")
    except Exception as exc:
        logger.error("app.secret_provider_failed", error=str(exc))
        # Fall back to env provider if KV provider fails to initialize
        from app.services.env_provider import EnvVarProvider

        app.state.secret_provider = EnvVarProvider()
        logger.warning("app.secret_provider_fallback_to_env")

    # 2. Log auth config
    logger.info(
        "auth.config",
        jwt_ttl_seconds=settings.JWT_TTL_SECONDS,
    )

    # 3. Warm up Valkey pool
    try:
        from app.deps import _get_valkey_pool

        pool = _get_valkey_pool()
        import redis.asyncio as redis_client

        r = redis_client.Redis(connection_pool=pool)
        await r.ping()
        logger.info("app.valkey_connected")

        # Load GitHub IP allowlist from Valkey cache on startup
        if settings.github_app.GITHUB_IP_ALLOWLIST_ENABLED:
            try:
                from app.services.github_ip_allowlist import GitHubIPAllowlist

                loaded = await GitHubIPAllowlist.load_from_cache(r)
                if not loaded:
                    await GitHubIPAllowlist.refresh(r)
                logger.info(
                    "github_ip_allowlist.startup",
                    loaded=GitHubIPAllowlist.is_loaded(),
                    network_count=GitHubIPAllowlist.network_count(),
                )
            except Exception as exc:
                logger.warning("github_ip_allowlist.startup_failed", error=str(exc))

    except Exception as exc:
        logger.error("app.valkey_failed", error=str(exc))

    # 4. Load GeoIP database (non-fatal)
    try:
        await load_geoip_db()
        logger.info("app.geoip_loaded")
    except Exception as exc:
        logger.warning("app.geoip_unavailable", error=str(exc))

    # 5. Load settings overlay from DB + generate setup token on first boot
    if app.state.db_pool_ready:
        try:
            from app.database import AsyncSessionLocal
            from app.services.config_overlay import load_settings_overlay
            from app.services.settings_service import (
                generate_setup_token,
                is_setup_complete,
            )

            async with AsyncSessionLocal() as db_session:
                # Load DB-backed settings overlay (with KV-first for secrets)
                count = await load_settings_overlay(
                    db_session, secret_provider=app.state.secret_provider
                )
                logger.info("settings_overlay.loaded", count=count)

                # Load HEC token — try Key Vault first, then fall back to DB
                from app.services.settings_service import get_setting

                hec_token: str | None = None
                if hasattr(app.state, "secret_provider"):
                    try:
                        hec_token = await app.state.secret_provider.get_secret(
                            "octowatch--hec--token"
                        )
                    except Exception as exc:
                        logger.debug("hec.kv_load_failed_at_startup", error=str(exc))

                if not hec_token:
                    hec_token = await get_setting(db_session, "hec_token")

                if hec_token:
                    from app.routers.ingest_hec import set_hec_token_cache

                    set_hec_token_cache(hec_token)
                    logger.info("hec.token_loaded")
                else:
                    logger.warning("hec.token_not_found_at_startup")

                # Generate setup token on first boot if setup is not complete
                if not await is_setup_complete(db_session):
                    token = await generate_setup_token(db_session)
                    await db_session.commit()
                    masked = token[:4] + "****" + token[-4:] if len(token) > 8 else "****"
                    logger.info(
                        "setup.token_generated",
                        message=(
                            f"\U0001f511 Setup token generated ({masked}) — "
                            "retrieve it from the setup endpoint or container logs at startup only"
                        ),
                    )
                    import sys

                    sys.stderr.write(  # noqa: T201
                        f"\n{'=' * 60}\n"
                        f"  SETUP TOKEN: {token}\n"
                        f"  Use this to complete initial setup at /setup\n"
                        f"{'=' * 60}\n\n"
                    )
                    sys.stderr.flush()
                else:
                    logger.info("setup.already_complete")
        except Exception as exc:
            logger.warning("settings_overlay.load_failed", error=str(exc))
            # Schedule background retry for HEC token loading
            import asyncio

            asyncio.create_task(_retry_hec_token_load())
    else:
        # DB not ready at startup — schedule background retry
        import asyncio

        asyncio.create_task(_retry_hec_token_load())

    yield

    # Shutdown
    logger.info("app.shutdown")
    # Close secret provider
    if hasattr(app.state, "secret_provider"):
        await app.state.secret_provider.close()
    await close_geoip_db()
    await dispose_pool()


# ─── Application factory ────────────────────────────────────────────────────────


def _status_to_code(status_code: int) -> str:
    """Map HTTP status codes to error code strings."""
    mapping = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        503: "service_unavailable",
    }
    return mapping.get(status_code, f"error_{status_code}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    openapi_tags = [
        {
            "name": "auth",
            "description": "Authentication and session management — login, logout, OAuth flows.",
        },
        {
            "name": "events",
            "description": "Audit event ingestion, search, and retrieval.",
        },
        {
            "name": "detections",
            "description": "Threat detection alerts — list, update status, assign.",
        },
        {
            "name": "rules",
            "description": "Detection rule CRUD — create, update, version, test, and manage.",
        },
        {
            "name": "rule-library",
            "description": "Pre-built detection rule templates — browse, enable, and customize.",
        },
        {
            "name": "health-signals",
            "description": "Organization health signals — PAT hygiene, stale repos, compliance.",
        },
        {
            "name": "posture",
            "description": "Security posture assessment and scoring.",
        },
        {
            "name": "reports",
            "description": "Compliance and executive reporting.",
        },
        {
            "name": "query",
            "description": "Ad-hoc SQL query explorer for audit data.",
        },
        {
            "name": "integrations",
            "description": "Third-party integrations — Slack, Jira, PagerDuty, SIEM.",
        },
        {
            "name": "admin",
            "description": "System administration — user management, org config.",
        },
        {
            "name": "copilot",
            "description": "GitHub Copilot usage analytics and policy management.",
        },
        {
            "name": "sync",
            "description": "GitHub data synchronization — entities, events, status.",
        },
        {
            "name": "setup",
            "description": "Initial setup wizard — authentication, sync, TLS.",
        },
        {
            "name": "health",
            "description": "Application health and readiness probes.",
        },
    ]

    app = FastAPI(
        title="OctoWatch API",
        description=(
            "GitHub Enterprise audit log security analytics platform.\n\n"
            "OctoWatch ingests GitHub audit logs, detects threats using configurable rules, "
            "and provides security posture dashboards for enterprise organizations.\n\n"
            "## Authentication\n"
            "All endpoints (except `/health`, `/ready`) require authentication via HTTP-only "
            "JWT cookie. Use the `/api/v1/auth/login` endpoint to authenticate.\n\n"
            "## Rate Limiting\n"
            "API requests are rate-limited per user. Check `X-RateLimit-*` response headers.\n\n"
            "## CSRF Protection\n"
            "State-changing requests (POST/PUT/PATCH/DELETE) require the `X-CSRF-Token` header "
            "matching the `csrf_token` cookie (double-submit pattern)."
        ),
        version="1.0.0",
        contact={
            "name": "OctoWatch Team",
            "url": "https://github.com/octowatch/octowatch",
        },
        license_info={
            "name": "Apache 2.0",
            "url": "https://www.apache.org/licenses/LICENSE-2.0",
        },
        openapi_tags=openapi_tags,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # ── Prometheus metrics instrumentation ──────────────────────────────────
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/ready", "/metrics"],
    )
    instrumentator.instrument(app)
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)

    # Record static application info as a Prometheus metric
    from app.services.metrics_service import set_app_info

    set_app_info(version="1.0.0", environment=settings.environment)

    # ── Middleware stack (applied bottom-up, executes top-down) ──────────────
    # NOTE: HTTPS redirect is handled by the ingress controller
    # (nginx.ingress.kubernetes.io/ssl-redirect: "true"). Applying it at the
    # app level breaks internal HTTP health probes from the kubelet.

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["X-CSRF-Token", "Content-Type", "Authorization"],
    )

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # CSRF token echo (sets X-CSRF-Token response header from cookie for frontend capture)
    app.add_middleware(CsrfEchoMiddleware)

    # Audit trail
    app.add_middleware(AuditTrailMiddleware)

    # Maintenance mode controls
    app.add_middleware(MaintenanceModeMiddleware)

    # GitHub IP allowlist (only when enabled)
    if settings.github_app.GITHUB_IP_ALLOWLIST_ENABLED:
        from app.middleware.ip_allowlist import GitHubIPAllowlistMiddleware

        app.add_middleware(GitHubIPAllowlistMiddleware)

    # Request ID correlation
    app.add_middleware(RequestIdMiddleware)

    # Metrics endpoint IP restriction
    app.add_middleware(MetricsIPRestrictionMiddleware)

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── Exception handlers ────────────────────────────────────────────────────

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unhandled exceptions. Never leak stack traces."""
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "unhandled_exception",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred. Please try again later.",
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Format validation errors consistently."""
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": [
                        {
                            "field": ".".join(str(loc) for loc in err.get("loc", [])),
                            "message": err.get("msg", ""),
                            "type": err.get("type", ""),
                        }
                        for err in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(FastAPIHTTPException)
    async def http_exception_handler(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
        """Wrap HTTP exceptions in consistent error envelope."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": _status_to_code(exc.status_code),
                    "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                }
            },
            headers=getattr(exc, "headers", None),
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    API_PREFIX = "/api/v1"

    app.include_router(health.router)  # /health, /ready (no prefix for k8s probes)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(events.router, prefix=API_PREFIX)
    app.include_router(detections.router, prefix=API_PREFIX)
    app.include_router(correlations.router, prefix=API_PREFIX)
    app.include_router(posture.router, prefix=API_PREFIX)
    app.include_router(reports.router, prefix=API_PREFIX)
    app.include_router(query.router, prefix=API_PREFIX)
    app.include_router(rules.router, prefix=API_PREFIX)
    app.include_router(rule_library.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(admin_retention.router, prefix=API_PREFIX)
    app.include_router(admin_roles.router, prefix=API_PREFIX)
    app.include_router(admin_teams.router, prefix=API_PREFIX)
    app.include_router(admin_audit_log.router, prefix=API_PREFIX)
    app.include_router(admin_settings.router, prefix=API_PREFIX)
    app.include_router(maintenance.router, prefix=API_PREFIX)
    app.include_router(admin_auth.router, prefix=API_PREFIX)
    app.include_router(enterprise_pat.router, prefix=API_PREFIX)
    app.include_router(integrations.router, prefix=API_PREFIX)
    app.include_router(slack.router, prefix=API_PREFIX)
    app.include_router(notifications.router, prefix=API_PREFIX)
    app.include_router(pagerduty.router, prefix=API_PREFIX)
    app.include_router(health_signals.router, prefix=API_PREFIX)
    app.include_router(copilot.router, prefix=API_PREFIX)
    app.include_router(features.router, prefix=API_PREFIX)
    app.include_router(org_config.router, prefix=API_PREFIX)
    app.include_router(sync.router, prefix=API_PREFIX + "/admin")
    app.include_router(secret_scanning.router, prefix=API_PREFIX)
    app.include_router(setup.router, prefix=API_PREFIX)
    app.include_router(suggestions.router, prefix=API_PREFIX)
    app.include_router(supply_chain.router, prefix=API_PREFIX)
    app.include_router(teams.router, prefix=API_PREFIX)
    app.include_router(dev_activity.router, prefix=API_PREFIX)
    app.include_router(threat_intel.router, prefix=API_PREFIX)
    app.include_router(actors.router, prefix=API_PREFIX)
    app.include_router(ingest_webhook.router, prefix=API_PREFIX)
    app.include_router(ingest_hec.router)  # No prefix — GitHub expects /services/collector
    app.include_router(cross_org.router, prefix=API_PREFIX)
    app.include_router(playbooks.router, prefix=API_PREFIX)
    app.include_router(workflow_scanner.router, prefix=API_PREFIX)
    app.include_router(workflow_metrics.router, prefix=API_PREFIX)
    app.include_router(copilot_governance.router, prefix=API_PREFIX)
    app.include_router(user_preferences.router, prefix=API_PREFIX)

    return app


app = create_app()
