"""Security tests: OWASP controls verification.

Tests cover:
- CSP, HSTS, X-Frame-Options, X-Content-Type-Options headers
- JWT wrong signature → 401
- JWT expired → 401
- Session revoked in Valkey → 401
- SQL injection in query params rejected by Pydantic (422)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.main import SecurityHeadersMiddleware

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(
    sub: str = "testuser",
    jti: str = "sec-jti",
    expired: bool = False,
    wrong_secret: bool = False,
) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    payload = {"sub": sub, "github_id": 12345, "jti": jti, "exp": exp, "iat": now}
    secret = "TOTALLY_WRONG_SECRET_NOT_VALID" if wrong_secret else SECRET
    return pyjwt.encode(payload, secret, algorithm="HS256")


def _make_session() -> str:
    return json.dumps(
        {
            "github_login": "testuser",
            "github_id": 12345,
            "roles": ["analyst"],
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
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _build_secured_app() -> FastAPI:
    """Minimal app with SecurityHeadersMiddleware and a test route."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/test")
    async def test_endpoint() -> dict:
        return {"ok": True}

    @app.post("/test")
    async def test_post_endpoint() -> dict:
        return {"ok": True}

    return app


def _build_auth_app(valkey_get_return: str | None = None) -> FastAPI:
    """Minimal app with auth router + dep overrides for JWT/session tests."""
    from app.routers import auth as auth_router_module

    app = FastAPI()
    app.include_router(auth_router_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_get_return)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app


# ─── Security Headers (OWASP A05: Security Misconfiguration) ─────────────────


class TestSecurityHeaders:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(_build_secured_app())

    def test_csp_header_present(self, client):
        resp = client.get("/test")
        assert "content-security-policy" in {k.lower() for k in resp.headers}

    def test_csp_contains_default_src_self(self, client):
        resp = client.get("/test")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp

    def test_csp_blocks_frame_ancestors(self, client):
        """CSP frame-ancestors 'none' blocks clickjacking."""
        resp = client.get("/test")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "frame-ancestors 'none'" in csp

    def test_hsts_header_present(self, client):
        resp = client.get("/test")
        assert "strict-transport-security" in {k.lower() for k in resp.headers}

    def test_hsts_has_long_max_age(self, client):
        """HSTS max-age should be at least 1 year (31536000)."""
        resp = client.get("/test")
        hsts = resp.headers.get("Strict-Transport-Security", "")
        assert "max-age=" in hsts
        max_age = int(hsts.split("max-age=")[1].split(";")[0].strip())
        assert max_age >= 31536000

    def test_x_frame_options_deny(self, client):
        resp = client.get("/test")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options_nosniff(self, client):
        resp = client.get("/test")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_referrer_policy_set(self, client):
        resp = client.get("/test")
        assert "referrer-policy" in {k.lower() for k in resp.headers}

    def test_permissions_policy_set(self, client):
        resp = client.get("/test")
        assert "permissions-policy" in {k.lower() for k in resp.headers}

    def test_security_headers_on_post_response(self, client):
        """Security headers must apply to POST responses too."""
        resp = client.post("/test")
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "content-security-policy" in {k.lower() for k in resp.headers}

    def test_security_headers_on_404_response(self, client):
        """Security headers must apply even on 404 responses."""
        resp = client.get("/nonexistent-path")
        assert resp.headers.get("X-Frame-Options") == "DENY"


# ─── JWT Validation (OWASP A07: Identification & Authentication Failures) ────


class TestJWTValidation:
    def test_wrong_signature_returns_401(self):
        """JWT signed with wrong secret must be rejected."""
        token = _make_jwt(wrong_secret=True)
        app = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 401

    def test_expired_jwt_returns_401(self):
        """Expired JWTs must be rejected even if session exists in Valkey."""
        token = _make_jwt(jti="exp-sec-jti", expired=True)
        app = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 401

    def test_missing_jwt_cookie_returns_401(self):
        """No JWT cookie → must return 401, not expose data."""
        app = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_tampered_jwt_payload_returns_401(self):
        """Manually tampered JWT (invalid base64 middle) must be rejected."""
        token = _make_jwt()
        # Tamper the payload section
        parts = token.split(".")
        tampered = parts[0] + ".TAMPERED_PAYLOAD_XXXX." + parts[2]
        app = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": tampered})
        assert resp.status_code == 401

    def test_none_algorithm_attack_rejected(self):
        """JWT with alg=none must be rejected (algorithm confusion attack)."""
        import base64

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        payload_data = {
            "sub": "attacker",
            "github_id": 0,
            "jti": "attack-jti",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
        }
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b"=")
        token = f"{header.decode()}.{payload_b64.decode()}."

        app = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 401


# ─── Session Revocation (OWASP A07) ──────────────────────────────────────────


class TestSessionRevocation:
    def test_revoked_session_returns_401(self):
        """After logout, session key is removed; subsequent requests must be 401."""
        jti = "revoked-sec-jti"
        token = _make_jwt(jti=jti)
        # Valkey returns None → session was revoked
        app = _build_auth_app(valkey_get_return=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 401

    def test_valid_session_returns_200(self):
        """Sanity check: valid JWT + session returns 200."""
        jti = "valid-sec-jti"
        token = _make_jwt(jti=jti)
        app = _build_auth_app(valkey_get_return=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/v1/auth/me", cookies={"access_token": token})
        assert resp.status_code == 200


# ─── SQL Injection (OWASP A03: Injection) ────────────────────────────────────


class TestSQLInjectionPrevention:
    def test_sql_injection_in_action_param_rejected(self):
        """SQL injection attempt in action filter must be rejected by Pydantic (422)."""
        from pydantic import ValidationError

        from app.schemas.audit_event import EventListParams

        with pytest.raises(ValidationError):
            EventListParams(action="repos.create'; DROP TABLE events --")

    def test_sql_injection_union_select_rejected(self):
        from pydantic import ValidationError

        from app.schemas.audit_event import EventListParams

        with pytest.raises(ValidationError):
            EventListParams(action="x' UNION SELECT * FROM pg_shadow --")

    def test_sql_injection_in_org_param_rejected(self):
        from pydantic import ValidationError

        from app.schemas.audit_event import EventListParams

        with pytest.raises(ValidationError):
            EventListParams(org="my-org' OR '1'='1")

    def test_semicolon_injection_rejected(self):
        from pydantic import ValidationError

        from app.schemas.audit_event import EventListParams

        with pytest.raises(ValidationError):
            EventListParams(action="repos.create; DELETE FROM events")

    def test_valid_action_passes_validation(self):
        from app.schemas.audit_event import EventListParams

        params = EventListParams(action="repos.create")
        assert params.action == "repos.create"

    def test_valid_action_wildcard_passes(self):
        from app.schemas.audit_event import EventListParams

        params = EventListParams(action="repos.*")
        assert params.action == "repos.*"


# ─── Query service SQL injection (OWASP A03) ─────────────────────────────────


class TestQueryServiceInjection:
    def test_drop_table_blocked(self):
        from app.services.query_service import QueryValidationError, validate_and_prepare
        from app.services.rbac_service import OrgRepoScope

        with pytest.raises(QueryValidationError):
            validate_and_prepare("DROP TABLE events", OrgRepoScope(scope_type="global"))

    def test_select_from_pg_shadow_blocked(self):
        """System catalog access must be blocked."""
        from app.services.query_service import QueryValidationError, validate_and_prepare
        from app.services.rbac_service import OrgRepoScope

        with pytest.raises(QueryValidationError):
            validate_and_prepare("SELECT * FROM pg_shadow", OrgRepoScope(scope_type="global"))

    def test_inline_drop_rejected(self):
        """Inline DROP after SELECT must be caught as multiple statements."""
        from app.services.query_service import QueryValidationError, validate_and_prepare
        from app.services.rbac_service import OrgRepoScope

        with pytest.raises(QueryValidationError):
            validate_and_prepare("SELECT 1; DROP TABLE events", OrgRepoScope(scope_type="global"))

    def test_insert_blocked(self):
        from app.services.query_service import QueryValidationError, validate_and_prepare
        from app.services.rbac_service import OrgRepoScope

        with pytest.raises(QueryValidationError):
            validate_and_prepare("INSERT INTO events VALUES (1)", OrgRepoScope(scope_type="global"))

    def test_information_schema_blocked(self):
        from app.services.query_service import QueryValidationError, validate_and_prepare
        from app.services.rbac_service import OrgRepoScope

        with pytest.raises(QueryValidationError):
            validate_and_prepare(
                "SELECT * FROM information_schema.tables",
                OrgRepoScope(scope_type="global"),
            )

    def test_dangerous_function_pg_read_file_blocked(self):
        from app.services.query_service import QueryValidationError, validate_and_prepare
        from app.services.rbac_service import OrgRepoScope

        with pytest.raises(QueryValidationError):
            validate_and_prepare(
                "SELECT pg_read_file('/etc/passwd')",
                OrgRepoScope(scope_type="global"),
            )


# ─── RBAC Authorization (OWASP A01: Broken Access Control) ─────────────────


class TestRBACAuthorization:
    def test_analyst_cannot_access_raw_event(self):
        """Raw event endpoint is restricted to sys_admin only."""
        import json as _json

        from app.deps import get_db, get_valkey
        from app.routers import events as events_router_module

        token = _make_jwt(jti="rbac-jti")
        session = _json.dumps(
            {
                "github_login": "testuser",
                "github_id": 12345,
                "roles": ["analyst"],  # NOT sys_admin
                "scoped_orgs": ["my-org"],
                "scoped_repos": [],
                "scope_type": "scoped",
                "session_expires_at": "2099-01-01T00:00:00+00:00",
            }
        )

        app = FastAPI()
        app.include_router(events_router_module.router, prefix="/api/v1")

        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=session)

        async def override_db():
            yield mock_db

        async def override_valkey():
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/events/1/raw", cookies={"access_token": token})
        assert resp.status_code == 403
