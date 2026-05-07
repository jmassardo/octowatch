"""Tests for saved query endpoints in the query router.

Covers:
- POST /query/saved — create a saved query
- GET /query/saved — list user's saved queries
- PUT /query/saved/{id} — update a saved query
- DELETE /query/saved/{id} — delete a saved query
- POST /query/saved/{id}/share — share a query
- GET /query/shared — list shared queries
- POST /query/saved/{id}/schedule — schedule a query
- GET /query/schema — return schema metadata
- Ownership checks (403 for non-owners)
- 404 for non-existent queries
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.models.saved_query import SavedQuery as SavedQueryModel
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


def _make_saved_query(
    query_id: int = 1,
    name: str = "Test Saved Query",
    sql_text: str = "SELECT id FROM events LIMIT 10",
    owner_login: str = "testuser",
    description: str | None = None,
    is_shared: bool = False,
    shared_with: list[str] | None = None,
    tags: list[str] | None = None,
    schedule_cron: str | None = None,
    schedule_enabled: bool = False,
) -> SavedQueryModel:
    """Create a SavedQueryModel instance for testing."""
    now = datetime.now(UTC)
    return SavedQueryModel(
        id=query_id,
        name=name,
        description=description,
        sql_text=sql_text,
        owner_login=owner_login,
        is_shared=is_shared,
        shared_with=shared_with,
        tags=tags,
        schedule_cron=schedule_cron,
        schedule_enabled=schedule_enabled,
        last_run_at=None,
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


# ─── POST /query/saved ───────────────────────────────────────────────────────


class TestCreateSavedQuery:
    """Tests for POST /query/saved."""

    def test_create_saved_query_success(self):
        """POST /query/saved creates a new saved query."""
        jti = "saved-create"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        now = datetime.now(UTC)

        # After flush+refresh, the mock should return the saved object
        mock_db.refresh = AsyncMock(return_value=None)

        # Mock the add to capture the object
        added_objects: list[SavedQueryModel] = []

        def capture_add(obj: SavedQueryModel) -> None:
            added_objects.append(obj)
            # Set attributes that would be set by DB
            obj.id = 1
            obj.created_at = now
            obj.updated_at = now
            obj.is_shared = False
            obj.schedule_enabled = False

        mock_db.add = capture_add

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/query/saved",
            json={
                "name": "My Query",
                "description": "Test desc",
                "sql_text": "SELECT id FROM events LIMIT 10",
                "tags": ["security", "audit"],
            },
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Query"
        assert data["description"] == "Test desc"
        assert data["owner_login"] == "testuser"
        assert data["tags"] == ["security", "audit"]

    def test_create_saved_query_no_auth(self):
        """POST /query/saved without auth returns 401."""
        app, _, _ = _build_query_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/query/saved",
            json={
                "name": "x",
                "sql_text": "SELECT id FROM events LIMIT 10",
            },
        )
        assert resp.status_code == 401


# ─── GET /query/saved ─────────────────────────────────────────────────────────


class TestListSavedQueries:
    """Tests for GET /query/saved."""

    def test_list_saved_queries_empty(self):
        """GET /query/saved returns empty list when no saved queries."""
        jti = "saved-list-empty"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/query/saved",
            cookies={"access_token": token, "csrf_token": "tok"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_saved_queries_returns_data(self):
        """GET /query/saved returns user's saved queries."""
        jti = "saved-list-data"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        saved = _make_saved_query(query_id=1, name="Q1")
        result = MagicMock()
        result.scalars.return_value.all.return_value = [saved]
        mock_db.execute = AsyncMock(return_value=result)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/query/saved",
            cookies={"access_token": token, "csrf_token": "tok"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Q1"


# ─── PUT /query/saved/{id} ───────────────────────────────────────────────────


class TestUpdateSavedQuery:
    """Tests for PUT /query/saved/{id}."""

    def test_update_saved_query_not_found(self):
        """PUT /query/saved/{id} returns 404 for non-existent query."""
        jti = "saved-update-404"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put(
            "/api/v1/query/saved/999",
            json={"name": "Updated"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404

    def test_update_saved_query_not_owner(self):
        """PUT /query/saved/{id} returns 403 if not owner."""
        jti = "saved-update-403"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        saved = _make_saved_query(query_id=1, owner_login="otheruser")
        result = MagicMock()
        result.scalar_one_or_none.return_value = saved
        mock_db.execute = AsyncMock(return_value=result)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put(
            "/api/v1/query/saved/1",
            json={"name": "Updated"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403


# ─── DELETE /query/saved/{id} ─────────────────────────────────────────────────


class TestDeleteSavedQuery:
    """Tests for DELETE /query/saved/{id}."""

    def test_delete_saved_query_not_found(self):
        """DELETE /query/saved/{id} returns 404 for non-existent query."""
        jti = "saved-del-404"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete(
            "/api/v1/query/saved/999",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404

    def test_delete_saved_query_not_owner(self):
        """DELETE /query/saved/{id} returns 403 if not owner."""
        jti = "saved-del-403"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        saved = _make_saved_query(query_id=1, owner_login="otheruser")
        result = MagicMock()
        result.scalar_one_or_none.return_value = saved
        mock_db.execute = AsyncMock(return_value=result)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete(
            "/api/v1/query/saved/1",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403

    def test_delete_saved_query_success(self):
        """DELETE /query/saved/{id} returns 204 on success."""
        jti = "saved-del-ok"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        saved = _make_saved_query(query_id=1, owner_login="testuser")
        result = MagicMock()
        result.scalar_one_or_none.return_value = saved
        mock_db.execute = AsyncMock(return_value=result)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete(
            "/api/v1/query/saved/1",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 204


# ─── POST /query/saved/{id}/share ─────────────────────────────────────────────


class TestShareQuery:
    """Tests for POST /query/saved/{id}/share."""

    def test_share_query_not_found(self):
        """POST /query/saved/{id}/share returns 404 for non-existent query."""
        jti = "share-404"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/query/saved/999/share",
            json={"logins": ["bob"]},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404

    def test_share_query_not_owner(self):
        """POST /query/saved/{id}/share returns 403 for non-owner."""
        jti = "share-403"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        saved = _make_saved_query(query_id=1, owner_login="otheruser")
        result = MagicMock()
        result.scalar_one_or_none.return_value = saved
        mock_db.execute = AsyncMock(return_value=result)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/query/saved/1/share",
            json={"logins": ["bob"]},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403


# ─── GET /query/shared ────────────────────────────────────────────────────────


class TestListSharedQueries:
    """Tests for GET /query/shared."""

    def test_list_shared_queries_empty(self):
        """GET /query/shared returns empty list by default."""
        jti = "shared-list"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/query/shared",
            cookies={"access_token": token, "csrf_token": "tok"},
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ─── POST /query/saved/{id}/schedule ──────────────────────────────────────────


class TestScheduleQuery:
    """Tests for POST /query/saved/{id}/schedule."""

    def test_schedule_query_not_found(self):
        """POST /query/saved/{id}/schedule returns 404 for non-existent query."""
        jti = "sched-404"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/query/saved/999/schedule",
            json={"cron": "0 9 * * 1", "enabled": True},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404

    def test_schedule_query_not_owner(self):
        """POST /query/saved/{id}/schedule returns 403 for non-owner."""
        jti = "sched-403"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, mock_db, _ = _build_query_app(valkey_get_return=session)

        saved = _make_saved_query(query_id=1, owner_login="otheruser")
        result = MagicMock()
        result.scalar_one_or_none.return_value = saved
        mock_db.execute = AsyncMock(return_value=result)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/query/saved/1/schedule",
            json={"cron": "0 9 * * 1", "enabled": True},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403


# ─── GET /query/schema ────────────────────────────────────────────────────────


class TestGetSchema:
    """Tests for GET /query/schema."""

    def test_get_schema_returns_tables(self):
        """GET /query/schema returns allowed tables with columns."""
        jti = "schema-get"
        token = _make_jwt(jti=jti)
        session = _make_session(roles=["analyst"])
        app, _, _ = _build_query_app(valkey_get_return=session)

        # Reset schema cache
        query_router_module._SCHEMA_CACHE = None

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/query/schema",
            cookies={"access_token": token, "csrf_token": "tok"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        table_names = {t["table"] for t in data}
        assert "events" in table_names
        assert "detections" in table_names

        # Check that events table has columns
        events_table = next(t for t in data if t["table"] == "events")
        col_names = {c["name"] for c in events_table["columns"]}
        assert "id" in col_names
        assert "action" in col_names
        assert "actor" in col_names

    def test_get_schema_no_auth(self):
        """GET /query/schema without auth returns 401."""
        app, _, _ = _build_query_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/query/schema")
        assert resp.status_code == 401
