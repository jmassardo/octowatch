"""Tests for the copilot_sessions router and service layer.

Tests cover:
- Overview endpoint happy path, org scoping, and permission denial
- Detail endpoint happy path, org scoping, not-found, and permission denial
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import copilot_sessions as copilot_sessions_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"

_RBAC_PATCH = "app.routers.copilot_sessions.rbac_service.get_scoped_orgs"
_PERMISSION_PATCH = "app.services.rbac_service.check_permission"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "cs-jti") -> str:
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
    mock_result.mappings.return_value.first.return_value = None
    mock_result.mappings.return_value.all.return_value = []
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _build_app(valkey_session: str | None = None) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(copilot_sessions_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Unauthenticated requests ─────────────────────────────────────────────────


class TestUnauthenticated:
    def test_overview_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/sessions/overview")
        assert resp.status_code == 401

    def test_detail_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/sessions/abc-123")
        assert resp.status_code == 401


# ─── Permission denial ─────────────────────────────────────────────────────────


class TestPermissionDenial:
    """403 when the user's roles do not grant copilot_sessions:view."""

    def test_overview_returns_403_when_permission_denied(self) -> None:
        token = _make_jwt(jti="noperm-overview")
        session = _make_session(roles=["viewer"])
        app, _, _ = _build_app(valkey_session=session)

        with patch(_PERMISSION_PATCH, AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/copilot/sessions/overview",
                cookies={"access_token": token},
            )
        assert resp.status_code == 403

    def test_detail_returns_403_when_permission_denied(self) -> None:
        token = _make_jwt(jti="noperm-detail")
        session = _make_session(roles=["viewer"])
        app, _, _ = _build_app(valkey_session=session)

        with patch(_PERMISSION_PATCH, AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/copilot/sessions/abc-123",
                cookies={"access_token": token},
            )
        assert resp.status_code == 403


# ─── RBAC org-scope enforcement ────────────────────────────────────────────────


class TestRbacEnforcement:
    """403 when the user has no org access, even with the right permission."""

    def test_overview_returns_403_when_no_orgs(self) -> None:
        token = _make_jwt(jti="noorgs-overview")
        session = _make_session(orgs=["my-org"])
        app, _, _ = _build_app(valkey_session=session)

        with (
            patch(_PERMISSION_PATCH, AsyncMock(return_value=True)),
            patch(_RBAC_PATCH, AsyncMock(return_value=[])),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/copilot/sessions/overview",
                cookies={"access_token": token},
            )
        assert resp.status_code == 403

    def test_detail_returns_403_when_no_orgs(self) -> None:
        token = _make_jwt(jti="noorgs-detail")
        session = _make_session(orgs=["my-org"])
        app, _, _ = _build_app(valkey_session=session)

        with (
            patch(_PERMISSION_PATCH, AsyncMock(return_value=True)),
            patch(_RBAC_PATCH, AsyncMock(return_value=[])),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/copilot/sessions/abc-123",
                cookies={"access_token": token},
            )
        assert resp.status_code == 403


# ─── Overview endpoint ─────────────────────────────────────────────────────────


class TestOverview:
    def test_overview_returns_200_with_empty_data(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        with (
            patch(_PERMISSION_PATCH, AsyncMock(return_value=True)),
            patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/copilot/sessions/overview",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_sessions"] == 0
        assert body["avg_duration_seconds"] is None
        assert body["top_models"] == []
        assert body["top_editors"] == []
        assert body["lookback_days"] == 30

    def test_overview_returns_200_with_aggregated_data(self) -> None:
        session = _make_session()
        app, mock_db, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        stats_result = MagicMock()
        stats_result.mappings.return_value.first.return_value = {
            "total_sessions": 42,
            "avg_duration_seconds": 123.45,
        }
        models_result = MagicMock()
        models_result.mappings.return_value.all.return_value = [
            {"model": "gpt-5", "session_count": 30},
            {"model": "claude", "session_count": 12},
        ]
        editors_result = MagicMock()
        editors_result.mappings.return_value.all.return_value = [
            {"editor": "vscode", "session_count": 40},
        ]
        mock_db.execute = AsyncMock(side_effect=[stats_result, models_result, editors_result])

        with (
            patch(_PERMISSION_PATCH, AsyncMock(return_value=True)),
            patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/copilot/sessions/overview?days=7",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_sessions"] == 42
        assert body["avg_duration_seconds"] == 123.45
        assert body["top_models"] == [
            {"model": "gpt-5", "count": 30},
            {"model": "claude", "count": 12},
        ]
        assert body["top_editors"] == [{"editor": "vscode", "count": 40}]
        assert body["lookback_days"] == 7


# ─── Detail endpoint ────────────────────────────────────────────────────────────


class TestDetail:
    def test_detail_returns_404_when_session_not_found(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        with (
            patch(_PERMISSION_PATCH, AsyncMock(return_value=True)),
            patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/copilot/sessions/missing-session",
                cookies={"access_token": token},
            )
        assert resp.status_code == 404

    def test_detail_returns_200_with_session_and_turns(self) -> None:
        session = _make_session()
        app, mock_db, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        now = datetime.now(UTC)
        session_result = MagicMock()
        session_result.mappings.return_value.first.return_value = {
            "id": 1,
            "session_id": "abc-123",
            "created_at": now,
            "enterprise": "my-enterprise",
            "org": "my-org",
            "actor": "octocat",
            "actor_id": 99,
            "editor": "vscode",
            "editor_version": "1.90",
            "copilot_version": "1.0",
            "model": "gpt-5",
            "language": "python",
            "repository": "my-org/repo",
            "turn_count": 1,
            "tool_call_count": 0,
            "total_tokens_in": 10,
            "total_tokens_out": 20,
            "duration_seconds": 30,
            "started_at": now,
            "ended_at": now,
        }
        turns_result = MagicMock()
        turns_result.mappings.return_value.all.return_value = [
            {
                "turn_index": 0,
                "created_at": now,
                "prompt_text": "hello",
                "prompt_tokens": 5,
                "response_text": "world",
                "response_tokens": 5,
                "model": "gpt-5",
                "finish_reason": "stop",
                "latency_ms": 100,
                "tool_calls": None,
                "references": None,
                "annotations": None,
            }
        ]
        mock_db.execute = AsyncMock(side_effect=[session_result, turns_result])

        with (
            patch(_PERMISSION_PATCH, AsyncMock(return_value=True)),
            patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/copilot/sessions/abc-123",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "abc-123"
        assert body["org"] == "my-org"
        assert len(body["turns"]) == 1
        assert body["turns"][0]["prompt_text"] == "hello"


# ─── Service-level unit tests ─────────────────────────────────────────────────


class TestServiceEmptyOrgScope:
    """Both service functions must short-circuit when scoped_orgs is empty."""

    def test_overview_with_no_orgs_returns_empty_without_querying(self) -> None:
        import asyncio

        from app.services.copilot_session_service import get_copilot_sessions_overview

        mock_db = AsyncMock()
        result = asyncio.run(get_copilot_sessions_overview(mock_db, [], days=30))
        assert result["total_sessions"] == 0
        mock_db.execute.assert_not_called()

    def test_detail_with_no_orgs_returns_none_without_querying(self) -> None:
        import asyncio

        from app.services.copilot_session_service import get_copilot_session_detail

        mock_db = AsyncMock()
        result = asyncio.run(get_copilot_session_detail(mock_db, [], "abc-123"))
        assert result is None
        mock_db.execute.assert_not_called()
