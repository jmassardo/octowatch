"""Integration tests for the health router.

Tests cover:
- /health (liveness probe) → always 200
- /ready (readiness probe) → 200 "ready" when deps healthy
- /ready → 200 "degraded" when DB or Valkey unavailable
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_valkey
from app.routers import health as health_router_module

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_health_app(
    db_healthy: bool = True,
    valkey_healthy: bool = True,
    setup_complete: bool = False,
) -> FastAPI:
    app = FastAPI()
    app.include_router(health_router_module.router)

    # DB mock
    mock_db = AsyncMock(spec=AsyncSession)
    if db_healthy:
        mock_db.execute = AsyncMock(return_value=MagicMock())
    else:
        mock_db.execute = AsyncMock(side_effect=Exception("DB connection refused"))

    # Valkey mock
    mock_valkey = AsyncMock()
    if valkey_healthy:
        mock_valkey.ping = AsyncMock(return_value=True)
    else:
        mock_valkey.ping = AsyncMock(side_effect=Exception("Valkey connection refused"))

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app


# ─── Liveness ─────────────────────────────────────────────────────────────────


class TestLiveness:
    def test_health_returns_200(self):
        app = FastAPI()
        app.include_router(health_router_module.router)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self):
        app = FastAPI()
        app.include_router(health_router_module.router)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.json()["status"] == "ok"

    def test_health_does_not_require_auth(self):
        """Liveness probe must always be accessible, no auth required."""
        app = FastAPI()
        app.include_router(health_router_module.router)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200


# ─── Readiness ────────────────────────────────────────────────────────────────


class TestReadiness:
    @patch(
        "app.services.settings_service.is_setup_complete",
        new_callable=AsyncMock,
        return_value=False,
    )
    def test_ready_returns_200_when_both_healthy(self, _mock_setup):
        app = _build_health_app(db_healthy=True, valkey_healthy=True)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/ready")
        assert resp.status_code == 200

    @patch(
        "app.services.settings_service.is_setup_complete",
        new_callable=AsyncMock,
        return_value=False,
    )
    def test_ready_status_is_ready_when_healthy(self, _mock_setup):
        app = _build_health_app(db_healthy=True, valkey_healthy=True)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/ready")
        data = resp.json()
        assert data["status"] == "ready"

    @patch(
        "app.services.settings_service.is_setup_complete",
        new_callable=AsyncMock,
        return_value=False,
    )
    def test_ready_checks_database(self, _mock_setup):
        app = _build_health_app(db_healthy=True, valkey_healthy=True)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/ready")
        data = resp.json()
        assert "checks" in data
        assert data["checks"]["database"] == "ok"

    @patch(
        "app.services.settings_service.is_setup_complete",
        new_callable=AsyncMock,
        return_value=False,
    )
    def test_ready_checks_valkey(self, _mock_setup):
        app = _build_health_app(db_healthy=True, valkey_healthy=True)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/ready")
        data = resp.json()
        assert "checks" in data
        assert data["checks"]["valkey"] == "ok"

    @patch(
        "app.services.settings_service.is_setup_complete",
        new_callable=AsyncMock,
        return_value=False,
    )
    def test_ready_degraded_when_db_down(self, _mock_setup):
        """When DB fails, readiness probe returns 503 with degraded status."""
        app = _build_health_app(db_healthy=False, valkey_healthy=True)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ready")
        # HTTP 503 so Kubernetes stops routing traffic to this pod
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert "error" in data["checks"]["database"]

    @patch(
        "app.services.settings_service.is_setup_complete",
        new_callable=AsyncMock,
        return_value=False,
    )
    def test_ready_degraded_when_valkey_down(self, _mock_setup):
        """When Valkey fails, readiness probe returns 503 with degraded status."""
        app = _build_health_app(db_healthy=True, valkey_healthy=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ready")
        # HTTP 503 so Kubernetes stops routing traffic to this pod
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert "error" in data["checks"]["valkey"]

    @patch(
        "app.services.settings_service.is_setup_complete",
        new_callable=AsyncMock,
        return_value=False,
    )
    def test_ready_degraded_when_both_down(self, _mock_setup):
        """When both deps fail, both check entries report errors."""
        app = _build_health_app(db_healthy=False, valkey_healthy=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ready")
        data = resp.json()
        assert data["status"] == "degraded"
        assert "error" in data["checks"]["database"]
        assert "error" in data["checks"]["valkey"]

    @patch(
        "app.services.settings_service.is_setup_complete",
        new_callable=AsyncMock,
        return_value=False,
    )
    def test_ready_does_not_require_auth(self, _mock_setup):
        """Readiness probe must be accessible without authentication."""
        app = _build_health_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/ready")
        assert resp.status_code == 200
