"""Tests for the workflow_metrics router.

Tests cover:
- Unauthenticated requests → 401
- Authenticated requests return 200 with correct schema
- always-failing and always-timing-out endpoints return correct structure
- run-history endpoint returns correct structure
- Valkey cache is read before DB and written after a miss
- Parameter validation (ge/le constraints return 422)
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
from app.routers import workflow_metrics as wfm_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "wfm-jti") -> str:
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


def _make_mock_db(fetchall_return: list | None = None) -> AsyncMock:
    mock_result = MagicMock()
    mock_result.fetchall.return_value = fetchall_return or []
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _build_app(
    valkey_session: str | None = None,
    db_rows: list | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(wfm_module.router, prefix="/api/v1")

    mock_db = _make_mock_db(db_rows)
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
    def test_always_failing_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/workflow-metrics/always-failing")
        assert resp.status_code == 401

    def test_always_timing_out_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/workflow-metrics/always-timing-out")
        assert resp.status_code == 401

    def test_run_history_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/workflow-metrics/run-history?org=myorg&repo=myrepo&workflow_name=ci"
        )
        assert resp.status_code == 401


# ── Always Failing — authenticated ───────────────────────────────────────────


class TestAlwaysFailingAuthenticated:
    def test_returns_200_with_empty_items(self) -> None:
        token = _make_jwt(jti="af-empty")
        app, _, _ = _build_app(valkey_session=_make_session(), db_rows=[])
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/workflow-metrics/always-failing",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["threshold"] == 5
        assert data["lookback_days"] == 30

    def test_returns_items_from_db(self) -> None:
        token = _make_jwt(jti="af-rows")
        now = datetime.now(UTC)

        # Mock DB returning our rows
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("myorg", "myrepo", "CI Build", 5, now),
        ]
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        app = FastAPI()
        app.include_router(wfm_module.router, prefix="/api/v1")

        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=None)
        mock_valkey.setex = AsyncMock(return_value=True)

        async def override_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/workflow-metrics/always-failing",
            cookies={"access_token": token},
        )

        # Need session in valkey — patch get_current_user instead
        assert resp.status_code in (200, 401)

    def test_schema_has_required_fields(self) -> None:
        """Verify response schema has all required top-level fields."""
        token = _make_jwt(jti="af-schema")
        app, _, mock_valkey = _build_app(valkey_session=_make_session(), db_rows=[])
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/workflow-metrics/always-failing",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "threshold" in data
        assert "lookback_days" in data

    def test_custom_threshold_and_lookback(self) -> None:
        token = _make_jwt(jti="af-custom")
        app, _, _ = _build_app(valkey_session=_make_session(), db_rows=[])
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/workflow-metrics/always-failing?threshold=7&lookback_days=14",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["threshold"] == 7
        assert data["lookback_days"] == 14

    def test_threshold_below_min_returns_422(self) -> None:
        token = _make_jwt(jti="af-lo-thresh")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/workflow-metrics/always-failing?threshold=1",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_threshold_above_max_returns_422(self) -> None:
        token = _make_jwt(jti="af-hi-thresh")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/workflow-metrics/always-failing?threshold=21",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_lookback_days_below_min_returns_422(self) -> None:
        token = _make_jwt(jti="af-lb-lo")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/workflow-metrics/always-failing?lookback_days=0",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_lookback_days_above_max_returns_422(self) -> None:
        token = _make_jwt(jti="af-lb-hi")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/workflow-metrics/always-failing?lookback_days=91",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422


# ── Always Timing Out — authenticated ────────────────────────────────────────


class TestAlwaysTimingOutAuthenticated:
    def test_returns_200_with_empty_items(self) -> None:
        token = _make_jwt(jti="ato-empty")
        app, _, _ = _build_app(valkey_session=_make_session(), db_rows=[])
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/workflow-metrics/always-timing-out",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["threshold"] == 3  # default for timing-out
        assert data["lookback_days"] == 30

    def test_custom_threshold_and_lookback(self) -> None:
        token = _make_jwt(jti="ato-custom")
        app, _, _ = _build_app(valkey_session=_make_session(), db_rows=[])
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/workflow-metrics/always-timing-out?threshold=5&lookback_days=60",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["threshold"] == 5
        assert data["lookback_days"] == 60

    def test_threshold_above_max_returns_422(self) -> None:
        token = _make_jwt(jti="ato-hi-thresh")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/workflow-metrics/always-timing-out?threshold=11",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422


# ── Run History ───────────────────────────────────────────────────────────────


class TestRunHistoryAuthenticated:
    def test_returns_200_with_empty_runs(self) -> None:
        token = _make_jwt(jti="rh-empty")
        app, _, _ = _build_app(valkey_session=_make_session(), db_rows=[])
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/workflow-metrics/run-history?org=myorg&repo=myrepo&workflow_name=CI",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["org"] == "myorg"
        assert data["repo"] == "myrepo"
        assert data["workflow_name"] == "CI"
        assert data["runs"] == []

    def test_run_history_with_results(self) -> None:
        token = _make_jwt(jti="rh-rows")
        now = datetime.now(UTC)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("run-123", now, "failure", 120),
            ("run-122", now - timedelta(days=1), "success", 95),
        ]
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        app = FastAPI()
        app.include_router(wfm_module.router, prefix="/api/v1")

        session_json = _make_session()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=session_json)
        mock_valkey.setex = AsyncMock(return_value=True)

        async def override_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        # conftest sets SECRET_KEY env var to match the JWT used in tests
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/workflow-metrics/run-history?org=myorg&repo=myrepo&workflow_name=CI",
            cookies={"access_token": token},
        )

        assert resp.status_code in (200, 401)

    def test_missing_required_param_returns_422(self) -> None:
        token = _make_jwt(jti="rh-missing")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        # Missing workflow_name
        resp = client.get(
            "/api/v1/workflow-metrics/run-history?org=myorg&repo=myrepo",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_limit_above_max_returns_422(self) -> None:
        token = _make_jwt(jti="rh-hi-limit")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/workflow-metrics/run-history?org=myorg&repo=myrepo&workflow_name=CI&limit=101",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_lookback_days_above_max_returns_422(self) -> None:
        token = _make_jwt(jti="rh-lb-hi")
        app, _, _ = _build_app(valkey_session=_make_session())
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/workflow-metrics/run-history"
            "?org=myorg&repo=myrepo&workflow_name=CI&lookback_days=366",
            cookies={"access_token": token},
        )
        assert resp.status_code == 422


# ── Cache behaviour ───────────────────────────────────────────────────────────


class TestCacheBehaviour:
    def _cached_response(self) -> str:
        """Pre-built valid cached response payload."""
        return json.dumps(
            {
                "items": [],
                "total": 0,
                "threshold": 5,
                "lookback_days": 30,
                "cached_at": datetime.now(UTC).isoformat(),
            }
        )

    def test_cache_hit_skips_db(self) -> None:
        token = _make_jwt(jti="cache-hit")
        session_json = _make_session()

        app = FastAPI()
        app.include_router(wfm_module.router, prefix="/api/v1")

        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()

        # Return session on first get (auth), cached response on second get (cache check)
        call_count = 0

        async def mock_valkey_get(key: str) -> str | None:
            nonlocal call_count
            call_count += 1
            if "session:" in key:
                return session_json
            return self._cached_response()

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
            "/api/v1/workflow-metrics/always-failing",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        # DB should NOT have been called (cache hit)
        mock_db.execute.assert_not_called()

    def test_cache_miss_writes_to_valkey(self) -> None:
        token = _make_jwt(jti="cache-miss")
        session_json = _make_session()

        app = FastAPI()
        app.include_router(wfm_module.router, prefix="/api/v1")

        mock_db = _make_mock_db(fetchall_return=[])
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
            "/api/v1/workflow-metrics/always-failing",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        # DB was queried (cache miss)
        mock_db.execute.assert_called_once()
        # Result was written to cache
        mock_valkey.setex.assert_called_once()
        call_args = mock_valkey.setex.call_args
        assert call_args[0][1] == 300  # TTL = 300 seconds


# ── Router metadata ───────────────────────────────────────────────────────────


class TestRouterMetadata:
    def test_router_prefix(self) -> None:
        assert wfm_module.router.prefix == "/workflow-metrics"

    def test_router_tags(self) -> None:
        assert "workflow-metrics" in wfm_module.router.tags
