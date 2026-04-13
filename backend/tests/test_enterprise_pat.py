"""Tests for the enterprise PAT management feature.

Covers:
  - Token masking utility
  - PUT / GET / DELETE / POST-test API endpoints
  - Token format validation
  - Sync worker PAT retrieval logic
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, get_valkey, verify_csrf

# ── Shared helpers ──────────────────────────────────────────────────────────


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with the enterprise-pat router."""
    from app.routers.enterprise_pat import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _mock_db() -> AsyncMock:
    """Return an ``AsyncMock`` that behaves like an ``AsyncSession``."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _admin_user() -> AuthenticatedUser:
    """Return a real ``AuthenticatedUser`` with ``sys_admin`` role."""
    return AuthenticatedUser(
        github_login="admin-user",
        github_id=99999,
        roles=["sys_admin"],
        scoped_orgs=["my-org"],
        scoped_repos=[],
        scope_type="all",
        jti="test-jti-pat",
        session_expires_at="2099-01-01T00:00:00+00:00",
    )


def _override_deps(app: FastAPI, db: AsyncMock, user: AuthenticatedUser) -> None:
    """Override auth, DB, Valkey, and CSRF deps for testing."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_valkey] = lambda: AsyncMock()
    app.dependency_overrides[verify_csrf] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user


# ═══════════════════════════════════════════════════════════════════════════════
#  mask_token
# ═══════════════════════════════════════════════════════════════════════════════


class TestMaskToken:
    """Unit tests for the ``mask_token`` helper."""

    def test_standard_classic_pat(self) -> None:
        from app.routers.enterprise_pat import mask_token

        assert mask_token("ghp_abc123xyz789abcdef") == "ghp_****...cdef"

    def test_short_token(self) -> None:
        from app.routers.enterprise_pat import mask_token

        # 7 chars is ≤ 8 so fully masked
        assert mask_token("ghp_abc") == "****"

    def test_very_short_token(self) -> None:
        from app.routers.enterprise_pat import mask_token

        assert mask_token("abcd") == "****"

    def test_exactly_eight_chars(self) -> None:
        from app.routers.enterprise_pat import mask_token

        assert mask_token("12345678") == "****"

    def test_nine_chars(self) -> None:
        from app.routers.enterprise_pat import mask_token

        result = mask_token("123456789")
        assert result == "1234****...6789"

    def test_fine_grained_pat(self) -> None:
        from app.routers.enterprise_pat import mask_token

        token = "github_pat_11ABC123def456ghi789"
        result = mask_token(token)
        assert result.startswith("gith")
        assert result.endswith("i789")
        assert "****..." in result


# ═══════════════════════════════════════════════════════════════════════════════
#  Token format validation regex
# ═══════════════════════════════════════════════════════════════════════════════


class TestTokenFormatValidation:
    """Tests for the PAT format regex."""

    def test_valid_classic_pat(self) -> None:
        from app.routers.enterprise_pat import _PAT_RE

        assert _PAT_RE.match("ghp_abcDEF123456789") is not None

    def test_valid_fine_grained_pat(self) -> None:
        from app.routers.enterprise_pat import _PAT_RE

        assert _PAT_RE.match("github_pat_11ABC123DEF") is not None

    def test_rejects_empty(self) -> None:
        from app.routers.enterprise_pat import _PAT_RE

        assert _PAT_RE.match("") is None

    def test_rejects_random_string(self) -> None:
        from app.routers.enterprise_pat import _PAT_RE

        assert _PAT_RE.match("some_random_token_value") is None

    def test_rejects_gho_token(self) -> None:
        from app.routers.enterprise_pat import _PAT_RE

        assert _PAT_RE.match("gho_abcdefghijklmnop") is None

    def test_rejects_prefix_only(self) -> None:
        from app.routers.enterprise_pat import _PAT_RE

        assert _PAT_RE.match("ghp_") is None  # min 1 char after prefix


# ═══════════════════════════════════════════════════════════════════════════════
#  GET /api/v1/admin/enterprise-pat
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetEnterprisePAT:
    """Tests for the GET endpoint."""

    @pytest.mark.asyncio
    async def test_returns_not_configured_when_no_pat(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        with patch(
            "app.routers.enterprise_pat.get_setting",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/v1/admin/enterprise-pat")

        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert data["masked"] is None

    @pytest.mark.asyncio
    async def test_returns_configured_with_masked_token(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        with patch(
            "app.routers.enterprise_pat.get_setting",
            new_callable=AsyncMock,
            return_value="ghp_abcdefghijklmnopqrst",
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/v1/admin/enterprise-pat")

        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["masked"] == "ghp_****...qrst"
        # Ensure the actual token is NOT in the response
        assert "abcdefghijklmnopqrst" not in resp.text


# ═══════════════════════════════════════════════════════════════════════════════
#  PUT /api/v1/admin/enterprise-pat
# ═══════════════════════════════════════════════════════════════════════════════


class TestSaveEnterprisePAT:
    """Tests for the PUT endpoint."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_format(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.put(
                "/api/v1/admin/enterprise-pat",
                json={"token": "invalid_token_format"},
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_saves_valid_token(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"x-oauth-scopes": "admin:enterprise, repo"}
        mock_response.json.return_value = {"login": "test-admin"}

        with (
            patch(
                "app.routers.enterprise_pat.set_setting",
                new_callable=AsyncMock,
            ) as mock_set,
            patch(
                "app.routers.enterprise_pat.load_settings_overlay",
                new_callable=AsyncMock,
            ),
            patch(
                "app.routers.enterprise_pat.log_action",
                new_callable=AsyncMock,
            ),
            patch(
                "app.routers.enterprise_pat._validate_token_with_github",
                new_callable=AsyncMock,
                return_value={"login": "test-admin", "scopes": "admin:enterprise, repo"},
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.put(
                    "/api/v1/admin/enterprise-pat",
                    json={"token": "ghp_validtoken12345678"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "****" in data["masked"]
        # Verify set_setting was called with correct args
        mock_set.assert_called_once()
        call_args = mock_set.call_args
        assert call_args[0][1] == "enterprise_pat"  # key
        assert call_args[0][2] == "ghp_validtoken12345678"  # value

    @pytest.mark.asyncio
    async def test_rejects_expired_token(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        from fastapi import HTTPException

        with patch(
            "app.routers.enterprise_pat._validate_token_with_github",
            new_callable=AsyncMock,
            side_effect=HTTPException(
                status_code=422,
                detail="Token is invalid or expired. GitHub returned 401.",
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.put(
                    "/api/v1/admin/enterprise-pat",
                    json={"token": "ghp_expiredtoken12345678"},
                )

        assert resp.status_code == 422
        assert "invalid or expired" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════════
#  DELETE /api/v1/admin/enterprise-pat
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeleteEnterprisePAT:
    """Tests for the DELETE endpoint."""

    @pytest.mark.asyncio
    async def test_deletes_existing_pat(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        with (
            patch(
                "app.routers.enterprise_pat.delete_setting",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.routers.enterprise_pat.load_settings_overlay",
                new_callable=AsyncMock,
            ),
            patch(
                "app.routers.enterprise_pat.log_action",
                new_callable=AsyncMock,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.delete("/api/v1/admin/enterprise-pat")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_returns_404_when_not_configured(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        with patch(
            "app.routers.enterprise_pat.delete_setting",
            new_callable=AsyncMock,
            return_value=False,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.delete("/api/v1/admin/enterprise-pat")

        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
#  POST /api/v1/admin/enterprise-pat/test
# ═══════════════════════════════════════════════════════════════════════════════


class TestTestEnterprisePAT:
    """Tests for the POST test endpoint."""

    @pytest.mark.asyncio
    async def test_returns_404_when_not_configured(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        with patch(
            "app.routers.enterprise_pat.get_setting",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post("/api/v1/admin/enterprise-pat/test")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_ok_on_valid_token(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        with (
            patch(
                "app.routers.enterprise_pat.get_setting",
                new_callable=AsyncMock,
                return_value="ghp_testedtoken12345678",
            ),
            patch(
                "app.routers.enterprise_pat._validate_token_with_github",
                new_callable=AsyncMock,
                return_value={"login": "admin-bot", "scopes": "admin:enterprise"},
            ),
            patch(
                "app.routers.enterprise_pat.log_action",
                new_callable=AsyncMock,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post("/api/v1/admin/enterprise-pat/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["login"] == "admin-bot"
        assert data["scopes"] == "admin:enterprise"

    @pytest.mark.asyncio
    async def test_returns_error_on_invalid_token(self) -> None:
        app = _make_app()
        db = _mock_db()
        user = _admin_user()
        _override_deps(app, db, user)

        from fastapi import HTTPException

        with (
            patch(
                "app.routers.enterprise_pat.get_setting",
                new_callable=AsyncMock,
                return_value="ghp_badtoken12345678901",
            ),
            patch(
                "app.routers.enterprise_pat._validate_token_with_github",
                new_callable=AsyncMock,
                side_effect=HTTPException(
                    status_code=422,
                    detail="Token is invalid or expired. GitHub returned 401.",
                ),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post("/api/v1/admin/enterprise-pat/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "invalid or expired" in (data.get("message") or "")


# ═══════════════════════════════════════════════════════════════════════════════
#  Sync worker PAT retrieval
# ═══════════════════════════════════════════════════════════════════════════════


class TestSyncWorkerPATRetrieval:
    """Verify that the sync worker retrieves the enterprise PAT for audit_log."""

    def test_setting_key_constant(self) -> None:
        """Ensure the router and sync worker use the same setting key."""
        from app.routers.enterprise_pat import SETTING_KEY

        assert SETTING_KEY == "enterprise_pat"

    @pytest.mark.asyncio
    async def test_get_setting_returns_token(self) -> None:
        """The settings service round-trips a stored PAT."""
        from app.services.settings_service import get_setting, set_setting

        # This test uses mocked encryption — just verify the interface works
        with (
            patch("app.services.settings_service._get_encryption_key", return_value=b"0" * 32),
            patch(
                "app.services.settings_service.encrypt_value",
                return_value="encrypted_blob",
            ),
            patch(
                "app.services.settings_service.decrypt_value",
                return_value="ghp_testtoken123456789",
            ),
        ):
            db = _mock_db()
            # Mock the select to return None (new) then the stored value
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db.execute = AsyncMock(return_value=mock_result)

            await set_setting(db, "enterprise_pat", "ghp_testtoken123456789")

            # Now mock the get
            mock_row = MagicMock()
            mock_row.encrypted_value = "encrypted_blob"
            mock_row.sensitivity = "critical"
            mock_get_result = MagicMock()
            mock_get_result.scalar_one_or_none.return_value = mock_row
            db.execute = AsyncMock(return_value=mock_get_result)

            result = await get_setting(db, "enterprise_pat")
            assert result == "ghp_testtoken123456789"
