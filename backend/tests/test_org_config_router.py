"""Unit tests for the org_config router endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user, get_db
from app.routers.org_config import router


@pytest.fixture
def app() -> FastAPI:
    """Create a minimal FastAPI app with the org_config router."""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def mock_admin_user():
    user = MagicMock()
    user.github_login = "admin-user"
    user.github_id = 1
    user.roles = ["sys_admin"]
    user.scoped_orgs = ["my-org"]
    user.has_role = MagicMock(return_value=True)
    return user


@pytest.fixture
def mock_viewer_user():
    user = MagicMock()
    user.github_login = "viewer-user"
    user.github_id = 2
    user.roles = ["viewer"]
    user.scoped_orgs = ["my-org"]
    user.has_role = MagicMock(return_value=False)
    return user


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    return session


@pytest.fixture
def admin_client(app, mock_admin_user, mock_db_session):
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_db] = lambda: mock_db_session
    return app, mock_db_session


@pytest.fixture
def viewer_client(app, mock_viewer_user, mock_db_session):
    app.dependency_overrides[get_current_user] = lambda: mock_viewer_user
    app.dependency_overrides[get_db] = lambda: mock_db_session
    return app, mock_db_session


class TestGetOrgConfig:
    """Tests for GET /api/v1/orgs/{org_slug}/config."""

    @pytest.mark.anyio
    async def test_returns_default_when_no_row(self, admin_client):
        app, mock_db = admin_client
        # Simulate no row found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/orgs/my-org/config")

        assert resp.status_code == 200
        data = resp.json()
        assert data["org_slug"] == "my-org"
        assert data["copilot_cost_per_seat"] == 19.0

    @pytest.mark.anyio
    async def test_returns_custom_cost(self, admin_client):
        app, mock_db = admin_client
        row = MagicMock()
        row.org_slug = "my-org"
        row.copilot_cost_per_seat = 39.0
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/orgs/my-org/config")

        assert resp.status_code == 200
        data = resp.json()
        assert data["copilot_cost_per_seat"] == 39.0

    @pytest.mark.anyio
    async def test_returns_default_when_null(self, admin_client):
        app, mock_db = admin_client
        row = MagicMock()
        row.org_slug = "my-org"
        row.copilot_cost_per_seat = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/orgs/my-org/config")

        assert resp.status_code == 200
        data = resp.json()
        assert data["copilot_cost_per_seat"] == 19.0


class TestUpdateOrgConfig:
    """Tests for PATCH /api/v1/orgs/{org_slug}/config."""

    @pytest.mark.anyio
    async def test_creates_config_when_no_row(self, admin_client):
        app, mock_db = admin_client
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        # After refresh, the row should have the new values
        async def fake_refresh(obj):
            obj.org_slug = "my-org"
            obj.copilot_cost_per_seat = 39.0

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                "/api/v1/orgs/my-org/config",
                json={"copilot_cost_per_seat": 39.0},
                cookies={"csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["copilot_cost_per_seat"] == 39.0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_updates_existing_config(self, admin_client):
        app, mock_db = admin_client
        row = MagicMock()
        row.org_slug = "my-org"
        row.copilot_cost_per_seat = 19.0
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        async def fake_refresh(obj):
            obj.copilot_cost_per_seat = 42.0

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                "/api/v1/orgs/my-org/config",
                json={"copilot_cost_per_seat": 42.0},
                cookies={"csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["copilot_cost_per_seat"] == 42.0

    @pytest.mark.anyio
    async def test_reset_to_default_with_null(self, admin_client):
        app, mock_db = admin_client
        row = MagicMock()
        row.org_slug = "my-org"
        row.copilot_cost_per_seat = 39.0
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        async def fake_refresh(obj):
            obj.copilot_cost_per_seat = None

        mock_db.refresh = AsyncMock(side_effect=fake_refresh)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                "/api/v1/orgs/my-org/config",
                json={"copilot_cost_per_seat": None},
                cookies={"csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        data = resp.json()
        # null falls back to default 19
        assert data["copilot_cost_per_seat"] == 19.0
