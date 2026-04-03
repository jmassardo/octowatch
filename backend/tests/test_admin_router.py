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


# ─── Audit trail export ───────────────────────────────────────────────────────

_CSRF_TOKEN = "test-csrf-token"


def _make_audit_row(**overrides: Any) -> MagicMock:
    """Create a mock AuditTrail row with sensible defaults."""
    defaults: dict[str, Any] = {
        "id": 1,
        "timestamp": datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC),
        "user_login": "alice",
        "user_github_id": 42,
        "ip_address": "10.0.0.1",
        "user_agent": "Mozilla/5.0",
        "action_type": "role.assign",
        "resource_type": "user",
        "resource_id": "bob",
        "parameters": {"role": "analyst"},
        "outcome": "success",
        "error_detail": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


class TestExportAuditTrail:
    """Tests for POST /admin/audit-trail/export."""

    def _post_export(
        self,
        client: TestClient,
        token: str,
        params: dict[str, str],
    ) -> Any:
        """POST to the export endpoint with CSRF token included."""
        return client.post(
            "/api/v1/admin/audit-trail/export",
            params=params,
            cookies={"access_token": token, "csrf_token": _CSRF_TOKEN},
            headers={"X-CSRF-Token": _CSRF_TOKEN},
        )

    def test_export_without_auth_returns_401(self) -> None:
        app, _, _ = _build_admin_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/admin/audit-trail/export",
            params={"from_date": "2024-01-01", "to_date": "2024-12-31"},
        )
        assert resp.status_code == 401

    def test_export_with_non_admin_returns_403(self) -> None:
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_admin_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = self._post_export(
            client, token, {"from_date": "2024-01-01", "to_date": "2024-12-31"}
        )
        assert resp.status_code == 403

    def test_export_without_csrf_returns_403(self) -> None:
        """POST without CSRF token should be rejected."""
        session = _make_session()
        app, _, _ = _build_admin_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/admin/audit-trail/export",
            params={"from_date": "2024-01-01", "to_date": "2024-12-31"},
            cookies={"access_token": token},
        )
        assert resp.status_code == 403

    def test_export_csv_default_format(self) -> None:
        """Default format should be CSV with proper headers and content."""
        session = _make_session()
        row = _make_audit_row()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client, token, {"from_date": "2024-01-01", "to_date": "2024-12-31"}
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert "audit_trail_" in resp.headers["content-disposition"]
        assert ".csv" in resp.headers["content-disposition"]

        # Parse the CSV body
        import csv
        import io

        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["user_login"] == "alice"
        assert rows[0]["action_type"] == "role.assign"
        assert rows[0]["outcome"] == "success"
        assert rows[0]["ip_address"] == "10.0.0.1"

    def test_export_csv_header_row_present(self) -> None:
        """CSV should include a header row with all expected columns."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client,
            token,
            {"from_date": "2024-01-01", "to_date": "2024-12-31", "format": "csv"},
        )
        assert resp.status_code == 200
        header_line = resp.text.split("\r\n")[0]
        expected_columns = [
            "id",
            "timestamp",
            "user_login",
            "user_github_id",
            "ip_address",
            "user_agent",
            "action_type",
            "resource_type",
            "resource_id",
            "parameters",
            "outcome",
            "error_detail",
        ]
        assert header_line == ",".join(expected_columns)

    def test_export_csv_multiple_rows(self) -> None:
        """CSV export should include all matching rows."""
        session = _make_session()
        row1 = _make_audit_row(id=1, user_login="alice", action_type="login")
        row2 = _make_audit_row(id=2, user_login="bob", action_type="logout")
        row3 = _make_audit_row(id=3, user_login="carol", action_type="role.assign")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row1, row2, row3]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client, token, {"from_date": "2024-01-01", "to_date": "2024-12-31"}
        )
        import csv
        import io

        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 3
        assert [r["user_login"] for r in rows] == ["alice", "bob", "carol"]

    def test_export_json_format(self) -> None:
        """JSON format should return NDJSON with proper content type."""
        session = _make_session()
        row = _make_audit_row()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client,
            token,
            {"from_date": "2024-01-01", "to_date": "2024-12-31", "format": "json"},
        )
        assert resp.status_code == 200
        assert "ndjson" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert ".ndjson" in resp.headers["content-disposition"]

        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["user_login"] == "alice"
        assert parsed["action_type"] == "role.assign"
        assert parsed["parameters"] == '{"role": "analyst"}'

    def test_export_json_multiple_rows(self) -> None:
        """NDJSON should have one JSON object per line."""
        session = _make_session()
        row1 = _make_audit_row(id=1, user_login="alice")
        row2 = _make_audit_row(id=2, user_login="bob")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row1, row2]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client,
            token,
            {"from_date": "2024-01-01", "to_date": "2024-12-31", "format": "json"},
        )
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 2
        assert json.loads(lines[0])["user_login"] == "alice"
        assert json.loads(lines[1])["user_login"] == "bob"

    def test_export_invalid_format_returns_400(self) -> None:
        """Unsupported format should return 400."""
        session = _make_session()
        app, _, _ = _build_admin_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = self._post_export(
            client,
            token,
            {"from_date": "2024-01-01", "to_date": "2024-12-31", "format": "xml"},
        )
        assert resp.status_code == 400
        assert "xml" in resp.json()["detail"]

    def test_export_empty_result_csv(self) -> None:
        """CSV export with no matching records should return only the header."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client, token, {"from_date": "2024-01-01", "to_date": "2024-12-31"}
        )
        assert resp.status_code == 200
        # Should have header row only
        lines = [line for line in resp.text.strip().split("\r\n") if line]
        assert len(lines) == 1
        assert lines[0].startswith("id,timestamp,")

    def test_export_empty_result_json(self) -> None:
        """NDJSON export with no matching records should return empty body."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client,
            token,
            {"from_date": "2024-01-01", "to_date": "2024-12-31", "format": "json"},
        )
        assert resp.status_code == 200
        assert resp.text.strip() == ""

    def test_export_csv_serializes_none_as_empty(self) -> None:
        """None values should appear as empty strings in CSV."""
        session = _make_session()
        row = _make_audit_row(
            ip_address=None,
            user_agent=None,
            resource_type=None,
            resource_id=None,
            parameters=None,
            error_detail=None,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client, token, {"from_date": "2024-01-01", "to_date": "2024-12-31"}
        )
        import csv
        import io

        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert rows[0]["ip_address"] == ""
        assert rows[0]["user_agent"] == ""
        assert rows[0]["parameters"] == ""
        assert rows[0]["error_detail"] == ""

    def test_export_csv_serializes_datetime_as_iso(self) -> None:
        """Datetime values should be serialized as ISO 8601 strings."""
        session = _make_session()
        ts = datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC)
        row = _make_audit_row(timestamp=ts)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client, token, {"from_date": "2024-01-01", "to_date": "2024-12-31"}
        )
        import csv
        import io

        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert rows[0]["timestamp"] == "2024-06-15T10:30:00+00:00"

    def test_export_csv_serializes_dict_as_json(self) -> None:
        """Dict values (like parameters) should be serialized as JSON strings."""
        session = _make_session()
        row = _make_audit_row(parameters={"key": "value", "nested": {"a": 1}})
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client, token, {"from_date": "2024-01-01", "to_date": "2024-12-31"}
        )
        import csv
        import io

        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        parsed = json.loads(rows[0]["parameters"])
        assert parsed == {"key": "value", "nested": {"a": 1}}

    def test_export_filename_contains_date_range(self) -> None:
        """Content-Disposition filename should include the requested date range."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        app, _, _ = _build_admin_app(
            valkey_get_return=session,
            db_execute_side_effect=[mock_result],
        )
        client = TestClient(app, raise_server_exceptions=True)
        token = _make_jwt()
        resp = self._post_export(
            client, token, {"from_date": "2024-01-01", "to_date": "2024-12-31"}
        )
        disposition = resp.headers["content-disposition"]
        assert "2024-01-01" in disposition
        assert "2024-12-31" in disposition


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
