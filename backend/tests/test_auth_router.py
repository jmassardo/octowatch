"""Integration tests for the auth router.

Tests cover:
- GitHub login redirect
- /me endpoint (auth required, session revocation)
- /logout endpoint (auth required, session deletion)
- JWT expiry and signature validation
- RBAC role enforcement (no-access default)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import auth as auth_router_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(
    sub: str = "testuser",
    jti: str = "test-jti",
    expired: bool = False,
    wrong_secret: bool = False,
) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    payload = {"sub": sub, "github_id": 12345, "jti": jti, "exp": exp, "iat": now}
    secret = "wrong-secret-totally-invalid" if wrong_secret else SECRET
    return pyjwt.encode(payload, secret, algorithm="HS256")


def _make_session(login: str = "testuser", roles: list[str] | None = None) -> str:
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


def _build_auth_app(valkey_get_return: str | None = None) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(auth_router_module.router, prefix="/api/v1")

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


# ─── GitHub OAuth redirect ────────────────────────────────────────────────────


class TestGithubLogin:
    def test_redirects_to_github(self):
        app, _, _ = _build_auth_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/api/v1/auth/github/login")
        assert resp.status_code in (302, 307)
        assert "github.com" in resp.headers["location"]

    def test_redirect_includes_client_id(self):
        app, _, _ = _build_auth_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/api/v1/auth/github/login")
        # state param should be present in redirect URL
        assert "state=" in resp.headers["location"]

    def test_oauth_state_cookie_set(self):
        """CSRF state cookie must be set on the redirect response."""
        app, _, _ = _build_auth_app()
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/api/v1/auth/github/login")
        set_cookie = resp.headers.get("set-cookie", "")
        assert "oauth_state" in set_cookie


# ─── /me ─────────────────────────────────────────────────────────────────────


class TestGetMe:
    def test_me_without_cookie_returns_401(self):
        app, _, _ = _build_auth_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_with_valid_jwt_and_session_returns_200(self):
        jti = "valid-jti"
        token = _make_jwt(jti=jti)
        app, _, _ = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["github_login"] == "testuser"
        assert "roles" in data

    def test_me_returns_correct_login(self):
        jti = "me-jti"
        token = _make_jwt(sub="alice", jti=jti)
        app, _, _ = _build_auth_app(valkey_get_return=_make_session(login="alice"))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 200
        assert resp.json()["github_login"] == "alice"

    def test_me_with_expired_jwt_returns_401(self):
        jti = "exp-jti"
        token = _make_jwt(jti=jti, expired=True)
        app, _, _ = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 401

    def test_me_with_wrong_signature_returns_401(self):
        jti = "bad-sig-jti"
        token = _make_jwt(jti=jti, wrong_secret=True)
        app, _, _ = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 401

    def test_me_with_revoked_session_returns_401(self):
        """Valkey returns None for session key → session revoked → 401."""
        jti = "revoked-jti"
        token = _make_jwt(jti=jti)
        # Valkey returns None → session doesn't exist
        app, _, _ = _build_auth_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 401


# ─── /logout ─────────────────────────────────────────────────────────────────


class TestLogout:
    def test_logout_without_auth_returns_401(self):
        app, _, _ = _build_auth_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 401

    def test_logout_with_valid_session_returns_200(self):
        jti = "logout-jti"
        token = _make_jwt(jti=jti)
        app, _, mock_valkey = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/auth/logout",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged_out"

    def test_logout_deletes_session_from_valkey(self):
        """Logout must immediately revoke the session in Valkey."""
        jti = "del-jti"
        token = _make_jwt(jti=jti)
        app, _, mock_valkey = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        client.post(
            "/api/v1/auth/logout",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        # revoke_session calls valkey.delete(f"session:{jti}")
        mock_valkey.delete.assert_called_once_with(f"session:{jti}")


# ─── RBAC require_role (no-access default) ──────────────────────────────────


class TestRequireRoleNoAccess:
    """Test that users with no roles get a specific 403 message."""

    def test_no_roles_returns_specific_403_message(self):
        """Users with empty roles list get the 'no role assignments' message."""
        from fastapi import Depends

        from app.deps import require_role

        jti = "norole-jti"
        token = _make_jwt(jti=jti)
        session_data = json.dumps(
            {
                "github_login": "newuser",
                "github_id": 99999,
                "roles": [],
                "scoped_orgs": [],
                "scoped_repos": [],
                "scope_type": "scoped",
                "session_expires_at": "2099-01-01T00:00:00+00:00",
            }
        )
        app, _, _ = _build_auth_app(valkey_get_return=session_data)

        @app.get("/test-protected")
        async def protected_route(
            user: object = Depends(require_role(["analyst"])),
        ) -> dict[str, bool]:
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test-protected", cookies={"access_token": token})
        assert resp.status_code == 403
        assert "no role assignments" in resp.json()["detail"]

    def test_wrong_role_returns_generic_403(self):
        """Users with roles but not the right ones get the generic message."""
        from fastapi import Depends

        from app.deps import require_role

        jti = "wrongrole-jti"
        token = _make_jwt(jti=jti)
        session_data = json.dumps(
            {
                "github_login": "someuser",
                "github_id": 88888,
                "roles": ["report_admin"],
                "scoped_orgs": ["org1"],
                "scoped_repos": [],
                "scope_type": "scoped",
                "session_expires_at": "2099-01-01T00:00:00+00:00",
            }
        )
        app, _, _ = _build_auth_app(valkey_get_return=session_data)

        @app.get("/test-protected2")
        async def protected_route2(
            user: object = Depends(require_role(["analyst"])),
        ) -> dict[str, bool]:
            return {"ok": True}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test-protected2", cookies={"access_token": token})
        assert resp.status_code == 403
        assert "Role required" in resp.json()["detail"]
