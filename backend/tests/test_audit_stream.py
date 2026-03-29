"""Tests for audit log streaming credentials (vault-managed).

Covers:
- AuditStreamSetup schema validation
- POST /setup/audit-stream endpoint
- GET /admin/audit-stream/config endpoint
- PUT /admin/audit-stream/config endpoint
- Config overlay mapping for streaming fields
- MinIOSettings streaming fields
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_valkey
from app.routers import admin as admin_router_module
from app.routers import setup as setup_router_module
from app.schemas.setup import AuditStreamSetup

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


def _build_setup_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(setup_router_module.router, prefix="/api/v1")

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


# ─── Schema Tests ─────────────────────────────────────────────────────────────


class TestAuditStreamSetupSchema:
    """Tests for AuditStreamSetup Pydantic schema validation."""

    def test_valid_payload(self) -> None:
        payload = AuditStreamSetup(
            stream_user="github-stream",
            stream_password="supersecret123",
        )
        assert payload.stream_user == "github-stream"
        assert payload.stream_password == "supersecret123"

    def test_default_stream_user(self) -> None:
        payload = AuditStreamSetup(stream_password="mysecretpw")
        assert payload.stream_user == "github-stream"

    def test_custom_stream_user(self) -> None:
        payload = AuditStreamSetup(
            stream_user="custom-user",
            stream_password="password123",
        )
        assert payload.stream_user == "custom-user"

    def test_password_required(self) -> None:
        with pytest.raises(ValidationError):
            AuditStreamSetup(stream_user="github-stream")

    def test_password_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditStreamSetup(stream_user="github-stream", stream_password="short")

    def test_password_min_length_boundary(self) -> None:
        payload = AuditStreamSetup(
            stream_user="github-stream",
            stream_password="12345678",
        )
        assert payload.stream_password == "12345678"

    def test_password_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditStreamSetup(
                stream_user="github-stream",
                stream_password="1234567",
            )

    def test_stream_user_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditStreamSetup(stream_user="ab", stream_password="password123")

    def test_stream_user_min_length_boundary(self) -> None:
        payload = AuditStreamSetup(stream_user="abc", stream_password="password123")
        assert payload.stream_user == "abc"

    def test_empty_password_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditStreamSetup(stream_user="github-stream", stream_password="")


# ─── MinIO Config Fields Tests ────────────────────────────────────────────────


class TestMinIOSettingsStreamFields:
    """Tests for the new MINIO_STREAM_USER and MINIO_STREAM_PASSWORD fields."""

    def test_stream_fields_exist(self) -> None:
        from app.config import MinIOSettings

        s = MinIOSettings(
            MINIO_AUDIT_BUCKET="audit-logs",
            MINIO_INGEST_USER="ingest",
            MINIO_INGEST_PASSWORD="ingest-pw",
        )
        assert s.MINIO_STREAM_USER == "github-stream"
        assert s.MINIO_STREAM_PASSWORD == ""

    def test_stream_fields_custom_values(self) -> None:
        from app.config import MinIOSettings

        s = MinIOSettings(
            MINIO_AUDIT_BUCKET="audit-logs",
            MINIO_INGEST_USER="ingest",
            MINIO_INGEST_PASSWORD="ingest-pw",
            MINIO_STREAM_USER="custom-stream",
            MINIO_STREAM_PASSWORD="custom-pw",
        )
        assert s.MINIO_STREAM_USER == "custom-stream"
        assert s.MINIO_STREAM_PASSWORD == "custom-pw"

    def test_stream_user_default(self) -> None:
        from app.config import MinIOSettings

        s = MinIOSettings(
            MINIO_AUDIT_BUCKET="audit-logs",
            MINIO_INGEST_USER="ingest",
            MINIO_INGEST_PASSWORD="ingest-pw",
        )
        assert s.MINIO_STREAM_USER == "github-stream"

    def test_stream_password_default_empty(self) -> None:
        from app.config import MinIOSettings

        s = MinIOSettings(
            MINIO_AUDIT_BUCKET="audit-logs",
            MINIO_INGEST_USER="ingest",
            MINIO_INGEST_PASSWORD="ingest-pw",
        )
        assert s.MINIO_STREAM_PASSWORD == ""


# ─── Config Overlay Tests ─────────────────────────────────────────────────────


class TestConfigOverlayStreamMappings:
    """Tests for the config overlay SETTING_MAP entries for streaming."""

    def test_stream_user_mapping_exists(self) -> None:
        from app.services.config_overlay import SETTING_MAP

        assert "minio_stream_user" in SETTING_MAP
        assert SETTING_MAP["minio_stream_user"] == ("MINIO", "MINIO_STREAM_USER")

    def test_stream_password_mapping_exists(self) -> None:
        from app.services.config_overlay import SETTING_MAP

        assert "minio_stream_password" in SETTING_MAP
        assert SETTING_MAP["minio_stream_password"] == ("MINIO", "MINIO_STREAM_PASSWORD")


# ─── Setup Router Tests ──────────────────────────────────────────────────────


class TestSetupAuditStreamAuth:
    """Verify that the audit-stream setup endpoint requires sys_admin role."""

    def test_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_setup_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/setup/audit-stream",
            json={"stream_user": "github-stream", "stream_password": "password123"},
        )
        assert resp.status_code == 401

    def test_non_admin_returns_403(self) -> None:
        app, _, _ = _build_setup_app(valkey_session=_make_analyst_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(sub="analyst", jti="analyst-jti")
        client.cookies.set("access_token", token)
        resp = client.post(
            "/api/v1/setup/audit-stream",
            json={"stream_user": "github-stream", "stream_password": "password123"},
        )
        assert resp.status_code == 403


class TestSetupAuditStreamEndpoint:
    """Tests for POST /setup/audit-stream endpoint."""

    @patch("app.routers.setup.is_setup_complete", new_callable=AsyncMock)
    @patch("app.routers.setup.set_setting", new_callable=AsyncMock)
    def test_saves_credentials_to_vault(
        self,
        mock_set_setting: AsyncMock,
        mock_is_complete: AsyncMock,
    ) -> None:
        mock_is_complete.return_value = False

        app, mock_db, _ = _build_setup_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.post(
            "/api/v1/setup/audit-stream",
            json={"stream_user": "my-stream-user", "stream_password": "mysecretpw"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "credentials saved" in data["message"].lower()

        # Verify set_setting was called for both user and password
        assert mock_set_setting.call_count == 2
        calls = mock_set_setting.call_args_list

        # First call: stream_user
        call_user = calls[0]
        assert call_user.args[1] == "minio_stream_user"
        assert call_user.args[2] == "my-stream-user"
        assert call_user.kwargs["category"] == "audit_stream"
        assert call_user.kwargs["sensitivity"] == "sensitive"

        # Second call: stream_password
        call_pw = calls[1]
        assert call_pw.args[1] == "minio_stream_password"
        assert call_pw.args[2] == "mysecretpw"
        assert call_pw.kwargs["category"] == "audit_stream"
        assert call_pw.kwargs["sensitivity"] == "critical"

    @patch("app.routers.setup.is_setup_complete", new_callable=AsyncMock)
    @patch("app.routers.setup.set_setting", new_callable=AsyncMock)
    def test_uses_default_stream_user(
        self,
        mock_set_setting: AsyncMock,
        mock_is_complete: AsyncMock,
    ) -> None:
        mock_is_complete.return_value = False

        app, mock_db, _ = _build_setup_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.post(
            "/api/v1/setup/audit-stream",
            json={"stream_password": "mysecretpw"},
        )
        assert resp.status_code == 200

        # First call should use default "github-stream"
        call_user = mock_set_setting.call_args_list[0]
        assert call_user.args[2] == "github-stream"

    @patch("app.routers.setup.is_setup_complete", new_callable=AsyncMock)
    def test_rejects_when_setup_complete(
        self,
        mock_is_complete: AsyncMock,
    ) -> None:
        mock_is_complete.return_value = True

        app, _, _ = _build_setup_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.post(
            "/api/v1/setup/audit-stream",
            json={"stream_user": "github-stream", "stream_password": "password123"},
        )
        assert resp.status_code == 403

    def test_invalid_password_too_short(self) -> None:
        app, _, _ = _build_setup_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.post(
            "/api/v1/setup/audit-stream",
            json={"stream_user": "github-stream", "stream_password": "short"},
        )
        assert resp.status_code == 422

    def test_missing_password_rejected(self) -> None:
        app, _, _ = _build_setup_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.post(
            "/api/v1/setup/audit-stream",
            json={"stream_user": "github-stream"},
        )
        assert resp.status_code == 422


# ─── Admin Router Tests ───────────────────────────────────────────────────────


class TestAdminAuditStreamAuth:
    """Verify that admin audit-stream endpoints require sys_admin role."""

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
        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 403

    def test_put_config_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_admin_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "u", "stream_password": "password123"},
        )
        assert resp.status_code == 401

    def test_put_config_non_admin_returns_403(self) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_analyst_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(sub="analyst", jti="analyst-jti")
        client.cookies.set("access_token", token)
        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "u", "stream_password": "password123"},
        )
        assert resp.status_code == 403


class TestGetAuditStreamConfig:
    """Tests for GET /admin/audit-stream/config endpoint."""

    @patch("app.routers.admin.settings")
    @patch("app.routers.admin.get_setting", new_callable=AsyncMock)
    def test_returns_config_when_configured(
        self,
        mock_get_setting: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.AUTH.APP_BASE_URL = "https://octowatch.example.com"
        mock_settings.MINIO.MINIO_AUDIT_BUCKET = "audit-logs"

        async def side_effect(db: Any, key: str) -> str | None:
            if key == "minio_stream_user":
                return "github-stream"
            if key == "minio_stream_password":
                return "secret-password"
            return None

        mock_get_setting.side_effect = side_effect

        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["stream_user"] == "github-stream"
        assert data["s3_endpoint"] == "https://octowatch.example.com/s3"
        assert data["bucket"] == "audit-logs"
        assert data["region"] == "us-east-1"
        assert "instructions" in data
        assert "step_1" in data["instructions"]
        assert "step_7" in data["instructions"]

    @patch("app.routers.admin.settings")
    @patch("app.routers.admin.get_setting", new_callable=AsyncMock)
    def test_returns_not_configured_when_empty(
        self,
        mock_get_setting: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.AUTH.APP_BASE_URL = "https://octowatch.example.com"
        mock_settings.MINIO.MINIO_AUDIT_BUCKET = "audit-logs"
        mock_get_setting.return_value = None

        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert data["stream_user"] == ""

    @patch("app.routers.admin.settings")
    @patch("app.routers.admin.get_setting", new_callable=AsyncMock)
    def test_instructions_include_configure_first_when_no_user(
        self,
        mock_get_setting: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        mock_settings.AUTH.APP_BASE_URL = "https://octowatch.example.com"
        mock_settings.MINIO.MINIO_AUDIT_BUCKET = "audit-logs"
        mock_get_setting.return_value = None

        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.get("/api/v1/admin/audit-stream/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "<configure first>" in data["instructions"]["step_5"]


class TestUpdateAuditStreamConfig:
    """Tests for PUT /admin/audit-stream/config endpoint."""

    @patch("app.routers.admin.set_setting", new_callable=AsyncMock)
    def test_updates_credentials_successfully(
        self,
        mock_set_setting: AsyncMock,
    ) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "my-user", "stream_password": "mypassword123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "updated" in data["message"].lower()

        # Verify set_setting was called twice
        assert mock_set_setting.call_count == 2
        calls = mock_set_setting.call_args_list

        # First: stream_user
        assert calls[0].args[1] == "minio_stream_user"
        assert calls[0].args[2] == "my-user"
        assert calls[0].kwargs["sensitivity"] == "sensitive"

        # Second: stream_password
        assert calls[1].args[1] == "minio_stream_password"
        assert calls[1].args[2] == "mypassword123"
        assert calls[1].kwargs["sensitivity"] == "critical"

    def test_rejects_missing_stream_user(self) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_password": "mypassword123"},
        )
        assert resp.status_code == 422

    def test_rejects_missing_stream_password(self) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "my-user"},
        )
        assert resp.status_code == 422

    def test_rejects_empty_stream_user(self) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "", "stream_password": "mypassword123"},
        )
        assert resp.status_code == 422

    def test_rejects_empty_stream_password(self) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "my-user", "stream_password": ""},
        )
        assert resp.status_code == 422

    def test_rejects_short_password(self) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "my-user", "stream_password": "short"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "8 characters" in data["detail"]

    def test_rejects_empty_body(self) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={},
        )
        assert resp.status_code == 422

    @patch("app.routers.admin.set_setting", new_callable=AsyncMock)
    def test_strips_whitespace_from_inputs(
        self,
        mock_set_setting: AsyncMock,
    ) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "  my-user  ", "stream_password": "  mypassword123  "},
        )
        assert resp.status_code == 200

        calls = mock_set_setting.call_args_list
        assert calls[0].args[2] == "my-user"
        assert calls[1].args[2] == "mypassword123"

    @patch("app.routers.admin.set_setting", new_callable=AsyncMock)
    def test_records_changed_by_user(
        self,
        mock_set_setting: AsyncMock,
    ) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "my-user", "stream_password": "password123"},
        )
        assert resp.status_code == 200

        for call in mock_set_setting.call_args_list:
            assert call.kwargs["changed_by"] == "admin"

    @patch("app.routers.admin.set_setting", new_callable=AsyncMock)
    def test_password_min_boundary_accepted(
        self,
        mock_set_setting: AsyncMock,
    ) -> None:
        app, _, _ = _build_admin_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/audit-stream/config",
            json={"stream_user": "my-user", "stream_password": "12345678"},
        )
        assert resp.status_code == 200
