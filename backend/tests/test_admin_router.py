"""Tests for the admin router: sessions, role assignments, and synced teams.

Tests cover:
- Active sessions endpoint with role resolution
- Role assignment CRUD with role_name in response
- Synced teams listing
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
from app.routers import admin as admin_router_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(
    sub: str = "admin-user",
    jti: str = "admin-jti",
) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(hours=1)
    payload = {"sub": sub, "github_id": 99, "jti": jti, "exp": exp, "iat": now}
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(login: str = "admin-user", roles: list[str] | None = None) -> str:
    return json.dumps(
        {
            "github_login": login,
            "github_id": 99,
            "roles": roles or ["sys_admin"],
            "scoped_orgs": [],
            "scoped_repos": [],
            "scope_type": "global",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


class _FakeRow:
    """Simulate a SQLAlchemy Row returned from raw text queries."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _build_admin_app(
    valkey_get_return: str | None = None,
    db_execute_side_effect: list[Any] | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(admin_router_module.router, prefix="/api/v1")

    mock_db = AsyncMock()
    if db_execute_side_effect:
        mock_db.execute = AsyncMock(side_effect=db_execute_side_effect)
    else:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

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


# ─── Active sessions ─────────────────────────────────────────────────────────


class TestListActiveSessions:
    def test_sessions_without_auth_returns_401(self) -> None:
        app, _, _ = _build_admin_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/sessions")
        assert resp.status_code == 401

    def test_sessions_with_non_admin_returns_403(self) -> None:
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_admin_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.get("/api/v1/admin/sessions", cookies={"access_token": token})
        assert resp.status_code == 403

    def test_sessions_returns_empty_when_no_audit_trail(self) -> None:
        session = _make_session()
        # First execute: audit_trail query returns empty
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get("/api/v1/admin/sessions", cookies={"access_token": token})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_sessions_resolves_actual_roles(self) -> None:
        session = _make_session()

        # First execute: audit_trail query returns active users
        audit_result = MagicMock()
        audit_result.fetchall.return_value = [
            _FakeRow(
                user_login="alice",
                last_active_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
                session_count=3,
            ),
            _FakeRow(
                user_login="bob",
                last_active_at=datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC),
                session_count=1,
            ),
        ]

        # Second execute: role assignment query returns tuples (login, role_name)
        role_result = MagicMock()
        role_result.fetchall.return_value = [
            ("alice", "sys_admin"),
            ("bob", "analyst"),
        ]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[audit_result, role_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get("/api/v1/admin/sessions", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        alice = next(u for u in data if u["login"] == "alice")
        bob = next(u for u in data if u["login"] == "bob")
        assert alice["role"] == "sys_admin"
        assert bob["role"] == "analyst"

    def test_sessions_defaults_to_viewer_when_no_role_found(self) -> None:
        session = _make_session()

        audit_result = MagicMock()
        audit_result.fetchall.return_value = [
            _FakeRow(
                user_login="unknown-user",
                last_active_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
                session_count=1,
            ),
        ]

        # No roles found for this user
        role_result = MagicMock()
        role_result.fetchall.return_value = []

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[audit_result, role_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get("/api/v1/admin/sessions", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["role"] == "viewer"

    def test_sessions_returns_highest_priority_role(self) -> None:
        """When a user has multiple roles, the highest-privilege one is returned."""
        session = _make_session()

        audit_result = MagicMock()
        audit_result.fetchall.return_value = [
            _FakeRow(
                user_login="multi-role",
                last_active_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
                session_count=2,
            ),
        ]

        # User has both analyst and report_admin roles
        role_result = MagicMock()
        role_result.fetchall.return_value = [
            ("multi-role", "analyst"),
            ("multi-role", "report_admin"),
        ]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[audit_result, role_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get("/api/v1/admin/sessions", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        # report_admin is higher priority than analyst
        assert data[0]["role"] == "report_admin"

    @patch("app.routers.admin.settings")
    def test_sessions_grants_sys_admin_to_initial_admin_logins(
        self, mock_settings: MagicMock
    ) -> None:
        """INITIAL_ADMIN_LOGINS users get sys_admin regardless of DB roles."""
        mock_settings.initial_admin_logins = {"bootstrap-admin"}
        session = _make_session()

        audit_result = MagicMock()
        audit_result.fetchall.return_value = [
            _FakeRow(
                user_login="bootstrap-admin",
                last_active_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
                session_count=1,
            ),
        ]

        # No roles in the DB
        role_result = MagicMock()
        role_result.fetchall.return_value = []

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[audit_result, role_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get("/api/v1/admin/sessions", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["role"] == "sys_admin"


# ─── Synced teams ─────────────────────────────────────────────────────────────


class TestListSyncedTeams:
    def test_teams_without_auth_returns_401(self) -> None:
        app, _, _ = _build_admin_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/teams")
        assert resp.status_code == 401

    def test_teams_returns_empty_list_when_none_synced(self) -> None:
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get("/api/v1/admin/teams", cookies={"access_token": token})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_teams_returns_synced_team_data(self) -> None:
        session = _make_session()

        synced_at = datetime(2024, 6, 1, tzinfo=UTC)
        # MagicMock(name=...) sets the mock's internal name, not an attribute.
        # Set .name explicitly after construction.
        team1 = MagicMock(
            org="my-org",
            team_slug="security-team",
            privacy="closed",
            synced_at=synced_at,
        )
        team1.name = "Security Team"

        team2 = MagicMock(
            org="my-org",
            team_slug="dev-team",
            privacy="secret",
            synced_at=synced_at,
        )
        team2.name = "Dev Team"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [team1, team2]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = client.get("/api/v1/admin/teams", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["team_slug"] == "security-team"
        assert data[0]["name"] == "Security Team"
        assert data[1]["team_slug"] == "dev-team"


# ─── Role priority ────────────────────────────────────────────────────────────


class TestRolePriority:
    """Verify the _ROLE_PRIORITY ordering used by list_active_sessions."""

    def test_role_priority_order(self) -> None:
        from app.routers.admin import _ROLE_PRIORITY

        assert _ROLE_PRIORITY == [
            "sys_admin",
            "report_admin",
            "rule_author",
            "analyst",
            "viewer",
        ]
