"""Integration tests for the query router.

Tests cover:
- POST /query/run with valid SQL → 200 + audit trail
- POST /query/run with disallowed table → 400 + audit trail (blocked)
- POST /query/run without auth → 401
- POST /query/run with insufficient role → 403
- POST /query/run with dangerous function → 400
- POST /query/validate with valid/invalid SQL
- GET /query/templates → 200
- POST /query/templates → 201 with created_at populated
- DELETE /query/templates/{id} → 204
- GET /query/templates/{id} → 404 for missing template
- POST /query/templates/{id}/run → executes template SQL
- Audit trail logging for successful and blocked queries
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.models.query_template import QueryTemplate as QueryTemplateModel
from app.routers import query as query_router_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(
    sub: str = "testuser",
    jti: str = "test-jti",
    expired: bool = False,
) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    payload = {"sub": sub, "github_id": 12345, "jti": jti, "exp": exp, "iat": now}
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(
    login: str = "testuser",
    roles: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "github_login": login,
            "github_id": 12345,
            "roles": roles or ["analyst"],
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
    return db


def _make_template_model(
    template_id: int = 1,
    name: str = "Test Query",
    sql: str = "SELECT id FROM events LIMIT 10",
    created_by: str = "testuser",
    description: str | None = None,
    org_slug: str | None = None,
) -> QueryTemplateModel:
    """Create a QueryTemplateModel instance for testing."""
    now = datetime.now(UTC)
    return QueryTemplateModel(
        id=template_id,
        name=name,
        description=description,
        sql=sql,
        created_by=created_by,
        org_slug=org_slug,
        created_at=now,
        updated_at=now,
    )


def _build_query_app(
    valkey_get_return: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(query_router_module.router, prefix="/api/v1")

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


# ─── /query/run ──────────────────────────────────────────────────────────────


class TestRunQuery:
    """Tests for POST /query/run."""

    def test_run_without_auth_returns_401(self):
        app, _, _ = _build_query_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/query/run",
            json={"sql": "SELECT id FROM events LIMIT 10"},
        )
        assert resp.status_code == 401

    def test_run_with_disallowed_table_returns_400(self):
        """Querying a non-allowlisted table must return 400, not 500."""
        jti = "disallowed-tbl"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/query/run",
            json={"sql": "SELECT * FROM audit_events LIMIT 10"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 400
        assert "not in allowed" in resp.json()["detail"]

    def test_run_with_allowed_table_calls_execute(self):
        """Valid SQL with an allowed table should reach execute_query."""
        jti = "valid-sql"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        mock_result = {
            "columns": ["id", "action"],
            "rows": [[1, "repos.create"]],
            "row_count": 1,
            "truncated": False,
            "execution_ms": 5,
            "query_id": "test-uuid",
        }

        with patch(
            "app.routers.query.execute_query",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.post(
                "/api/v1/query/run",
                json={"sql": "SELECT id, action FROM events LIMIT 10"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["row_count"] == 1
        assert data["columns"] == ["id", "action"]

    def test_run_validation_error_returns_400_not_500(self):
        """QueryValidationError must be caught and returned as 400."""
        jti = "val-err"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/query/run",
            json={"sql": "SELECT * FROM pg_catalog.pg_tables"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 400

    def test_run_write_statement_returns_400(self):
        """INSERT/UPDATE/DELETE must be rejected with 400."""
        jti = "write-stmt"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/query/run",
            json={"sql": "INSERT INTO events VALUES (1)"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 400

    def test_run_without_csrf_returns_403(self):
        """POST /query/run requires CSRF double-submit."""
        jti = "no-csrf"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/query/run",
            json={"sql": "SELECT id FROM events LIMIT 10"},
            cookies={"access_token": token},
        )
        assert resp.status_code == 403

    def test_run_viewer_role_returns_403(self):
        """Users without analyst/report_admin/sys_admin cannot run queries."""
        jti = "viewer-jti"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["viewer"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/query/run",
            json={"sql": "SELECT id FROM events LIMIT 10"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403

    def test_run_dangerous_function_returns_400(self):
        """Dangerous functions like pg_read_file must be blocked."""
        jti = "danger-func"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/query/run",
            json={"sql": "SELECT pg_read_file('/etc/passwd') FROM events"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 400
        assert "pg_read_file" in resp.json()["detail"]


class TestRunQueryAuditLogging:
    """Tests for audit trail logging on query execution."""

    def test_successful_query_creates_audit_trail(self):
        """A successful query should log to audit_trail with action_type='query.executed'."""
        jti = "audit-success"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        mock_result = {
            "columns": ["id"],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "execution_ms": 5,
            "query_id": "test-uuid",
        }

        with patch(
            "app.routers.query.execute_query",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.post(
                "/api/v1/query/run",
                json={"sql": "SELECT id FROM events LIMIT 10"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        # Verify db.add was called (audit trail record added)
        assert mock_db.add.called
        audit_obj = mock_db.add.call_args[0][0]
        assert audit_obj.action_type == "query.executed"
        assert audit_obj.outcome == "success"
        assert audit_obj.user_login == "testuser"
        assert audit_obj.resource_type == "query_explorer"
        assert "sql" in audit_obj.parameters
        assert audit_obj.parameters["row_count"] == 1

    def test_blocked_query_creates_audit_trail(self):
        """A blocked query should log to audit_trail with action_type='query.blocked'."""
        jti = "audit-blocked"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/query/run",
            json={"sql": "SELECT * FROM app_settings LIMIT 10"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )

        assert resp.status_code == 400
        # Verify db.add was called (audit trail record added)
        assert mock_db.add.called
        audit_obj = mock_db.add.call_args[0][0]
        assert audit_obj.action_type == "query.blocked"
        assert audit_obj.outcome == "denied"
        assert audit_obj.user_login == "testuser"
        assert "app_settings" in audit_obj.parameters["sql"]
        assert audit_obj.error_detail is not None

    def test_audit_trail_captures_client_ip(self):
        """Audit trail should capture the client IP address."""
        jti = "audit-ip"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        mock_result = {
            "columns": ["id"],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "execution_ms": 5,
            "query_id": "test-uuid",
        }

        with patch(
            "app.routers.query.execute_query",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.post(
                "/api/v1/query/run",
                json={"sql": "SELECT id FROM events LIMIT 10"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        audit_obj = mock_db.add.call_args[0][0]
        # TestClient uses testclient which provides a host
        assert audit_obj.ip_address is not None

    def test_audit_sql_truncated_to_500_chars(self):
        """SQL in audit parameters should be truncated to 500 characters."""
        jti = "audit-trunc"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        # Create a long SQL query that exceeds 500 chars
        long_sql = (
            "SELECT id FROM events WHERE action IN ("
            + ", ".join([f"'action_{i}'" for i in range(200)])
            + ")"
        )

        mock_result = {
            "columns": ["id"],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "execution_ms": 5,
            "query_id": "test-uuid",
        }

        with patch(
            "app.routers.query.execute_query",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = client.post(
                "/api/v1/query/run",
                json={"sql": long_sql},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        audit_obj = mock_db.add.call_args[0][0]
        assert len(audit_obj.parameters["sql"]) <= 500


# ─── /query/validate ──────────────────────────────────────────────────────────


class TestValidateQuery:
    """Tests for POST /query/validate."""

    def test_validate_valid_sql(self):
        jti = "validate-ok"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.post(
            "/api/v1/query/validate",
            json={"sql": "SELECT id FROM events LIMIT 10"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_validate_invalid_table(self):
        jti = "validate-bad"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.post(
            "/api/v1/query/validate",
            json={"sql": "SELECT * FROM pg_stat_activity"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert "error" in data


# ─── /query/templates ─────────────────────────────────────────────────────────


class TestQueryTemplates:
    """Tests for query template CRUD endpoints (DB-backed)."""

    def test_list_templates_empty(self):
        jti = "tpl-list"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get(
            "/api/v1/query/templates",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_templates_returns_persisted(self):
        """Templates fetched from DB are returned in the list."""
        jti = "tpl-list-db"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=True)

        tmpl = _make_template_model(template_id=5, name="Saved Query")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tmpl]
        mock_db.execute = AsyncMock(return_value=mock_result)

        resp = client.get(
            "/api/v1/query/templates",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 5
        assert data[0]["name"] == "Saved Query"

    def test_create_template_includes_created_at(self):
        """Template creation must populate created_at field."""
        jti = "tpl-create"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        now = datetime.now(UTC)

        async def _mock_refresh(obj: object, attribute_names: object = None) -> None:
            """Simulate DB-generated fields after flush."""
            if isinstance(obj, QueryTemplateModel):
                obj.id = 1
                obj.created_at = now
                obj.updated_at = now

        mock_db.refresh = AsyncMock(side_effect=_mock_refresh)

        client = TestClient(app, raise_server_exceptions=True)

        resp = client.post(
            "/api/v1/query/templates",
            json={
                "name": "Test Query",
                "sql": "SELECT id FROM events LIMIT 10",
            },
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Query"
        assert data["created_by"] == "testuser"
        assert "created_at" in data
        assert data["created_at"] is not None
        assert len(data["created_at"]) > 0

    def test_create_template_persists_to_db(self):
        """Template creation should call db.add with a QueryTemplateModel."""
        jti = "tpl-persist"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        now = datetime.now(UTC)

        async def _mock_refresh(obj: object, attribute_names: object = None) -> None:
            if isinstance(obj, QueryTemplateModel):
                obj.id = 1
                obj.created_at = now
                obj.updated_at = now

        mock_db.refresh = AsyncMock(side_effect=_mock_refresh)

        client = TestClient(app, raise_server_exceptions=True)

        resp = client.post(
            "/api/v1/query/templates",
            json={
                "name": "Persist Me",
                "description": "A test template",
                "sql": "SELECT action FROM events LIMIT 5",
            },
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 201
        # Verify db.add was called with a model instance
        assert mock_db.add.called
        added_obj = mock_db.add.call_args[0][0]
        assert isinstance(added_obj, QueryTemplateModel)
        assert added_obj.name == "Persist Me"
        assert added_obj.sql == "SELECT action FROM events LIMIT 5"
        assert added_obj.created_by == "testuser"

    def test_create_template_with_org_slug(self):
        """Template creation should store org_slug when provided."""
        jti = "tpl-org"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        now = datetime.now(UTC)

        async def _mock_refresh(obj: object, attribute_names: object = None) -> None:
            if isinstance(obj, QueryTemplateModel):
                obj.id = 1
                obj.created_at = now
                obj.updated_at = now

        mock_db.refresh = AsyncMock(side_effect=_mock_refresh)

        client = TestClient(app, raise_server_exceptions=True)

        resp = client.post(
            "/api/v1/query/templates",
            json={
                "name": "Org Query",
                "sql": "SELECT id FROM events LIMIT 10",
                "org_slug": "my-org",
            },
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["org_slug"] == "my-org"
        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.org_slug == "my-org"

    def test_get_template_not_found(self):
        jti = "tpl-404"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get(
            "/api/v1/query/templates/9999",
            cookies={"access_token": token},
        )
        assert resp.status_code == 404

    def test_get_template_found(self):
        """GET /templates/{id} returns the template when it exists in DB."""
        jti = "tpl-found"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        tmpl = _make_template_model(template_id=42, name="Found Me")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tmpl
        mock_db.execute = AsyncMock(return_value=mock_result)

        client = TestClient(app, raise_server_exceptions=True)

        resp = client.get(
            "/api/v1/query/templates/42",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 42
        assert data["name"] == "Found Me"

    def test_delete_template(self):
        jti = "tpl-del"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        tmpl = _make_template_model(template_id=1, name="To Delete")

        # First execute (DELETE lookup) returns the template,
        # second execute (GET verification) returns None.
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = tmpl

        result_not_found = MagicMock()
        result_not_found.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[result_found, result_not_found])

        client = TestClient(app, raise_server_exceptions=True)

        # Delete it
        del_resp = client.delete(
            "/api/v1/query/templates/1",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert del_resp.status_code == 204

        # Verify db.delete was called with the template model
        assert mock_db.delete.called

        # Verify it's gone
        get_resp = client.get(
            "/api/v1/query/templates/1",
            cookies={"access_token": token},
        )
        assert get_resp.status_code == 404

    def test_delete_template_not_found(self):
        """DELETE on a non-existent template returns 404."""
        jti = "tpl-del-404"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.delete(
            "/api/v1/query/templates/9999",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404

    def test_run_template_executes_sql(self):
        """POST /templates/{id}/run fetches SQL from DB and executes it."""
        jti = "tpl-run"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        tmpl = _make_template_model(
            template_id=10,
            name="Run Me",
            sql="SELECT id FROM events LIMIT 5",
        )

        # First execute returns the template (lookup),
        # subsequent executes are for get_user_scope / execute_query.
        result_found = MagicMock()
        result_found.scalar_one_or_none.return_value = tmpl

        # Default result for scope queries
        result_default = MagicMock()
        result_default.scalars.return_value.all.return_value = []
        result_default.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[result_found, result_default])

        client = TestClient(app, raise_server_exceptions=False)

        mock_query_result = {
            "columns": ["id"],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "execution_ms": 3,
            "query_id": "tpl-run-uuid",
        }

        with patch(
            "app.routers.query.execute_query",
            new_callable=AsyncMock,
            return_value=mock_query_result,
        ):
            resp = client.post(
                "/api/v1/query/templates/10/run",
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["row_count"] == 1

    def test_run_template_not_found(self):
        """POST /templates/{id}/run returns 404 for missing template."""
        jti = "tpl-run-404"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["sys_admin"])
        app, _, _ = _build_query_app(valkey_get_return=session)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/query/templates/9999/run",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404
