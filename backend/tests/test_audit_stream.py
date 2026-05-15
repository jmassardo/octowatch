"""Tests for audit log streaming configuration (HEC-based).

Covers:
- GET /admin/audit-stream/config endpoint (HEC config)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_valkey
from app.routers import admin as admin_router_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helper Functions ─────────────────────────────────────────────────────────


def _make_jwt(sub: str = "admin", jti: str = "audit-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 99999,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_admin_session() -> str:
    return json.dumps(
        {
            "github_login": "admin",
            "github_id": 99999,
            "roles": ["sys_admin"],
            "scoped_orgs": [],
            "scoped_repos": [],
            "scope_type": "global",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_analyst_session() -> str:
    return json.dumps(
        {
            "github_login": "analyst",
            "github_id": 11111,
            "roles": ["analyst"],
            "scoped_orgs": ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db() -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar_one.return_value = 0
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _build_admin_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(admin_router_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)
    mock_valkey.ping = AsyncMock(return_value=True)
    mock_valkey.aclose = AsyncMock()

    async def override_db() -> AsyncSession:  # type: ignore[misc]
        yield mock_db  # type: ignore[misc]

    async def override_valkey() -> AsyncMock:  # type: ignore[misc]
        yield mock_valkey  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Admin Router Auth Tests ──────────────────────────────────────────────────


class TestAdminAuditStreamAuth:
    """Verify that the admin audit-stream config endpoint requires sys_admin role."""

    def test_get_config_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_admin_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 401

    def test_get_config_non_admin_returns_403(self) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_analyst_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(sub="analyst", jti="analyst-jti")
        client.cookies.set("access_token", token)
        client.cookies.set("csrf_token", "tok")
        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 403


# ─── GET /admin/audit-stream/config Tests ────────────────────────────────────


class TestGetAuditStreamConfig:
    """Tests for GET /admin/audit-stream/config endpoint (HEC mode)."""

    @patch("app.routers.admin.settings")
    @patch("app.routers.admin.get_setting", new_callable=AsyncMock)
    def test_returns_configured_when_hec_token_set(
        self,
        mock_get_setting: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.AUTH.APP_BASE_URL = "https://octowatch.example.com"
        mock_get_setting.return_value = "my-hec-token"

        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)
        client.cookies.set("csrf_token", "tok")

        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["hec_configured"] is True
        assert "hec_endpoint" in data
        assert "/services/collector" in data["hec_endpoint"]
        assert "hec_instructions" in data
        assert "step_1" in data["hec_instructions"]

    @patch("app.routers.admin.settings")
    @patch("app.routers.admin.get_setting", new_callable=AsyncMock)
    def test_returns_not_configured_when_no_token(
        self,
        mock_get_setting: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.AUTH.APP_BASE_URL = "https://octowatch.example.com"
        mock_get_setting.return_value = None

        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)
        client.cookies.set("csrf_token", "tok")

        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert data["hec_configured"] is False

    @patch("app.routers.admin.settings")
    @patch("app.routers.admin.get_setting", new_callable=AsyncMock)
    def test_hec_endpoint_uses_app_base_url(
        self,
        mock_get_setting: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.AUTH.APP_BASE_URL = "https://myapp.example.com"
        mock_get_setting.return_value = "tok"

        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)
        client.cookies.set("csrf_token", "tok")

        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 200
        data = resp.json()
        # Test assertion — not URL validation
        assert data["hec_endpoint"].startswith(  # codeql[py/incomplete-url-substring-sanitization]
            "https://myapp.example.com"
        )
