"""Integration tests for the events router.

Tests cover:
- Unauthenticated requests → 401
- Authenticated list returns 200 with correct schema
- RBAC scope is passed to the event service
- Single event retrieval
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
from app.routers import events as events_router_module
from app.services.rbac_service import OrgRepoScope

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "ev-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 12345,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(orgs: list[str] | None = None, roles: list[str] | None = None) -> str:
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


def _empty_events_result() -> tuple[list[object], int]:
    """Return the (events, total) tuple that list_events() now produces."""
    return ([], 0)


def _build_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(events_router_module.router, prefix="/api/v1")

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


class TestEventsUnauthenticated:
    def test_list_events_without_auth_returns_401(self):
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/events")
        assert resp.status_code == 401

    def test_get_event_by_id_without_auth_returns_401(self):
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/events/1")
        assert resp.status_code == 401

    def test_get_raw_event_without_auth_returns_401(self):
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/events/1/raw")
        assert resp.status_code == 401


# ─── Authenticated list ───────────────────────────────────────────────────────


class TestEventsAuthenticated:
    def test_list_events_returns_200(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session())
        with patch(
            "app.routers.events.list_events",
            AsyncMock(return_value=_empty_events_result()),
        ):
            with patch(
                "app.routers.events.get_user_scope",
                AsyncMock(
                    return_value=OrgRepoScope(
                        scoped_orgs=["my-org"], scoped_repos=[], scope_type="org"
                    )
                ),
            ):
                client = TestClient(app, raise_server_exceptions=True)
                resp = client.get("/api/v1/events", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 0
        assert data["page"] == 1

    def test_list_events_returns_correct_schema_keys(self):
        token = _make_jwt()
        app, _, _ = _build_app(valkey_session=_make_session())
        with patch(
            "app.routers.events.list_events",
            AsyncMock(return_value=_empty_events_result()),
        ):
            with patch(
                "app.routers.events.get_user_scope",
                AsyncMock(return_value=OrgRepoScope(scope_type="global")),
            ):
                client = TestClient(app, raise_server_exceptions=True)
                resp = client.get("/api/v1/events", cookies={"access_token": token})
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "has_next" in data


# ─── Scope enforcement ────────────────────────────────────────────────────────


class TestEventsScopeEnforcement:
    def test_scoped_user_scope_passed_to_list_events(self):
        """List events must be called with the user's restricted org scope."""
        token = _make_jwt(jti="scope-jti")
        user_scope = OrgRepoScope(scoped_orgs=["my-org"], scoped_repos=[], scope_type="org")
        app, _, _ = _build_app(valkey_session=_make_session(orgs=["my-org"]))

        with patch(
            "app.routers.events.list_events",
            AsyncMock(return_value=_empty_events_result()),
        ) as mock_list:
            with patch(
                "app.routers.events.get_user_scope",
                AsyncMock(return_value=user_scope),
            ):
                client = TestClient(app, raise_server_exceptions=True)
                client.get("/api/v1/events", cookies={"access_token": token})

        assert mock_list.called
        call_kwargs = mock_list.call_args.kwargs
        scope_passed = call_kwargs.get("scope")
        assert scope_passed is not None
        assert not scope_passed.is_global
        assert "my-org" in scope_passed.scoped_orgs

    def test_global_scope_user_scope_is_global(self):
        """sys_admin users should receive global (unrestricted) scope."""
        token = _make_jwt(jti="global-jti")
        global_scope = OrgRepoScope(scope_type="global")
        app, _, _ = _build_app(valkey_session=_make_session(orgs=[], roles=["sys_admin"]))

        with patch(
            "app.routers.events.list_events",
            AsyncMock(return_value=_empty_events_result()),
        ) as mock_list:
            with patch(
                "app.routers.events.get_user_scope",
                AsyncMock(return_value=global_scope),
            ):
                client = TestClient(app, raise_server_exceptions=True)
                client.get("/api/v1/events", cookies={"access_token": token})

        scope_passed = mock_list.call_args.kwargs.get("scope")
        assert scope_passed.is_global


# ─── Pydantic validation of event filter params ──────────────────────────────


class TestEventFilterValidation:
    def test_valid_action_param_accepted(self):
        r"""Pattern ^[\w.*]+$ should accept dot-separated action names."""

        from app.schemas.audit_event import EventListParams

        params = EventListParams(action="repos.create")
        assert params.action == "repos.create"

    def test_sql_injection_in_action_param_rejected(self):
        """SQL injection in action param must be rejected by Pydantic (422)."""
        from pydantic import ValidationError

        from app.schemas.audit_event import EventListParams

        with pytest.raises(ValidationError):
            EventListParams(action="'; DROP TABLE events --")

    def test_sql_injection_semicolon_rejected(self):
        from pydantic import ValidationError

        from app.schemas.audit_event import EventListParams

        with pytest.raises(ValidationError):
            EventListParams(action="repos.create; DELETE FROM events")

    def test_wildcard_glob_in_action_accepted(self):
        from app.schemas.audit_event import EventListParams

        params = EventListParams(action="repos.*")
        assert params.action == "repos.*"

    def test_org_param_html_injection_rejected(self):
        from pydantic import ValidationError

        from app.schemas.audit_event import EventListParams

        with pytest.raises(ValidationError):
            EventListParams(org="<script>alert(1)</script>")

    def test_invalid_geo_country_too_long_rejected(self):
        from pydantic import ValidationError

        from app.schemas.audit_event import EventListParams

        with pytest.raises(ValidationError):
            EventListParams(geo_country_code="USA")  # 3 chars, must be exactly 2
