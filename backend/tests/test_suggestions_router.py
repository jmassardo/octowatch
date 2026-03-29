"""Integration tests for the suggestions router.

Tests cover:
- Unauthenticated requests → 401
- Authenticated requests with scoped orgs → 200 with correct schema
- Empty scoped orgs → empty lists
- Dynamic fields are prefixed with 'data.'
- Static fields are always present
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import suggestions as suggestions_router_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "sug-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 12345,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(
    orgs: list[str] | None = None,
    roles: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "github_login": "testuser",
            "github_id": 12345,
            "roles": roles or ["analyst"],
            "scoped_orgs": orgs or ["my-org"],
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


def _build_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(suggestions_router_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Unauthenticated requests ─────────────────────────────────────────────────


class TestSuggestionsUnauthenticated:
    def test_actions_without_auth_returns_401(self):
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/suggestions/actions")
        assert resp.status_code == 401

    def test_fields_without_auth_returns_401(self):
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/suggestions/fields")
        assert resp.status_code == 401

    def test_actors_without_auth_returns_401(self):
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/suggestions/actors")
        assert resp.status_code == 401


# ─── Empty scoped orgs ────────────────────────────────────────────────────────


class TestSuggestionsEmptyScope:
    def test_actions_empty_scope_returns_empty_list(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=[]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/suggestions/actions",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        assert resp.json() == {"actions": []}

    def test_fields_empty_scope_returns_static_only(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=[]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/suggestions/fields",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["fields"] == [
            "actor",
            "action",
            "org",
            "repo",
            "source_ip",
            "created_at",
        ]

    def test_actors_empty_scope_returns_empty_list(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=[]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/suggestions/actors",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        assert resp.json() == {"actors": []}


# ─── Authenticated with data ──────────────────────────────────────────────────


class TestSuggestionsAuthenticated:
    def test_actions_returns_distinct_values(self):
        token = _make_jwt()
        app, mock_db, _ = _build_app(valkey_session=_make_session())

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("git.clone",), ("git.push",), ("repo.create",)]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/suggestions/actions",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["actions"] == ["git.clone", "git.push", "repo.create"]

    def test_actors_returns_distinct_values(self):
        token = _make_jwt()
        app, mock_db, _ = _build_app(valkey_session=_make_session())

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("alice",), ("github-actions[bot]",)]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/suggestions/actors",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["actors"] == ["alice", "github-actions[bot]"]

    def test_fields_returns_static_and_dynamic(self):
        token = _make_jwt()
        app, mock_db, _ = _build_app(valkey_session=_make_session())

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("repository",), ("user_agent",)]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/suggestions/fields",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        fields = data["fields"]
        # Static fields come first
        assert fields[:6] == [
            "actor",
            "action",
            "org",
            "repo",
            "source_ip",
            "created_at",
        ]
        # Dynamic fields are prefixed and sorted
        assert "data.repository" in fields
        assert "data.user_agent" in fields

    def test_fields_dynamic_keys_are_sorted(self):
        token = _make_jwt()
        app, mock_db, _ = _build_app(valkey_session=_make_session())

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("zebra",), ("apple",), ("mango",)]
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/suggestions/fields",
                cookies={"access_token": token},
            )

        data = resp.json()
        dynamic = [f for f in data["fields"] if f.startswith("data.")]
        assert dynamic == ["data.apple", "data.mango", "data.zebra"]


# ─── DB is called with scoped_orgs param ──────────────────────────────────────


class TestSuggestionsScopeEnforcement:
    def test_actions_calls_get_scoped_orgs(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session(orgs=["my-org"]))

        mock_get_scoped = AsyncMock(return_value=["my-org"])
        with patch("app.routers.suggestions.get_scoped_orgs", mock_get_scoped):
            client = TestClient(app, raise_server_exceptions=True)
            client.get(
                "/api/v1/suggestions/actions",
                cookies={"access_token": token},
            )

        assert mock_get_scoped.called

    def test_actors_calls_get_scoped_orgs(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session(orgs=["my-org"]))

        mock_get_scoped = AsyncMock(return_value=["my-org"])
        with patch("app.routers.suggestions.get_scoped_orgs", mock_get_scoped):
            client = TestClient(app, raise_server_exceptions=True)
            client.get(
                "/api/v1/suggestions/actors",
                cookies={"access_token": token},
            )

        assert mock_get_scoped.called

    def test_fields_calls_get_scoped_orgs(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session(orgs=["my-org"]))

        mock_get_scoped = AsyncMock(return_value=["my-org"])
        with patch("app.routers.suggestions.get_scoped_orgs", mock_get_scoped):
            client = TestClient(app, raise_server_exceptions=True)
            client.get(
                "/api/v1/suggestions/fields",
                cookies={"access_token": token},
            )

        assert mock_get_scoped.called


# ─── Response schema validation ───────────────────────────────────────────────


class TestSuggestionsResponseSchema:
    @pytest.mark.parametrize(
        "endpoint",
        ["/api/v1/suggestions/actions", "/api/v1/suggestions/actors"],
    )
    def test_response_is_dict_with_list_of_strings(self, endpoint: str):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=[]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(endpoint, cookies={"access_token": token})

        data = resp.json()
        assert isinstance(data, dict)
        key = list(data.keys())[0]
        assert isinstance(data[key], list)

    def test_fields_response_has_fields_key(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.suggestions.get_scoped_orgs",
            AsyncMock(return_value=[]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/suggestions/fields",
                cookies={"access_token": token},
            )

        data = resp.json()
        assert "fields" in data
        assert isinstance(data["fields"], list)
        assert all(isinstance(f, str) for f in data["fields"])
