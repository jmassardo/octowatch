"""Tests for the velocity router.

Tests cover:
- Unauthenticated requests → 401
- Authenticated requests return 200 with correct schema
- Parameter validation (ge/le constraints return 422)
- Cache hit skips DB query
- Cache miss writes to Valkey
- Router metadata (prefix, tags)
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import velocity as vel_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "vel-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 99,
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
            "github_id": 99,
            "roles": roles or ["analyst"],
            "scoped_orgs": orgs or ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db(scalar_return: int = 0) -> AsyncMock:
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (scalar_return,)
    mock_result.fetchall.return_value = []
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _build_app(
    valkey_session: str | None = None,
    db_scalar: int = 0,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(vel_module.router, prefix="/api/v1")

    mock_db = _make_mock_db(db_scalar)
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)
    mock_valkey.setex = AsyncMock(return_value=True)

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ── Unauthenticated ───────────────────────────────────────────────────────────


class TestUnauthenticated:
    def test_leadership_summary_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/velocity/leadership-summary")
        assert resp.status_code == 401

    def test_team_comparison_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/velocity/team-comparison")
        assert resp.status_code == 401

    def test_shipping_cadence_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/velocity/shipping-cadence")
        assert resp.status_code == 401


# ── Leadership Summary ────────────────────────────────────────────────────────


class TestLeadershipSummary:
    def test_returns_200_with_correct_schema(self) -> None:
        token = _make_jwt(jti="ls-schema")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/leadership-summary",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "deployment_frequency" in data
        assert "lead_time" in data
        assert "change_failure_rate" in data
        assert "mttr" in data
        assert "pr_throughput" in data
        assert "active_contributors" in data
        assert "period_days" in data

    def test_metric_has_trend_fields(self) -> None:
        token = _make_jwt(jti="ls-trend")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/leadership-summary",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        metric = resp.json()["deployment_frequency"]
        assert "value" in metric
        assert "previous_value" in metric
        assert "trend_pct" in metric
        assert "classification" in metric

    def test_custom_period(self) -> None:
        token = _make_jwt(jti="ls-custom")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/leadership-summary?period=90",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 90

    def test_period_below_min_returns_422(self) -> None:
        token = _make_jwt(jti="ls-lo-period")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/velocity/leadership-summary?period=3",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_period_above_max_returns_422(self) -> None:
        token = _make_jwt(jti="ls-hi-period")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/velocity/leadership-summary?period=365",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422


# ── Team Comparison ───────────────────────────────────────────────────────────


class TestTeamComparison:
    def test_returns_200_with_correct_schema(self) -> None:
        token = _make_jwt(jti="tc-schema")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/team-comparison",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "metric" in data
        assert "period_days" in data
        assert data["metric"] == "deploy_freq"

    def test_custom_metric_param(self) -> None:
        token = _make_jwt(jti="tc-metric")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/team-comparison?metric=cfr",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["metric"] == "cfr"

    def test_invalid_metric_returns_422(self) -> None:
        token = _make_jwt(jti="tc-bad-metric")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/velocity/team-comparison?metric=invalid",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_period_below_min_returns_422(self) -> None:
        token = _make_jwt(jti="tc-lo-period")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/velocity/team-comparison?period=3",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422


# ── Shipping Cadence ──────────────────────────────────────────────────────────


class TestShippingCadence:
    def test_returns_200_with_correct_schema(self) -> None:
        token = _make_jwt(jti="sc-schema")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/shipping-cadence",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "period_days" in data
        assert isinstance(data["items"], list)

    def test_cadence_items_have_expected_fields(self) -> None:
        token = _make_jwt(jti="sc-fields")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/shipping-cadence",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Default 90 days of data should be returned
        assert len(items) == 90
        for item in items[:3]:  # Check first 3
            assert "date" in item
            assert "deployments" in item
            assert "merges" in item
            assert "reviews" in item

    def test_custom_period(self) -> None:
        token = _make_jwt(jti="sc-custom")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/shipping-cadence?period=30",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["period_days"] == 30
        assert len(data["items"]) == 30

    def test_period_below_min_returns_422(self) -> None:
        token = _make_jwt(jti="sc-lo-period")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/velocity/shipping-cadence?period=3",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_period_above_max_returns_422(self) -> None:
        token = _make_jwt(jti="sc-hi-period")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/velocity/shipping-cadence?period=400",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422


# ── Cache Behaviour ───────────────────────────────────────────────────────────


class TestCacheBehaviour:
    def _cached_summary(self) -> str:
        """Pre-built valid cached leadership summary payload."""
        metric = {
            "value": 1.5,
            "previous_value": 1.0,
            "trend_pct": 50.0,
            "classification": "high",
        }
        return json.dumps(
            {
                "deployment_frequency": metric,
                "lead_time": metric,
                "change_failure_rate": metric,
                "mttr": metric,
                "pr_throughput": metric,
                "active_contributors": metric,
                "period_days": 30,
                "cached_at": datetime.now(UTC).isoformat(),
            }
        )

    def test_cache_hit_skips_db(self) -> None:
        token = _make_jwt(jti="cache-hit")
        session_json = _make_session()

        app = FastAPI()
        app.include_router(vel_module.router, prefix="/api/v1")

        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()

        async def mock_valkey_get(key: str) -> str | None:
            if "session:" in key:
                return session_json
            return self._cached_summary()

        mock_valkey.get = mock_valkey_get
        mock_valkey.setex = AsyncMock(return_value=True)
        mock_valkey.ttl = AsyncMock(return_value=3600)

        async def override_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/leadership-summary",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        mock_db.execute.assert_not_called()

    def test_cache_miss_writes_to_valkey(self) -> None:
        token = _make_jwt(jti="cache-miss")
        session_json = _make_session()

        app = FastAPI()
        app.include_router(vel_module.router, prefix="/api/v1")

        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()

        async def mock_valkey_get(key: str) -> str | None:
            if "session:" in key:
                return session_json
            return None  # cache miss

        mock_valkey.get = mock_valkey_get
        mock_valkey.setex = AsyncMock(return_value=True)
        mock_valkey.ttl = AsyncMock(return_value=3600)

        async def override_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/velocity/leadership-summary",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        mock_db.execute.assert_called()
        mock_valkey.setex.assert_called_once()
        call_args = mock_valkey.setex.call_args
        assert call_args[0][1] == 300  # TTL = 300 seconds


# ── Router Metadata ───────────────────────────────────────────────────────────


class TestRouterMetadata:
    def test_router_prefix(self) -> None:
        assert vel_module.router.prefix == "/velocity"

    def test_router_tags(self) -> None:
        assert "velocity" in vel_module.router.tags
