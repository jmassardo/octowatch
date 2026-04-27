"""Unit tests for the issue-stats router (/api/v1/issue-stats).

Covers:
- /by-org endpoint response shape and totals
- /by-repo endpoint response shape and totals
- Empty result handling
- Service function logic
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture()
def app():
    return create_app()


def _fake_user(*, roles: list[str] | None = None, login: str = "admin"):
    user = MagicMock()
    user.github_login = login
    user.roles = roles or ["sys_admin"]
    return user


# ── /by-org ──────────────────────────────────────────────────────────────────


class TestByOrgEndpoint:
    """Tests for the by-org endpoint response shape."""

    @pytest.mark.asyncio
    async def test_by_org_returns_correct_shape(self, app) -> None:
        mock_service_result = [
            {
                "org": "acme-corp",
                "opened": 25,
                "closed": 18,
                "net_open": 7,
                "avg_hours_to_close": 48.5,
            },
            {
                "org": "beta-org",
                "opened": 10,
                "closed": 12,
                "net_open": -2,
                "avg_hours_to_close": 24.0,
            },
        ]

        with (
            patch("app.routers.issue_stats.require_role", return_value=lambda: _fake_user()),
            patch(
                "app.routers.issue_stats.issue_stats_service.get_issue_stats_by_org",
                new_callable=AsyncMock,
                return_value=mock_service_result,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/issue-stats/by-org?window_days=30")

        if resp.status_code == 200:
            data = resp.json()
            assert "window_days" in data
            assert "total_opened" in data
            assert "total_closed" in data
            assert "orgs" in data
            assert data["total_opened"] == 35
            assert data["total_closed"] == 30
            assert len(data["orgs"]) == 2

            org = data["orgs"][0]
            assert "org" in org
            assert "opened" in org
            assert "closed" in org
            assert "net_open" in org
            assert "avg_hours_to_close" in org

    @pytest.mark.asyncio
    async def test_by_org_empty_result(self, app) -> None:
        with (
            patch("app.routers.issue_stats.require_role", return_value=lambda: _fake_user()),
            patch(
                "app.routers.issue_stats.issue_stats_service.get_issue_stats_by_org",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/issue-stats/by-org")

        if resp.status_code == 200:
            data = resp.json()
            assert data["total_opened"] == 0
            assert data["total_closed"] == 0
            assert data["orgs"] == []


# ── /by-repo ─────────────────────────────────────────────────────────────────


class TestByRepoEndpoint:
    """Tests for the by-repo endpoint response shape."""

    @pytest.mark.asyncio
    async def test_by_repo_returns_correct_shape(self, app) -> None:
        mock_service_result = [
            {
                "org": "acme-corp",
                "repo": "acme-corp/api",
                "opened": 15,
                "closed": 10,
                "net_open": 5,
                "avg_hours_to_close": 36.2,
            },
            {
                "org": "acme-corp",
                "repo": "acme-corp/web",
                "opened": 10,
                "closed": 8,
                "net_open": 2,
                "avg_hours_to_close": 72.0,
            },
        ]

        with (
            patch("app.routers.issue_stats.require_role", return_value=lambda: _fake_user()),
            patch(
                "app.routers.issue_stats.issue_stats_service.get_issue_stats_by_repo",
                new_callable=AsyncMock,
                return_value=mock_service_result,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/issue-stats/by-repo?window_days=90")

        if resp.status_code == 200:
            data = resp.json()
            assert "window_days" in data
            assert "total_opened" in data
            assert "total_closed" in data
            assert "repos" in data
            assert data["total_opened"] == 25
            assert data["total_closed"] == 18
            assert len(data["repos"]) == 2

            repo = data["repos"][0]
            assert "org" in repo
            assert "repo" in repo
            assert "opened" in repo
            assert "closed" in repo
            assert "net_open" in repo
            assert "avg_hours_to_close" in repo

    @pytest.mark.asyncio
    async def test_by_repo_with_org_filter(self, app) -> None:
        mock_service_result = [
            {
                "org": "acme-corp",
                "repo": "acme-corp/api",
                "opened": 15,
                "closed": 10,
                "net_open": 5,
                "avg_hours_to_close": None,
            },
        ]

        with (
            patch("app.routers.issue_stats.require_role", return_value=lambda: _fake_user()),
            patch(
                "app.routers.issue_stats.issue_stats_service.get_issue_stats_by_repo",
                new_callable=AsyncMock,
                return_value=mock_service_result,
            ) as _mock_fn,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/issue-stats/by-repo?window_days=30&org=acme-corp")

        if resp.status_code == 200:
            data = resp.json()
            assert len(data["repos"]) == 1
            assert data["repos"][0]["org"] == "acme-corp"


# ── Service unit tests ───────────────────────────────────────────────────────


class TestIssueStatsService:
    """Direct unit tests for the service functions."""

    @pytest.mark.asyncio
    async def test_get_issue_stats_by_org(self) -> None:
        from app.services.issue_stats_service import get_issue_stats_by_org

        # Mock main query result
        fake_row = MagicMock()
        fake_row.org = "acme-corp"
        fake_row.opened = 20
        fake_row.closed = 15

        fake_main_result = MagicMock()
        fake_main_result.fetchall.return_value = [fake_row]

        # Mock avg query result
        fake_avg_row = MagicMock()
        fake_avg_row.org = "acme-corp"
        fake_avg_row.avg_hours_to_close = 48.123

        fake_avg_result = MagicMock()
        fake_avg_result.fetchall.return_value = [fake_avg_row]

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[fake_main_result, fake_avg_result])

        result = await get_issue_stats_by_org(session, window_days=30)

        assert len(result) == 1
        assert result[0]["org"] == "acme-corp"
        assert result[0]["opened"] == 20
        assert result[0]["closed"] == 15
        assert result[0]["net_open"] == 5
        assert result[0]["avg_hours_to_close"] == 48.1

    @pytest.mark.asyncio
    async def test_get_issue_stats_by_repo(self) -> None:
        from app.services.issue_stats_service import get_issue_stats_by_repo

        fake_row = MagicMock()
        fake_row.org = "acme-corp"
        fake_row.repo = "acme-corp/api"
        fake_row.opened = 10
        fake_row.closed = 8

        fake_main_result = MagicMock()
        fake_main_result.fetchall.return_value = [fake_row]

        fake_avg_row = MagicMock()
        fake_avg_row.repo = "acme-corp/api"
        fake_avg_row.avg_hours_to_close = 24.0

        fake_avg_result = MagicMock()
        fake_avg_result.fetchall.return_value = [fake_avg_row]

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[fake_main_result, fake_avg_result])

        result = await get_issue_stats_by_repo(session, window_days=30)

        assert len(result) == 1
        assert result[0]["org"] == "acme-corp"
        assert result[0]["repo"] == "acme-corp/api"
        assert result[0]["opened"] == 10
        assert result[0]["closed"] == 8
        assert result[0]["net_open"] == 2
        assert result[0]["avg_hours_to_close"] == 24.0

    @pytest.mark.asyncio
    async def test_get_issue_stats_by_org_with_org_filter(self) -> None:
        from app.services.issue_stats_service import get_issue_stats_by_org

        fake_row = MagicMock()
        fake_row.org = "acme-corp"
        fake_row.opened = 5
        fake_row.closed = 3

        fake_main_result = MagicMock()
        fake_main_result.fetchall.return_value = [fake_row]

        fake_avg_result = MagicMock()
        fake_avg_result.fetchall.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[fake_main_result, fake_avg_result])

        result = await get_issue_stats_by_org(session, window_days=30, org="acme-corp")

        assert len(result) == 1
        assert result[0]["org"] == "acme-corp"
        assert result[0]["avg_hours_to_close"] is None

    @pytest.mark.asyncio
    async def test_get_issue_stats_by_org_empty(self) -> None:
        from app.services.issue_stats_service import get_issue_stats_by_org

        fake_main_result = MagicMock()
        fake_main_result.fetchall.return_value = []

        fake_avg_result = MagicMock()
        fake_avg_result.fetchall.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[fake_main_result, fake_avg_result])

        result = await get_issue_stats_by_org(session, window_days=30)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_issue_stats_by_repo_null_avg(self) -> None:
        from app.services.issue_stats_service import get_issue_stats_by_repo

        fake_row = MagicMock()
        fake_row.org = "acme-corp"
        fake_row.repo = "acme-corp/api"
        fake_row.opened = 5
        fake_row.closed = 0

        fake_main_result = MagicMock()
        fake_main_result.fetchall.return_value = [fake_row]

        fake_avg_result = MagicMock()
        fake_avg_result.fetchall.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[fake_main_result, fake_avg_result])

        result = await get_issue_stats_by_repo(session, window_days=90)

        assert len(result) == 1
        assert result[0]["net_open"] == 5
        assert result[0]["avg_hours_to_close"] is None
