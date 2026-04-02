"""Unit tests for the features router.

Tests cover:
- GET /api/v1/features — returns feature flags with defaults
- GET /api/v1/features — returns stored feature flags
- PUT /api/v1/features — admin can update feature flags
- PUT /api/v1/features — ignores unknown feature keys
- PUT /api/v1/features — non-admin is rejected
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user, get_db
from app.routers.features import router


@pytest.fixture
def app() -> FastAPI:
    """Create a minimal FastAPI app with the features router."""
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
    return AsyncMock()


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


class TestGetFeatures:
    """Tests for GET /api/v1/features."""

    @pytest.mark.anyio
    async def test_returns_defaults_when_no_stored_values(self, admin_client):
        app, _ = admin_client

        with patch(
            "app.routers.features.get_setting",
            new_callable=AsyncMock,
            return_value=None,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/features")

        assert resp.status_code == 200
        data = resp.json()
        assert data["copilot_insights"] is False
        assert data["velocity"] is True
        assert data["dev_activity"] is True
        assert data["org_health"] is True

    @pytest.mark.anyio
    async def test_returns_stored_values(self, admin_client):
        app, _ = admin_client

        async def mock_get_setting(_db, key):
            if key == "feature_copilot_insights":
                return "true"
            if key == "feature_velocity":
                return "false"
            return None

        with patch(
            "app.routers.features.get_setting",
            side_effect=mock_get_setting,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/features")

        assert resp.status_code == 200
        data = resp.json()
        assert data["copilot_insights"] is True
        assert data["velocity"] is False
        assert data["dev_activity"] is True  # default
        assert data["org_health"] is True  # default

    @pytest.mark.anyio
    async def test_interprets_truthy_values(self, admin_client):
        """Various truthy string values should all resolve to True."""
        app, _ = admin_client

        for truthy_val in ["true", "True", "TRUE", "1", "yes", "on"]:

            async def mock_get_setting(_db, key, val=truthy_val):
                if key == "feature_copilot_insights":
                    return val
                return None

            with patch(
                "app.routers.features.get_setting",
                side_effect=mock_get_setting,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.get("/api/v1/features")

            assert resp.json()["copilot_insights"] is True, (
                f"Expected 'true' for value '{truthy_val}'"
            )

    @pytest.mark.anyio
    async def test_interprets_falsy_values(self, admin_client):
        """Non-truthy string values should resolve to False."""
        app, _ = admin_client

        async def mock_get_setting(_db, key):
            if key == "feature_copilot_insights":
                return "false"
            if key == "feature_velocity":
                return "no"
            return None

        with patch(
            "app.routers.features.get_setting",
            side_effect=mock_get_setting,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/v1/features")

        data = resp.json()
        assert data["copilot_insights"] is False
        assert data["velocity"] is False


class TestUpdateFeatures:
    """Tests for PUT /api/v1/features."""

    @pytest.mark.anyio
    async def test_admin_can_update_features(self, admin_client):
        app, _ = admin_client

        with patch(
            "app.routers.features.set_setting",
            new_callable=AsyncMock,
        ) as mock_set:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(
                    "/api/v1/features",
                    json={"copilot_insights": True, "velocity": False},
                    cookies={"csrf_token": "tok"},
                    headers={"X-CSRF-Token": "tok"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["copilot_insights"] is True
        assert data["velocity"] is False
        assert mock_set.call_count == 2

    @pytest.mark.anyio
    async def test_set_setting_called_with_correct_args(self, admin_client):
        app, mock_db = admin_client

        with patch(
            "app.routers.features.set_setting",
            new_callable=AsyncMock,
        ) as mock_set:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.put(
                    "/api/v1/features",
                    json={"copilot_insights": True},
                    cookies={"csrf_token": "tok"},
                    headers={"X-CSRF-Token": "tok"},
                )

        mock_set.assert_called_once_with(
            mock_db,
            "feature_copilot_insights",
            "true",
            category="features",
            sensitivity="config",
            description="Feature toggle: copilot_insights",
            changed_by="admin-user",
        )

    @pytest.mark.anyio
    async def test_ignores_unknown_feature_keys(self, admin_client):
        app, _ = admin_client

        with patch(
            "app.routers.features.set_setting",
            new_callable=AsyncMock,
        ) as mock_set:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(
                    "/api/v1/features",
                    json={"unknown_feature": True, "copilot_insights": True},
                    cookies={"csrf_token": "tok"},
                    headers={"X-CSRF-Token": "tok"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "unknown_feature" not in data
        assert data["copilot_insights"] is True
        # Only copilot_insights should be set, not unknown_feature
        assert mock_set.call_count == 1

    @pytest.mark.anyio
    async def test_empty_payload_returns_empty(self, admin_client):
        app, _ = admin_client

        with patch(
            "app.routers.features.set_setting",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(
                    "/api/v1/features",
                    json={},
                    cookies={"csrf_token": "tok"},
                    headers={"X-CSRF-Token": "tok"},
                )

        assert resp.status_code == 200
        assert resp.json() == {}

    @pytest.mark.anyio
    async def test_viewer_cannot_update_features(self, viewer_client):
        app, _ = viewer_client

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                "/api/v1/features",
                json={"copilot_insights": True},
                cookies={"csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 403
