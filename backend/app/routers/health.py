"""Health check endpoints: liveness and readiness probes.

These endpoints are intentionally unauthenticated so that Kubernetes
(and other orchestrators) can call them without credentials.  The
liveness probe reveals no sensitive information; the readiness probe
only exposes aggregate ok/error status for DB and Valkey connectivity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_valkey

router = APIRouter(tags=["health"])


@router.get("/health", response_model=dict)
async def liveness() -> dict:
    """Kubernetes liveness probe — returns 200 if the process is alive."""
    return {"status": "ok"}


@router.get("/ready", response_model=dict)
async def readiness(
    response: Response,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> dict:
    """Kubernetes readiness probe — checks DB and Valkey connectivity."""
    checks: dict[str, str] = {}

    # Database check
    try:
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Valkey check
    try:
        await valkey.ping()
        checks["valkey"] = "ok"
    except Exception:
        checks["valkey"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    if not all_ok:
        response.status_code = 503
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }
