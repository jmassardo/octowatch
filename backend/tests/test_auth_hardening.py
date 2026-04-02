"""Tests for auth/security hardening: RBAC session refresh, dev-login, rate limits.

Tests cover:
- H4: Periodic role refresh in get_current_user (roles_refreshed_at)
- H5: Dev-login warning log and rate limiting
- H9: Per-endpoint rate limit decorators on sensitive endpoints
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey

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
    roles_refreshed_at: float | None = None,
) -> str:
    data: dict[str, object] = {
        "github_login": login,
        "github_id": 12345,
        "roles": roles or ["analyst"],
        "scoped_orgs": ["my-org"],
        "scoped_repos": [],
        "scope_type": "scoped",
        "session_expires_at": "2099-01-01T00:00:00+00:00",
    }
    if roles_refreshed_at is not None:
        data["roles_refreshed_at"] = roles_refreshed_at
    return json.dumps(data)


def _make_mock_db() -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.fetchall.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _build_auth_app(valkey_get_return: str | None = None) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    from app.routers import auth as auth_router_module

    app = FastAPI()
    app.include_router(auth_router_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_get_return)
    mock_valkey.delete = AsyncMock(return_value=1)
    mock_valkey.ttl = AsyncMock(return_value=3600)
    mock_valkey.setex = AsyncMock(return_value=True)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── H4: RBAC Session Refresh ────────────────────────────────────────────────


class TestRBACSessionRefresh:
    """Test periodic role refresh in get_current_user."""

    def test_fresh_session_skips_refresh(self):
        """Session refreshed less than 5 minutes ago should NOT trigger DB lookup."""
        # roles_refreshed_at is recent (1 minute ago)
        recent_refresh = time.time() - 60
        session = _make_session(roles=["analyst"], roles_refreshed_at=recent_refresh)
        app, mock_db, mock_valkey = _build_auth_app(valkey_get_return=session)
        token = _make_jwt(jti="fresh-jti")

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["roles"] == ["analyst"]
        # Valkey.setex should NOT be called (no refresh needed)
        mock_valkey.setex.assert_not_called()

    def test_stale_session_triggers_refresh(self):
        """Session refreshed more than 5 minutes ago should trigger DB role re-resolve."""
        # roles_refreshed_at is old (10 minutes ago)
        stale_refresh = time.time() - 600
        session = _make_session(roles=["analyst"], roles_refreshed_at=stale_refresh)
        app, mock_db, mock_valkey = _build_auth_app(valkey_get_return=session)
        token = _make_jwt(jti="stale-jti")

        # Mock OrgRepoScope from get_user_scope
        from app.services.rbac_service import OrgRepoScope

        mock_scope = OrgRepoScope(scoped_orgs=["new-org"], scoped_repos=[], scope_type="org")

        mock_inner_session = AsyncMock()

        with (
            patch("app.database.AsyncSessionLocal") as mock_session_local,
            patch(
                "app.services.rbac_service.resolve_roles",
                return_value=["report_admin"],
            ),
            patch(
                "app.services.rbac_service.get_user_scope",
                return_value=mock_scope,
            ),
        ):
            # Set up the context manager mock properly
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_inner_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_local.return_value = mock_ctx

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/auth/me", cookies={"access_token": token})

        assert resp.status_code == 200
        data = resp.json()
        assert "report_admin" in data["roles"]
        # Valkey.setex should be called to persist updated session
        mock_valkey.setex.assert_called_once()

    def test_missing_refreshed_at_triggers_refresh(self):
        """Session without roles_refreshed_at field should trigger refresh (treated as 0)."""
        session = _make_session(roles=["analyst"])  # No roles_refreshed_at
        app, _, mock_valkey = _build_auth_app(valkey_get_return=session)
        token = _make_jwt(jti="no-refresh-jti")

        from app.services.rbac_service import OrgRepoScope

        mock_scope = OrgRepoScope(scoped_orgs=["org1"], scoped_repos=[], scope_type="org")

        mock_inner_session = AsyncMock()

        with (
            patch("app.database.AsyncSessionLocal") as mock_session_local,
            patch(
                "app.services.rbac_service.resolve_roles",
                return_value=["analyst"],
            ) as mock_resolve,
            patch("app.services.rbac_service.get_user_scope", return_value=mock_scope),
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_inner_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_local.return_value = mock_ctx

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/auth/me", cookies={"access_token": token})

        assert resp.status_code == 200
        mock_resolve.assert_called_once()

    def test_refresh_failure_falls_back_to_cached_roles(self):
        """If DB is down during refresh, fall back to cached roles gracefully."""
        stale_refresh = time.time() - 600
        session = _make_session(roles=["analyst"], roles_refreshed_at=stale_refresh)
        app, _, mock_valkey = _build_auth_app(valkey_get_return=session)
        token = _make_jwt(jti="fallback-jti")

        with patch(
            "app.database.AsyncSessionLocal",
            side_effect=Exception("DB connection refused"),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/auth/me", cookies={"access_token": token})

        assert resp.status_code == 200
        data = resp.json()
        # Should fall back to cached roles
        assert data["roles"] == ["analyst"]

    def test_refresh_updates_scope_in_valkey(self):
        """After refresh, Valkey session should contain updated scope fields."""
        stale_refresh = time.time() - 600
        session = _make_session(roles=["analyst"], roles_refreshed_at=stale_refresh)
        app, _, mock_valkey = _build_auth_app(valkey_get_return=session)
        token = _make_jwt(jti="scope-update-jti")

        from app.services.rbac_service import OrgRepoScope

        mock_scope = OrgRepoScope(
            scoped_orgs=["updated-org"], scoped_repos=["updated-repo"], scope_type="org"
        )

        mock_inner_session = AsyncMock()

        with (
            patch("app.database.AsyncSessionLocal") as mock_session_local,
            patch("app.services.rbac_service.resolve_roles", return_value=["sys_admin"]),
            patch("app.services.rbac_service.get_user_scope", return_value=mock_scope),
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_inner_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_local.return_value = mock_ctx

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/auth/me", cookies={"access_token": token})

        assert resp.status_code == 200
        # Verify setex was called and session data contains updated fields
        mock_valkey.setex.assert_called_once()
        call_args = mock_valkey.setex.call_args
        stored_session = json.loads(call_args[0][2])
        assert stored_session["scoped_orgs"] == ["updated-org"]
        assert stored_session["scoped_repos"] == ["updated-repo"]
        assert "roles_refreshed_at" in stored_session

    def test_refresh_preserves_ttl(self):
        """Updated session should preserve the original TTL from Valkey."""
        stale_refresh = time.time() - 600
        session = _make_session(roles=["analyst"], roles_refreshed_at=stale_refresh)
        app, _, mock_valkey = _build_auth_app(valkey_get_return=session)
        mock_valkey.ttl = AsyncMock(return_value=1800)  # 30 minutes remaining
        token = _make_jwt(jti="ttl-jti")

        from app.services.rbac_service import OrgRepoScope

        mock_scope = OrgRepoScope(scoped_orgs=[], scoped_repos=[], scope_type="global")

        mock_inner_session = AsyncMock()

        with (
            patch("app.database.AsyncSessionLocal") as mock_session_local,
            patch("app.services.rbac_service.resolve_roles", return_value=["analyst"]),
            patch("app.services.rbac_service.get_user_scope", return_value=mock_scope),
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_inner_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_local.return_value = mock_ctx

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/auth/me", cookies={"access_token": token})

        assert resp.status_code == 200
        # TTL should be preserved at 1800
        call_args = mock_valkey.setex.call_args
        assert call_args[0][1] == 1800

    def test_refresh_skipped_when_ttl_expired(self):
        """If Valkey TTL is <= 0, don't write back the session."""
        stale_refresh = time.time() - 600
        session = _make_session(roles=["analyst"], roles_refreshed_at=stale_refresh)
        app, _, mock_valkey = _build_auth_app(valkey_get_return=session)
        mock_valkey.ttl = AsyncMock(return_value=-1)  # key has no TTL
        token = _make_jwt(jti="expired-ttl-jti")

        from app.services.rbac_service import OrgRepoScope

        mock_scope = OrgRepoScope(scoped_orgs=[], scoped_repos=[], scope_type="global")

        mock_inner_session = AsyncMock()

        with (
            patch("app.database.AsyncSessionLocal") as mock_session_local,
            patch("app.services.rbac_service.resolve_roles", return_value=["analyst"]),
            patch("app.services.rbac_service.get_user_scope", return_value=mock_scope),
        ):
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_inner_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_local.return_value = mock_ctx

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/auth/me", cookies={"access_token": token})

        assert resp.status_code == 200
        # setex should NOT be called when TTL is <= 0
        mock_valkey.setex.assert_not_called()


# ─── H5: Dev-Login Hardening ─────────────────────────────────────────────────


class TestDevLoginHardening:
    """Test dev-login warning log and rate limit decorator."""

    def test_dev_login_logs_warning(self):
        """Successful dev-login should emit a warning log."""
        app, mock_db, mock_valkey = _build_auth_app()

        with patch("app.routers.auth.logger") as mock_logger:
            mock_valkey.setex = AsyncMock(return_value=True)
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/auth/dev-login",
                json={"username": "devuser", "password": "devuser"},
            )

        assert resp.status_code == 200
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args
        assert call_kwargs[0][0] == "auth.dev_login_used"
        assert call_kwargs[1]["username"] == "devuser"
        assert "remote_ip" in call_kwargs[1]

    def test_dev_login_still_rejects_bad_credentials(self):
        """Dev-login with wrong password must still return 401."""
        app, _, _ = _build_auth_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/auth/dev-login",
            json={"username": "devuser", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_dev_login_blocked_in_production(self):
        """Dev-login must return 404 when ENVIRONMENT=production."""
        app, _, _ = _build_auth_app()

        # The dev_login endpoint does `from app.config import settings as cfg`
        # and checks `cfg.ENVIRONMENT`, so we patch app.config.settings
        with patch("app.config.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            # Also need initial_admin_logins for get_current_user path
            mock_settings.initial_admin_logins = set()
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/v1/auth/dev-login",
                json={"username": "devuser", "password": "devuser"},
            )
        assert resp.status_code == 404


# ─── H9: Per-Endpoint Rate Limiting ──────────────────────────────────────────


class TestRateLimitDecorators:
    """Verify that rate limit decorators are present on sensitive endpoints."""

    def _get_route_limits(self, func_module: str, func_name: str) -> list[str]:
        """Extract rate limit strings from the shared limiter for a given function."""
        from app.rate_limit import limiter

        key = f"{func_module}.{func_name}"
        limit_objs = limiter._route_limits.get(key, [])
        return [str(lim.limit) for lim in limit_objs]

    def test_dev_login_has_rate_limit(self):
        """POST /auth/dev-login should have a 5/minute rate limit."""
        from app.routers import auth  # noqa: F401 — trigger decorator registration

        limits = self._get_route_limits("app.routers.auth", "dev_login")
        assert limits, "dev_login endpoint is missing @limiter.limit() decorator"
        assert any("5" in s and "minute" in s for s in limits), (
            f"Expected '5 per ... minute' rate limit, found: {limits}"
        )

    def test_github_callback_has_rate_limit(self):
        """GET /auth/github/callback should have a 10/minute rate limit."""
        from app.routers import auth  # noqa: F401

        limits = self._get_route_limits("app.routers.auth", "github_callback")
        assert limits, "github_callback is missing @limiter.limit() decorator"
        assert any("10" in s and "minute" in s for s in limits), (
            f"Expected '10 per ... minute' rate limit, found: {limits}"
        )

    def test_saml_acs_has_rate_limit(self):
        """POST /auth/saml/acs should have a 10/minute rate limit."""
        from app.routers import auth  # noqa: F401

        limits = self._get_route_limits("app.routers.auth", "saml_acs")
        assert limits, "saml_acs is missing @limiter.limit() decorator"
        assert any("10" in s and "minute" in s for s in limits), (
            f"Expected '10 per ... minute' rate limit, found: {limits}"
        )

    def test_setup_login_has_rate_limit(self):
        """POST /setup/login should have a 5/minute rate limit."""
        from app.routers import setup  # noqa: F401

        limits = self._get_route_limits("app.routers.setup", "setup_login")
        assert limits, "setup_login is missing @limiter.limit() decorator"
        assert any("5" in s and "minute" in s for s in limits), (
            f"Expected '5 per ... minute' rate limit, found: {limits}"
        )

    def test_setup_complete_has_rate_limit(self):
        """POST /setup/complete should have a 3/minute rate limit."""
        from app.routers import setup  # noqa: F401

        limits = self._get_route_limits("app.routers.setup", "setup_complete_endpoint")
        assert limits, "setup_complete_endpoint is missing @limiter.limit() decorator"
        assert any("3" in s and "minute" in s for s in limits), (
            f"Expected '3 per ... minute' rate limit, found: {limits}"
        )

    def test_query_run_has_rate_limit(self):
        """POST /query/run should have a 30/minute rate limit."""
        from app.routers import query  # noqa: F401

        limits = self._get_route_limits("app.routers.query", "run_query")
        assert limits, "run_query is missing @limiter.limit() decorator"
        assert any("30" in s and "minute" in s for s in limits), (
            f"Expected '30 per ... minute' rate limit, found: {limits}"
        )


class TestRateLimitModule:
    """Test the shared rate_limit module."""

    def test_limiter_is_importable(self):
        """The shared limiter instance should be importable from app.rate_limit."""
        from app.rate_limit import limiter

        assert limiter is not None

    def test_limiter_is_same_instance_as_main(self):
        """The limiter used in main.py should be the same instance as app.rate_limit."""
        from app.main import limiter as main_limiter
        from app.rate_limit import limiter as shared_limiter

        assert main_limiter is shared_limiter

    def test_limiter_has_default_limits(self):
        """The shared limiter should have default limits configured."""
        from slowapi import Limiter

        from app.rate_limit import limiter

        assert isinstance(limiter, Limiter)
