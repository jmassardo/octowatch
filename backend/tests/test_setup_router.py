"""Tests for the setup wizard router: initial-admins endpoint and current config.

Tests cover:
- POST /setup/initial-admins creates DB-backed sys_admin role assignments
- POST /setup/initial-admins rejects requests when setup is already complete
- POST /setup/initial-admins returns 500 when sys_admin role is missing
- GET /setup/current returns initial_admins_configured flag
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import setup as setup_router_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(
    sub: str = "setup_admin",
    jti: str = "setup-jti",
) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(hours=1)
    payload = {"sub": sub, "github_id": 0, "jti": jti, "exp": exp, "iat": now}
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(login: str = "setup_admin", roles: list[str] | None = None) -> str:
    return json.dumps(
        {
            "github_login": login,
            "github_id": 0,
            "roles": roles or ["sys_admin"],
            "scoped_orgs": [],
            "scoped_repos": [],
            "scope_type": "global",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
            "display_name": "Setup Administrator",
        }
    )


def _build_setup_app(
    valkey_get_return: str | None = None,
    db_execute_side_effect: list[Any] | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(setup_router_module.router, prefix="/api/v1")

    mock_db = AsyncMock()
    if db_execute_side_effect:
        mock_db.execute = AsyncMock(side_effect=db_execute_side_effect)
    else:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(return_value=mock_result)

    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_get_return)

    async def override_db() -> Any:
        yield mock_db

    async def override_valkey() -> Any:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


def _mock_setup_incomplete() -> MagicMock:
    """Return a mock result for is_setup_complete that says setup is NOT complete."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


def _mock_setup_complete() -> MagicMock:
    """Return a mock result for is_setup_complete that says setup IS complete."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock()
    return result


def _mock_sys_admin_role() -> MagicMock:
    """Return a mock result for looking up the sys_admin role."""
    role = MagicMock()
    role.id = 1
    role.name = "sys_admin"
    result = MagicMock()
    result.scalar_one_or_none.return_value = role
    return result


def _mock_no_role() -> MagicMock:
    """Return a mock result for looking up a role that doesn't exist."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


def _mock_admin_count(count: int) -> MagicMock:
    """Return a mock result for counting admin assignments."""
    result = MagicMock()
    result.scalar_one.return_value = count
    return result


# ─── POST /setup/initial-admins ──────────────────────────────────────────────


class TestSetupInitialAdmins:
    @patch("app.routers.setup.settings")
    def test_initial_admins_without_auth_returns_401(self, mock_settings: MagicMock) -> None:
        app, _, _ = _build_setup_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/setup/initial-admins",
            json={"admin_logins": ["alice"]},
        )
        assert resp.status_code == 401

    @patch("app.routers.setup.settings")
    def test_initial_admins_with_non_admin_returns_403(self, mock_settings: MagicMock) -> None:
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_setup_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/setup/initial-admins",
            json={"admin_logins": ["alice"]},
            cookies={"access_token": token},
        )
        assert resp.status_code == 403

    @patch("app.routers.setup.settings")
    def test_initial_admins_creates_role_assignments(self, mock_settings: MagicMock) -> None:
        """POST /setup/initial-admins creates DB role assignments for each login."""
        mock_settings.SECRET_KEY = SECRET
        mock_settings.JWT_TTL_SECONDS = 3600
        session = _make_session()

        app, mock_db, _ = _build_setup_app(
            valkey_get_return=session,
            db_execute_side_effect=[
                _mock_setup_incomplete(),  # _require_setup_incomplete
                _mock_sys_admin_role(),  # lookup sys_admin role
            ],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/setup/initial-admins",
            json={"admin_logins": ["alice", "Bob"]},
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "2 users" in data["message"]

        # Verify db.add was called for each login (the setup_incomplete check
        # may also call db.add when creating the setup state row, so we check
        # the calls for our specific UserRoleAssignment objects)
        assignment_adds = [
            call_args[0][0]
            for call_args in mock_db.add.call_args_list
            if hasattr(call_args[0][0], "github_login")
        ]
        assert len(assignment_adds) == 2
        mock_db.commit.assert_awaited_once()

    @patch("app.routers.setup.settings")
    def test_initial_admins_lowercases_logins(self, mock_settings: MagicMock) -> None:
        """Logins are normalized to lowercase before storing."""
        mock_settings.SECRET_KEY = SECRET
        mock_settings.JWT_TTL_SECONDS = 3600
        session = _make_session()

        app, mock_db, _ = _build_setup_app(
            valkey_get_return=session,
            db_execute_side_effect=[
                _mock_setup_incomplete(),
                _mock_sys_admin_role(),
            ],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/setup/initial-admins",
            json={"admin_logins": ["  ALICE  "]},
            cookies={"access_token": token},
        )
        assert resp.status_code == 200

        # Check the assignment was created with lowercase login
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.github_login == "alice"
        assert added_obj.granted_by == "setup_wizard"
        assert added_obj.scope_type == "global"
        assert added_obj.active is True

    @patch("app.routers.setup.settings")
    def test_initial_admins_rejects_when_setup_complete(self, mock_settings: MagicMock) -> None:
        """Returns 403 when setup is already completed."""
        mock_settings.SECRET_KEY = SECRET
        mock_settings.JWT_TTL_SECONDS = 3600
        session = _make_session()

        app, _, _ = _build_setup_app(
            valkey_get_return=session,
            db_execute_side_effect=[
                _mock_setup_complete(),  # _require_setup_incomplete → 403
            ],
        )
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/setup/initial-admins",
            json={"admin_logins": ["alice"]},
            cookies={"access_token": token},
        )
        assert resp.status_code == 403
        assert "already been completed" in resp.json()["detail"]

    @patch("app.routers.setup.settings")
    def test_initial_admins_returns_500_when_role_missing(self, mock_settings: MagicMock) -> None:
        """Returns 500 when sys_admin role is not found in the database."""
        mock_settings.SECRET_KEY = SECRET
        mock_settings.JWT_TTL_SECONDS = 3600
        session = _make_session()

        app, _, _ = _build_setup_app(
            valkey_get_return=session,
            db_execute_side_effect=[
                _mock_setup_incomplete(),
                _mock_no_role(),  # sys_admin role not found
            ],
        )
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/setup/initial-admins",
            json={"admin_logins": ["alice"]},
            cookies={"access_token": token},
        )
        assert resp.status_code == 500
        assert "sys_admin role not found" in resp.json()["detail"]

    @patch("app.routers.setup.settings")
    def test_initial_admins_rejects_empty_list(self, mock_settings: MagicMock) -> None:
        """Rejects payload with empty admin_logins list (validated by schema)."""
        mock_settings.SECRET_KEY = SECRET
        mock_settings.JWT_TTL_SECONDS = 3600
        session = _make_session()

        app, _, _ = _build_setup_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/setup/initial-admins",
            json={"admin_logins": []},
            cookies={"access_token": token},
        )
        assert resp.status_code == 422


# ─── GET /setup/current (initial_admins_configured flag) ─────────────────────


class TestSetupCurrentConfig:
    @patch("app.routers.setup.settings")
    def test_current_config_includes_initial_admins_flag_false(
        self, mock_settings: MagicMock
    ) -> None:
        """GET /setup/current returns initial_admins_configured: false when none set."""
        mock_settings.SECRET_KEY = SECRET
        mock_settings.JWT_TTL_SECONDS = 3600
        mock_settings.AUTH.GITHUB_CLIENT_ID = ""
        mock_settings.GITHUB_APP.GITHUB_APP_ID = ""
        mock_settings.AUTH.SAML_IDP_METADATA_URL = ""
        session = _make_session()

        app, _, _ = _build_setup_app(
            valkey_get_return=session,
            db_execute_side_effect=[
                _mock_setup_incomplete(),  # _require_setup_incomplete
                _mock_admin_count(0),  # _count_admin_assignments
            ],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/setup/current",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["initial_admins_configured"] is False

    @patch("app.routers.setup.settings")
    def test_current_config_includes_initial_admins_flag_true(
        self, mock_settings: MagicMock
    ) -> None:
        """GET /setup/current returns initial_admins_configured: true when admins exist."""
        mock_settings.SECRET_KEY = SECRET
        mock_settings.JWT_TTL_SECONDS = 3600
        mock_settings.AUTH.GITHUB_CLIENT_ID = ""
        mock_settings.GITHUB_APP.GITHUB_APP_ID = ""
        mock_settings.AUTH.SAML_IDP_METADATA_URL = ""
        session = _make_session()

        app, _, _ = _build_setup_app(
            valkey_get_return=session,
            db_execute_side_effect=[
                _mock_setup_incomplete(),
                _mock_admin_count(2),  # 2 admin assignments
            ],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/setup/current",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["initial_admins_configured"] is True
