"""Tests for the dev_activity router (usage-stats and developers endpoints).

Tests cover:
- Unauthenticated requests → 401
- Authenticated request returns 200 with correct schema
- RBAC scope enforcement (403 when no orgs)
- Response structure validation
- Developers endpoint returns per-developer aggregated stats
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
from app.routers import dev_activity as dev_activity_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "da-jti") -> str:
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
    mock_result.scalar.return_value = 0
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _build_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(dev_activity_module.router, prefix="/api/v1")

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


class TestUsageStatsUnauthenticated:
    def test_usage_stats_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/dev-activity/usage-stats")
        assert resp.status_code == 401


# ─── Authenticated — 403 when no orgs ─────────────────────────────────────────


class TestUsageStatsNoOrgs:
    def test_returns_403_when_no_scoped_orgs(self) -> None:
        token = _make_jwt(jti="noorgs-jti")
        app, _, _ = _build_app(valkey_session=_make_session(orgs=["my-org"]))

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=[]),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/dev-activity/usage-stats",
                cookies={"access_token": token},
            )
        assert resp.status_code == 403


# ─── Authenticated — success path ─────────────────────────────────────────────


class TestUsageStatsAuthenticated:
    def _mock_db_with_responses(self) -> AsyncMock:
        """Create a mock DB where each execute call returns different data."""
        db = AsyncMock()
        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1

            result = MagicMock()

            if call_count == 1:
                # _git_action_counts: returns action → count rows
                result.fetchall.return_value = [
                    ("git.clone", 100),
                    ("git.push", 50),
                    ("git.fetch", 5),
                ]
            elif call_count == 2:
                # _top_cloners
                result.fetchall.return_value = [
                    ("github-actions[bot]", 95, True),
                    ("jmassardo", 5, False),
                ]
            elif call_count == 3:
                # _top_pushers
                result.fetchall.return_value = [
                    ("jmassardo", 50, ["org/repo-a", "org/repo-b"]),
                ]
            elif call_count == 4:
                # _daily_git_trend
                result.fetchall.return_value = [
                    ("2026-03-20", 10, 5, 1),
                    ("2026-03-21", 8, 3, 0),
                ]
            elif call_count == 5:
                # _api_stats: COUNT(*) → 0 (no api events)
                result.scalar.return_value = 0
            elif call_count == 6:
                # _bot_vs_human
                result.fetchall.return_value = [
                    (True, 95, ["github-actions[bot]"]),
                    (False, 60, ["jmassardo"]),
                ]
            else:
                result.fetchall.return_value = []
                result.scalar.return_value = 0

            return result

        db.execute = mock_execute
        return db

    def test_usage_stats_returns_200_with_correct_structure(self) -> None:
        token = _make_jwt()
        session = _make_session()

        app = FastAPI()
        app.include_router(dev_activity_module.router, prefix="/api/v1")

        mock_db = self._mock_db_with_responses()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=session)

        async def override_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/dev-activity/usage-stats",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()

        # Verify top-level keys
        assert "git_stats" in data
        assert "api_stats" in data
        assert "bot_vs_human" in data

        # Verify git_stats structure
        git = data["git_stats"]
        assert git["total_clones"] == 100
        assert git["total_pushes"] == 50
        assert git["total_fetches"] == 5
        assert len(git["top_cloners"]) == 2
        assert git["top_cloners"][0]["actor"] == "github-actions[bot]"
        assert git["top_cloners"][0]["is_bot"] is True
        assert git["top_cloners"][1]["actor"] == "jmassardo"
        assert git["top_cloners"][1]["is_bot"] is False
        assert len(git["top_pushers"]) == 1
        assert git["top_pushers"][0]["repos"] == ["org/repo-a", "org/repo-b"]
        assert len(git["daily_trend"]) == 2
        assert git["daily_trend"][0]["date"] == "2026-03-20"
        assert git["daily_trend"][0]["clones"] == 10

        # Verify api_stats when unavailable
        api = data["api_stats"]
        assert api["available"] is False
        assert api["total_requests"] == 0
        assert api["top_users"] == []

        # Verify bot_vs_human
        bvh = data["bot_vs_human"]
        assert bvh["bot_events"] == 95
        assert bvh["human_events"] == 60
        assert "github-actions[bot]" in bvh["bot_actors"]
        assert "jmassardo" in bvh["human_actors"]

    def test_usage_stats_accepts_lookback_days_param(self) -> None:
        token = _make_jwt(jti="lb-jti")
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/dev-activity/usage-stats?lookback_days=7",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200

    def test_usage_stats_rejects_invalid_lookback_days(self) -> None:
        token = _make_jwt(jti="invalid-lb")
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/dev-activity/usage-stats?lookback_days=0",
                cookies={"access_token": token},
            )

        assert resp.status_code == 422

    def test_usage_stats_rejects_lookback_days_too_large(self) -> None:
        token = _make_jwt(jti="bigval-jti")
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/dev-activity/usage-stats?lookback_days=500",
                cookies={"access_token": token},
            )

        assert resp.status_code == 422


# ─── Authenticated — with API events available ────────────────────────────────


class TestUsageStatsWithApiEvents:
    def _mock_db_with_api_data(self) -> AsyncMock:
        """Mock DB returning api events available."""
        db = AsyncMock()
        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1

            result = MagicMock()

            if call_count == 1:
                # _git_action_counts: empty
                result.fetchall.return_value = []
            elif call_count == 2:
                # _top_cloners: empty
                result.fetchall.return_value = []
            elif call_count == 3:
                # _top_pushers: empty
                result.fetchall.return_value = []
            elif call_count == 4:
                # _daily_git_trend: empty
                result.fetchall.return_value = []
            elif call_count == 5:
                # _api_stats: COUNT(*) → 42
                result.scalar.return_value = 42
            elif call_count == 6:
                # top api users
                result.fetchall.return_value = [
                    ("admin-user", 30),
                    ("service-bot[bot]", 12),
                ]
            elif call_count == 7:
                # top endpoints
                result.fetchall.return_value = [
                    ("GET /repos", 25),
                    ("POST /orgs", 17),
                ]
            elif call_count == 8:
                # daily api trend
                result.fetchall.return_value = [
                    ("2026-03-20", 20),
                    ("2026-03-21", 22),
                ]
            elif call_count == 9:
                # _bot_vs_human: empty (no git events)
                result.fetchall.return_value = []
            else:
                result.fetchall.return_value = []
                result.scalar.return_value = 0

            return result

        db.execute = mock_execute
        return db

    def test_api_stats_returned_when_available(self) -> None:
        token = _make_jwt(jti="api-jti")
        session = _make_session()

        app = FastAPI()
        app.include_router(dev_activity_module.router, prefix="/api/v1")

        mock_db = self._mock_db_with_api_data()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=session)

        async def override_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/dev-activity/usage-stats",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()

        api = data["api_stats"]
        assert api["available"] is True
        assert api["total_requests"] == 42
        assert len(api["top_users"]) == 2
        assert api["top_users"][0]["actor"] == "admin-user"
        assert api["top_users"][0]["count"] == 30
        assert len(api["top_endpoints"]) == 2
        assert api["top_endpoints"][0]["endpoint"] == "GET /repos"
        assert len(api["daily_trend"]) == 2

        # git stats should be zeros
        git = data["git_stats"]
        assert git["total_clones"] == 0
        assert git["total_pushes"] == 0
        assert git["total_fetches"] == 0

        # bot_vs_human should be empty (no git events)
        bvh = data["bot_vs_human"]
        assert bvh["bot_events"] == 0
        assert bvh["human_events"] == 0


# ─── Empty data path ──────────────────────────────────────────────────────────


class TestUsageStatsEmptyData:
    def test_returns_zeros_when_no_events_exist(self) -> None:
        token = _make_jwt(jti="empty-jti")
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/dev-activity/usage-stats",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()

        git = data["git_stats"]
        assert git["total_clones"] == 0
        assert git["total_pushes"] == 0
        assert git["total_fetches"] == 0
        assert git["top_cloners"] == []
        assert git["top_pushers"] == []
        assert git["daily_trend"] == []

        api = data["api_stats"]
        assert api["available"] is False
        assert api["total_requests"] == 0

        bvh = data["bot_vs_human"]
        assert bvh["bot_events"] == 0
        assert bvh["human_events"] == 0
        assert bvh["bot_actors"] == []
        assert bvh["human_actors"] == []


# ─── Developers endpoint tests ───────────────────────────────────────────────


class TestDevelopersUnauthenticated:
    def test_developers_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/dev-activity/developers")
        assert resp.status_code == 401


class TestDevelopersNoOrgs:
    def test_returns_403_when_no_scoped_orgs(self) -> None:
        token = _make_jwt(jti="dev-noorgs-jti")
        app, _, _ = _build_app(valkey_session=_make_session(orgs=["my-org"]))

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=[]),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/dev-activity/developers",
                cookies={"access_token": token},
            )
        assert resp.status_code == 403


class TestDevelopersAuthenticated:
    def _mock_db_with_developer_data(self) -> AsyncMock:
        """Mock DB returning developer aggregation data."""
        db = AsyncMock()

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            result = MagicMock()
            last_active = datetime(2026, 3, 25, 10, 30, 0, tzinfo=UTC)
            result.fetchall.return_value = [
                # actor, event_count, pr_count, review_count, repos, last_active,
                # w6, w5, w4, w3, w2, w1, w0
                (
                    "alice",
                    25,
                    10,
                    3,
                    ["org/repo-a", "org/repo-b", "org/repo-c"],
                    last_active,
                    5,
                    4,
                    4,
                    4,
                    3,
                    3,
                    2,
                ),
                (
                    "bob",
                    12,
                    5,
                    1,
                    ["org/repo-a"],
                    last_active - timedelta(days=2),
                    3,
                    2,
                    2,
                    2,
                    1,
                    1,
                    1,
                ),
            ]
            return result

        db.execute = mock_execute
        return db

    def test_developers_returns_200_with_correct_structure(self) -> None:
        token = _make_jwt(jti="dev-ok-jti")
        session = _make_session()

        app = FastAPI()
        app.include_router(dev_activity_module.router, prefix="/api/v1")

        mock_db = self._mock_db_with_developer_data()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=session)

        async def override_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/dev-activity/developers",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()

        assert "developers" in data
        assert "lookback_days" in data
        assert data["lookback_days"] == 90

        devs = data["developers"]
        assert len(devs) == 2

        # First developer
        alice = devs[0]
        assert alice["login"] == "alice"
        assert alice["event_count"] == 25
        assert alice["pr_count"] == 10
        assert alice["review_count"] == 3
        assert alice["repo_count"] == 3
        assert alice["top_repos"] == ["org/repo-a", "org/repo-b", "org/repo-c"]
        assert alice["last_active"] is not None
        assert len(alice["weekly_counts"]) == 7
        # weekly_counts order: [w0, w1, w2, w3, w4, w5, w6] (oldest first)
        assert alice["weekly_counts"] == [2, 3, 3, 4, 4, 4, 5]

        # Second developer
        bob = devs[1]
        assert bob["login"] == "bob"
        assert bob["event_count"] == 12
        assert bob["pr_count"] == 5
        assert bob["repo_count"] == 1

    def test_developers_accepts_lookback_days_param(self) -> None:
        token = _make_jwt(jti="dev-lb-jti")
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/dev-activity/developers?lookback_days=30",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        assert resp.json()["lookback_days"] == 30

    def test_developers_rejects_invalid_lookback_days(self) -> None:
        token = _make_jwt(jti="dev-invalid-lb")
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/dev-activity/developers?lookback_days=0",
                cookies={"access_token": token},
            )

        assert resp.status_code == 422

    def test_developers_rejects_lookback_days_too_large(self) -> None:
        token = _make_jwt(jti="dev-bigval-jti")
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/dev-activity/developers?lookback_days=500",
                cookies={"access_token": token},
            )

        assert resp.status_code == 422


class TestDevelopersEmptyData:
    def test_returns_empty_list_when_no_repo_events(self) -> None:
        token = _make_jwt(jti="dev-empty-jti")
        app, _, _ = _build_app(valkey_session=_make_session())

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/dev-activity/developers",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()

        assert data["developers"] == []
        assert data["lookback_days"] == 90


class TestDevelopersTopReposLimit:
    def _mock_db_with_many_repos(self) -> AsyncMock:
        """Mock DB returning a developer with more than 5 repos."""
        db = AsyncMock()

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            result = MagicMock()
            last_active = datetime(2026, 3, 25, 10, 30, 0, tzinfo=UTC)
            many_repos = [f"org/repo-{i}" for i in range(10)]
            result.fetchall.return_value = [
                (
                    "prolific-dev",
                    100,
                    40,
                    10,
                    many_repos,
                    last_active,
                    15,
                    15,
                    15,
                    15,
                    15,
                    15,
                    10,
                ),
            ]
            return result

        db.execute = mock_execute
        return db

    def test_top_repos_limited_to_5(self) -> None:
        token = _make_jwt(jti="dev-repos-jti")
        session = _make_session()

        app = FastAPI()
        app.include_router(dev_activity_module.router, prefix="/api/v1")

        mock_db = self._mock_db_with_many_repos()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=session)

        async def override_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
            yield mock_valkey

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_valkey] = override_valkey

        with patch(
            "app.routers.dev_activity.rbac_service.get_scoped_orgs",
            AsyncMock(return_value=["my-org"]),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get(
                "/api/v1/dev-activity/developers",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        dev = resp.json()["developers"][0]
        assert len(dev["top_repos"]) == 5
        assert dev["repo_count"] == 10
