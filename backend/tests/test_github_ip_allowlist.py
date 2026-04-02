"""Tests for the GitHub IP allowlist service, middleware, and admin endpoints."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github_ip_allowlist import (
    VALKEY_KEY,
    VALKEY_TTL,
    GitHubIPAllowlist,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_allowlist() -> None:
    """Ensure every test starts with a clean allowlist state."""
    GitHubIPAllowlist.reset()
    yield  # type: ignore[misc]
    GitHubIPAllowlist.reset()


@pytest.fixture
def mock_valkey() -> AsyncMock:
    """Return a mock Valkey client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sample_meta_response() -> dict[str, Any]:
    """Return a realistic GitHub /meta response snippet."""
    return {
        "verifiable_password_authentication": True,
        "hooks": [
            "192.30.252.0/22",
            "185.199.108.0/22",
            "140.82.112.0/20",
        ],
        "actions": [
            "4.148.0.0/16",
            "13.65.0.0/16",
        ],
        "packages": ["13.65.0.0/16"],
    }


# ─── GitHubIPAllowlist.refresh ─────────────────────────────────────────────────


class TestRefresh:
    """Tests for GitHubIPAllowlist.refresh()."""

    @pytest.mark.asyncio
    async def test_refresh_fetches_and_caches(
        self, mock_valkey: AsyncMock, sample_meta_response: dict[str, Any]
    ) -> None:
        """refresh() fetches /meta, stores CIDRs in Valkey, and updates in-memory."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_meta_response
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.github_ip_allowlist.httpx.AsyncClient", return_value=mock_client):
            count = await GitHubIPAllowlist.refresh(mock_valkey)

        # hooks has 3 + actions has 2 = 5 unique CIDRs
        assert count == 5
        assert GitHubIPAllowlist.is_loaded() is True
        assert GitHubIPAllowlist.network_count() == 5

        # Verify Valkey was called with correct key/TTL
        mock_valkey.set.assert_called_once()
        call_args = mock_valkey.set.call_args
        assert call_args[0][0] == VALKEY_KEY
        cached_cidrs = json.loads(call_args[0][1])
        assert len(cached_cidrs) == 5
        assert call_args[1]["ex"] == VALKEY_TTL

    @pytest.mark.asyncio
    async def test_refresh_deduplicates_cidrs(self, mock_valkey: AsyncMock) -> None:
        """CIDRs that appear in both hooks and actions are deduplicated."""
        meta = {
            "hooks": ["10.0.0.0/8", "192.168.1.0/24"],
            "actions": ["10.0.0.0/8", "172.16.0.0/12"],
        }
        mock_response = MagicMock()
        mock_response.json.return_value = meta
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.github_ip_allowlist.httpx.AsyncClient", return_value=mock_client):
            count = await GitHubIPAllowlist.refresh(mock_valkey)

        # 10.0.0.0/8 appears in both → deduplicated to 3
        assert count == 3

    @pytest.mark.asyncio
    async def test_refresh_handles_missing_keys(self, mock_valkey: AsyncMock) -> None:
        """If /meta response lacks hooks or actions keys, refresh still works."""
        meta: dict[str, Any] = {"verifiable_password_authentication": True}
        mock_response = MagicMock()
        mock_response.json.return_value = meta
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.github_ip_allowlist.httpx.AsyncClient", return_value=mock_client):
            count = await GitHubIPAllowlist.refresh(mock_valkey)

        assert count == 0
        assert GitHubIPAllowlist.is_loaded() is True

    @pytest.mark.asyncio
    async def test_refresh_raises_on_http_error(self, mock_valkey: AsyncMock) -> None:
        """refresh() propagates HTTP errors from the GitHub API."""
        import httpx

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.services.github_ip_allowlist.httpx.AsyncClient",
                return_value=mock_client,
            ),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await GitHubIPAllowlist.refresh(mock_valkey)


# ─── GitHubIPAllowlist.load_from_cache ─────────────────────────────────────────


class TestLoadFromCache:
    """Tests for GitHubIPAllowlist.load_from_cache()."""

    @pytest.mark.asyncio
    async def test_load_from_cache_returns_true_when_cached(self, mock_valkey: AsyncMock) -> None:
        """load_from_cache() returns True when Valkey has cached CIDRs."""
        cidrs = ["192.30.252.0/22", "185.199.108.0/22"]
        mock_valkey.get = AsyncMock(return_value=json.dumps(cidrs))

        loaded = await GitHubIPAllowlist.load_from_cache(mock_valkey)

        assert loaded is True
        assert GitHubIPAllowlist.is_loaded() is True
        assert GitHubIPAllowlist.network_count() == 2

    @pytest.mark.asyncio
    async def test_load_from_cache_returns_false_when_empty(self, mock_valkey: AsyncMock) -> None:
        """load_from_cache() returns False when Valkey key is missing."""
        mock_valkey.get = AsyncMock(return_value=None)

        loaded = await GitHubIPAllowlist.load_from_cache(mock_valkey)

        assert loaded is False
        assert GitHubIPAllowlist.is_loaded() is False


# ─── GitHubIPAllowlist.is_allowed ──────────────────────────────────────────────


class TestIsAllowed:
    """Tests for GitHubIPAllowlist.is_allowed()."""

    @pytest.mark.asyncio
    async def test_allowed_ip_in_range(self, mock_valkey: AsyncMock) -> None:
        """IP within a loaded CIDR range is allowed."""
        cidrs = ["192.30.252.0/22"]
        mock_valkey.get = AsyncMock(return_value=json.dumps(cidrs))
        await GitHubIPAllowlist.load_from_cache(mock_valkey)

        assert GitHubIPAllowlist.is_allowed("192.30.252.1") is True
        assert GitHubIPAllowlist.is_allowed("192.30.255.254") is True

    @pytest.mark.asyncio
    async def test_blocked_ip_not_in_range(self, mock_valkey: AsyncMock) -> None:
        """IP outside all loaded CIDR ranges is blocked."""
        cidrs = ["192.30.252.0/22"]
        mock_valkey.get = AsyncMock(return_value=json.dumps(cidrs))
        await GitHubIPAllowlist.load_from_cache(mock_valkey)

        assert GitHubIPAllowlist.is_allowed("10.0.0.1") is False

    def test_fail_open_when_not_loaded(self) -> None:
        """When allowlist is not loaded, is_allowed returns True (fail-open)."""
        assert GitHubIPAllowlist.is_loaded() is False
        assert GitHubIPAllowlist.is_allowed("1.2.3.4") is True

    def test_invalid_ip_returns_false(self) -> None:
        """Invalid IP strings are rejected."""
        # Force _loaded to True so fail-open doesn't trigger
        GitHubIPAllowlist._loaded = True
        GitHubIPAllowlist._networks = []

        assert GitHubIPAllowlist.is_allowed("not-an-ip") is False
        assert GitHubIPAllowlist.is_allowed("") is False

    @pytest.mark.asyncio
    async def test_ipv6_support(self, mock_valkey: AsyncMock) -> None:
        """IPv6 CIDRs and addresses are correctly handled."""
        cidrs = ["2a0a:a440::/29"]
        mock_valkey.get = AsyncMock(return_value=json.dumps(cidrs))
        await GitHubIPAllowlist.load_from_cache(mock_valkey)

        assert GitHubIPAllowlist.is_allowed("2a0a:a440::1") is True
        assert GitHubIPAllowlist.is_allowed("2a0a:a448::1") is False


# ─── GitHubIPAllowlist state methods ───────────────────────────────────────────


class TestStateMethods:
    """Tests for state inspection methods."""

    def test_initial_state(self) -> None:
        """Initial state is not loaded with zero networks."""
        assert GitHubIPAllowlist.is_loaded() is False
        assert GitHubIPAllowlist.network_count() == 0

    def test_reset(self) -> None:
        """reset() clears all state."""
        GitHubIPAllowlist._loaded = True
        GitHubIPAllowlist._networks = [MagicMock()]
        GitHubIPAllowlist.reset()
        assert GitHubIPAllowlist.is_loaded() is False
        assert GitHubIPAllowlist.network_count() == 0


# ─── Middleware tests ──────────────────────────────────────────────────────────


class TestGitHubIPAllowlistMiddleware:
    """Tests for GitHubIPAllowlistMiddleware."""

    def _build_app(self) -> Any:
        """Build a minimal FastAPI app with the middleware."""
        from fastapi import FastAPI

        from app.middleware.ip_allowlist import GitHubIPAllowlistMiddleware

        test_app = FastAPI()
        test_app.add_middleware(
            GitHubIPAllowlistMiddleware,
            protected_prefixes=["/api/v1/ingest/webhook"],
        )

        @test_app.get("/api/v1/ingest/webhook")
        async def webhook() -> dict[str, str]:
            return {"status": "ok"}

        @test_app.get("/api/v1/events")
        async def events() -> dict[str, str]:
            return {"status": "ok"}

        return test_app

    def test_unprotected_path_allowed(self) -> None:
        """Requests to unprotected paths are always allowed."""
        from fastapi.testclient import TestClient

        app = self._build_app()
        client = TestClient(app)
        resp = client.get("/api/v1/events")
        assert resp.status_code == 200

    def test_protected_path_blocked_when_ip_not_in_allowlist(self) -> None:
        """Requests to protected paths from non-GitHub IPs are blocked."""
        from fastapi.testclient import TestClient

        # Load an allowlist that doesn't include testclient IP
        GitHubIPAllowlist._loaded = True
        GitHubIPAllowlist._networks = []

        app = self._build_app()
        client = TestClient(app)
        resp = client.get("/api/v1/ingest/webhook")
        assert resp.status_code == 403
        assert "GitHub IP allowlist" in resp.json()["detail"]

    def test_protected_path_allowed_when_ip_matches(self) -> None:
        """Requests to protected paths from GitHub IPs are allowed."""
        import ipaddress

        from fastapi.testclient import TestClient

        # TestClient uses 'testclient' as host, so let's use X-Forwarded-For
        GitHubIPAllowlist._loaded = True
        GitHubIPAllowlist._networks = [ipaddress.ip_network("10.0.0.0/8")]

        app = self._build_app()
        client = TestClient(app)
        resp = client.get(
            "/api/v1/ingest/webhook",
            headers={"x-forwarded-for": "10.1.2.3"},
        )
        assert resp.status_code == 200

    def test_protected_path_uses_x_forwarded_for(self) -> None:
        """Middleware extracts client IP from X-Forwarded-For header."""
        import ipaddress

        from fastapi.testclient import TestClient

        GitHubIPAllowlist._loaded = True
        GitHubIPAllowlist._networks = [ipaddress.ip_network("203.0.113.0/24")]

        app = self._build_app()
        client = TestClient(app)

        # With matching X-Forwarded-For
        resp = client.get(
            "/api/v1/ingest/webhook",
            headers={"x-forwarded-for": "203.0.113.50, 10.0.0.1"},
        )
        assert resp.status_code == 200

        # With non-matching X-Forwarded-For
        resp = client.get(
            "/api/v1/ingest/webhook",
            headers={"x-forwarded-for": "198.51.100.1"},
        )
        assert resp.status_code == 403

    def test_fail_open_when_not_loaded(self) -> None:
        """When allowlist is not loaded, protected paths are accessible."""
        from fastapi.testclient import TestClient

        assert GitHubIPAllowlist.is_loaded() is False

        app = self._build_app()
        client = TestClient(app)
        resp = client.get("/api/v1/ingest/webhook")
        assert resp.status_code == 200


# ─── Admin endpoint tests ─────────────────────────────────────────────────────


class TestAdminEndpoints:
    """Tests for the /admin/github-ip-allowlist endpoints."""

    def _build_admin_app(
        self,
        valkey_get_return: str | None = None,
        roles: list[str] | None = None,
    ) -> Any:
        """Build a minimal FastAPI app with admin routes."""
        import jwt as pyjwt
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.deps import get_db, get_valkey
        from app.routers import admin as admin_module

        app = FastAPI()
        app.include_router(admin_module.router, prefix="/api/v1")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        mock_valkey_instance = AsyncMock()
        mock_valkey_instance.get = AsyncMock(return_value=valkey_get_return)
        mock_valkey_instance.set = AsyncMock(return_value=True)

        async def _mock_db() -> Any:
            yield mock_db

        async def _mock_valkey() -> Any:
            yield mock_valkey_instance

        app.dependency_overrides[get_db] = _mock_db
        app.dependency_overrides[get_valkey] = _mock_valkey

        # Create a valid JWT for auth
        session_data = json.dumps(
            {
                "github_login": "admin-user",
                "github_id": 99,
                "roles": roles or ["sys_admin"],
                "scoped_orgs": [],
                "scoped_repos": [],
                "scope_type": "global",
                "session_expires_at": "2099-01-01T00:00:00+00:00",
            }
        )
        mock_valkey_instance.get.return_value = session_data
        mock_valkey_instance.ttl = AsyncMock(return_value=3600)

        from datetime import UTC, datetime, timedelta

        token = pyjwt.encode(
            {
                "sub": "admin-user",
                "github_id": 99,
                "jti": "test-jti",
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "iat": datetime.now(UTC),
            },
            "testsecretkey_for_unit_tests_only_32ch",
            algorithm="HS256",
        )

        client = TestClient(app)
        client.cookies.set("access_token", token)
        client.cookies.set("csrf_token", "test-csrf")

        return client, mock_valkey_instance

    def test_status_endpoint(self) -> None:
        """GET /admin/github-ip-allowlist returns allowlist status."""
        client, _ = self._build_admin_app()

        resp = client.get("/api/v1/admin/github-ip-allowlist")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "loaded" in data
        assert "network_count" in data

    def test_status_endpoint_forbidden_for_non_admin(self) -> None:
        """Non-admin users cannot access the status endpoint."""
        client, _ = self._build_admin_app(roles=["analyst"])

        resp = client.get("/api/v1/admin/github-ip-allowlist")
        assert resp.status_code == 403

    def test_refresh_endpoint(self) -> None:
        """POST /admin/github-ip-allowlist/refresh triggers a refresh."""
        client, mock_valkey_instance = self._build_admin_app()

        meta_response = {
            "hooks": ["192.30.252.0/22"],
            "actions": ["4.148.0.0/16"],
        }
        mock_http_response = MagicMock()
        mock_http_response.json.return_value = meta_response
        mock_http_response.raise_for_status = MagicMock()

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_http_response)
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.github_ip_allowlist.httpx.AsyncClient",
            return_value=mock_http_client,
        ):
            resp = client.post(
                "/api/v1/admin/github-ip-allowlist/refresh",
                headers={"X-CSRF-Token": "test-csrf"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["refreshed"] is True
        assert data["network_count"] == 2

    def test_refresh_endpoint_requires_csrf(self) -> None:
        """POST /admin/github-ip-allowlist/refresh requires CSRF token."""
        client, _ = self._build_admin_app()

        resp = client.post("/api/v1/admin/github-ip-allowlist/refresh")
        assert resp.status_code == 403
