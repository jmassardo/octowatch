"""FastAPI application factory with all middleware, routers, and lifespan events."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.database import dispose_pool, warm_up_pool
from app.routers import admin, auth, detections, events, health, integrations, query, reports, rules
from app.services.geoip_service import close_geoip_db, load_geoip_db

logger = structlog.get_logger(__name__)


# ─── Rate limiter ───────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ─── Custom middleware ──────────────────────────────────────────────────────────


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
                client_ip=request.client.host if request.client else None,
            )

            # Async DB write is done in background to avoid blocking the response
            if actor and request.app.state.db_pool_ready:
                try:
                    from app.database import AsyncSessionLocal
                    from app.models.audit_trail import AuditTrail

                    async with AsyncSessionLocal() as db_session:
                        trail = AuditTrail(
                            actor=actor,
                            action=(
                                f"api.{request.method.lower()}"
                                f".{request.url.path.replace('/', '_').strip('_')}"
                            ),
                            resource_type="api_endpoint",
                            resource_id=None,
                            ip_address=request.client.host if request.client else None,
                            request_method=request.method,
                            request_path=request.url.path,
                            response_status=response.status_code,
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
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.unbind_contextvars("request_id")
        return response


# ─── Lifespan ───────────────────────────────────────────────────────────────────


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

    # 2. Warm up Valkey pool
    try:
        from app.deps import _get_valkey_pool

        pool = _get_valkey_pool()
        import redis.asyncio as redis_client

        r = redis_client.Redis(connection_pool=pool)
        await r.ping()
        logger.info("app.valkey_connected")
    except Exception as exc:
        logger.error("app.valkey_failed", error=str(exc))

    # 3. Load GeoIP database (non-fatal)
    try:
        await load_geoip_db()
        logger.info("app.geoip_loaded")
    except Exception as exc:
        logger.warning("app.geoip_unavailable", error=str(exc))

    yield

    # Shutdown
    logger.info("app.shutdown")
    await close_geoip_db()
    await dispose_pool()


# ─── Application factory ────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Audit Log Analyzer",
        description="GitHub enterprise audit log analysis platform",
        version="1.0.0",
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url="/api/redoc" if settings.environment != "production" else None,
        openapi_url="/api/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )

    # ── Middleware stack (applied bottom-up, executes top-down) ──────────────
    # HTTPS redirect (disable in development to allow HTTP)
    if settings.environment == "production":
        app.add_middleware(HTTPSRedirectMiddleware)

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

    # Audit trail
    app.add_middleware(AuditTrailMiddleware)

    # Request ID correlation
    app.add_middleware(RequestIdMiddleware)

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────────
    API_PREFIX = "/api/v1"

    app.include_router(health.router)  # /health, /ready (no prefix for k8s probes)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(events.router, prefix=API_PREFIX)
    app.include_router(detections.router, prefix=API_PREFIX)
    app.include_router(reports.router, prefix=API_PREFIX)
    app.include_router(query.router, prefix=API_PREFIX)
    app.include_router(rules.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(integrations.router, prefix=API_PREFIX)

    return app


app = create_app()
