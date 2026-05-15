"""Integration tests for the dashboard config router.

Tests cover:
- GET /dashboard/config — creates default on first visit
- PUT /dashboard/config — save/update layout
- GET /dashboard/widgets — widget catalog
- GET /dashboard/personas — persona list with default layouts
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import dashboard_config as dashboard_config_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(
    sub: str = "testuser",
    jti: str = "test-jti",
) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(hours=1)
    payload = {"sub": sub, "github_id": 12345, "jti": jti, "exp": exp, "iat": now}
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(login: str = "testuser") -> str:
    return json.dumps(
        {
            "github_login": login,
            "github_id": 12345,
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
    mock_result.fetchall.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _build_app(
    valkey_get_return: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(dashboard_config_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_get_return)
    mock_valkey.delete = AsyncMock(return_value=1)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestGetDashboardConfig:
    """GET /api/v1/dashboard/config."""

    @patch("app.deps.settings")
    def test_creates_default_config_on_first_visit(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, mock_db, _ = _build_app(valkey_get_return=session_data)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.get(
            "/api/v1/dashboard/config",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "testuser"
        assert body["persona"] == "security-analyst"
        assert isinstance(body["layout"], list)
        assert len(body["layout"]) > 0
        # Verify db.add was called to persist the new config
        mock_db.add.assert_called_once()

    @patch("app.deps.settings")
    def test_returns_existing_config(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, mock_db, _ = _build_app(valkey_get_return=session_data)

        # Simulate an existing config row
        existing_config = MagicMock()
        existing_config.id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        existing_config.user_id = "testuser"
        existing_config.layout = [{"widget_id": "sync-health", "x": 0, "y": 0, "w": 4, "h": 3}]
        existing_config.persona = "platform-engineer"
        existing_config.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        existing_config.updated_at = datetime(2026, 1, 2, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_config
        mock_db.execute = AsyncMock(return_value=mock_result)

        client = TestClient(app)
        resp = client.get(
            "/api/v1/dashboard/config",
            cookies={"access_token": _make_jwt()},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["persona"] == "platform-engineer"
        assert len(body["layout"]) == 1
        assert body["layout"][0]["widget_id"] == "sync-health"

    @patch("app.deps.settings")
    def test_unauthenticated(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        app, _, _ = _build_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/dashboard/config")
        assert resp.status_code == 401


class TestUpdateDashboardConfig:
    """PUT /api/v1/dashboard/config."""

    @patch("app.deps.settings")
    def test_creates_new_config_on_update(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, mock_db, _ = _build_app(valkey_get_return=session_data)
        client = TestClient(app)

        token = _make_jwt()
        body = {
            "layout": [{"widget_id": "event-volume", "x": 0, "y": 0, "w": 6, "h": 3}],
            "persona": "executive",
        }
        resp = client.put(
            "/api/v1/dashboard/config",
            json=body,
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "testuser"
        assert data["persona"] == "executive"
        assert len(data["layout"]) == 1
        mock_db.add.assert_called_once()

    @patch("app.deps.settings")
    def test_updates_existing_config(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, mock_db, _ = _build_app(valkey_get_return=session_data)

        existing_config = MagicMock()
        existing_config.id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        existing_config.user_id = "testuser"
        existing_config.layout = []
        existing_config.persona = ""
        existing_config.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        existing_config.updated_at = datetime(2026, 1, 2, tzinfo=UTC)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_config
        mock_db.execute = AsyncMock(return_value=mock_result)

        client = TestClient(app)
        body = {
            "layout": [
                {"widget_id": "posture-score", "x": 0, "y": 0, "w": 4, "h": 3},
                {"widget_id": "compliance-status", "x": 4, "y": 0, "w": 4, "h": 3},
            ],
            "persona": "engineering-manager",
        }
        resp = client.put(
            "/api/v1/dashboard/config",
            json=body,
            cookies={"access_token": _make_jwt(), "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["persona"] == "engineering-manager"

    @patch("app.deps.settings")
    def test_validates_persona(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, _, _ = _build_app(valkey_get_return=session_data)
        client = TestClient(app)

        body = {"layout": [], "persona": "invalid-persona"}
        resp = client.put(
            "/api/v1/dashboard/config",
            json=body,
            cookies={"access_token": _make_jwt(), "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 422

    @patch("app.deps.settings")
    def test_validates_layout_widget_id(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, _, _ = _build_app(valkey_get_return=session_data)
        client = TestClient(app)

        body = {
            "layout": [{"widget_id": "", "x": 0, "y": 0, "w": 4, "h": 3}],
            "persona": "",
        }
        resp = client.put(
            "/api/v1/dashboard/config",
            json=body,
            cookies={"access_token": _make_jwt(), "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 422


class TestWidgetCatalog:
    """GET /api/v1/dashboard/widgets."""

    @patch("app.deps.settings")
    def test_lists_all_widgets(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, _, _ = _build_app(valkey_get_return=session_data)
        client = TestClient(app)

        resp = client.get(
            "/api/v1/dashboard/widgets",
            cookies={"access_token": _make_jwt()},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "widgets" in body
        widget_ids = [w["id"] for w in body["widgets"]]
        assert "unified-security" in widget_ids
        assert "copilot-usage" in widget_ids
        assert "workflow-health" in widget_ids
        assert len(body["widgets"]) >= 16

    @patch("app.deps.settings")
    def test_widget_has_required_fields(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, _, _ = _build_app(valkey_get_return=session_data)
        client = TestClient(app)

        resp = client.get(
            "/api/v1/dashboard/widgets",
            cookies={"access_token": _make_jwt()},
        )

        widget = resp.json()["widgets"][0]
        assert "id" in widget
        assert "title" in widget
        assert "description" in widget
        assert "category" in widget
        assert "default_w" in widget
        assert "default_h" in widget


class TestPersonas:
    """GET /api/v1/dashboard/personas."""

    @patch("app.deps.settings")
    def test_lists_all_personas(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, _, _ = _build_app(valkey_get_return=session_data)
        client = TestClient(app)

        resp = client.get(
            "/api/v1/dashboard/personas",
            cookies={"access_token": _make_jwt()},
        )

        assert resp.status_code == 200
        body = resp.json()
        persona_ids = [p["id"] for p in body["personas"]]
        assert "security-analyst" in persona_ids
        assert "engineering-manager" in persona_ids
        assert "platform-engineer" in persona_ids
        assert "executive" in persona_ids
        assert len(body["personas"]) == 4

    @patch("app.deps.settings")
    def test_persona_has_default_layout(self, mock_settings: MagicMock) -> None:
        mock_settings.SECRET_KEY = SECRET
        mock_settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS = 999999

        session_data = _make_session()
        app, _, _ = _build_app(valkey_get_return=session_data)
        client = TestClient(app)

        resp = client.get(
            "/api/v1/dashboard/personas",
            cookies={"access_token": _make_jwt()},
        )

        for persona in resp.json()["personas"]:
            assert "default_layout" in persona
            assert isinstance(persona["default_layout"], list)
            assert len(persona["default_layout"]) > 0
            first_item = persona["default_layout"][0]
            assert "widget_id" in first_item
            assert "x" in first_item
            assert "y" in first_item
            assert "w" in first_item
            assert "h" in first_item
