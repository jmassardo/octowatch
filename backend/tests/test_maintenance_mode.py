from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, verify_csrf
from app.middleware.maintenance import MaintenanceModeMiddleware
from app.services.maintenance_service import MaintenanceStatus


def _mock_db() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    return db


def _user(*roles: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        github_login="maintenance-admin",
        github_id=42,
        roles=list(roles),
        scoped_orgs=["octo-org"],
        scoped_repos=[],
        scope_type="global",
        jti="maintenance-jti",
        session_expires_at="2099-01-01T00:00:00+00:00",
    )


def _maintenance_router_app(db: AsyncMock, user: AuthenticatedUser) -> FastAPI:
    from app.routers.maintenance import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[verify_csrf] = lambda: None
    return app


class TestMaintenanceRouter:
    @pytest.mark.asyncio
    async def test_get_status_available_to_authenticated_users(self) -> None:
        app = _maintenance_router_app(_mock_db(), _user("viewer"))
        expected = MaintenanceStatus(
            enabled=True,
            message="Scheduled maintenance in progress",
            severity="warning",
            block_writes=True,
        )

        with patch(
            "app.routers.maintenance.get_maintenance_status",
            new=AsyncMock(return_value=expected),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/api/v1/admin/maintenance")

        assert response.status_code == 200
        assert response.json() == {
            "enabled": True,
            "message": "Scheduled maintenance in progress",
            "severity": "warning",
            "block_writes": True,
            "started_at": None,
            "estimated_end": None,
        }

    @pytest.mark.asyncio
    async def test_update_status_persists_and_audits(self) -> None:
        db = _mock_db()
        app = _maintenance_router_app(db, _user("sys_admin"))
        saved = MaintenanceStatus(
            enabled=True,
            message="Deploying hotfixes",
            severity="critical",
            block_writes=True,
        )

        with (
            patch(
                "app.routers.maintenance.save_maintenance_status",
                new=AsyncMock(return_value=saved),
            ) as save_mock,
            patch(
                "app.routers.maintenance.load_settings_overlay",
                new=AsyncMock(),
            ) as overlay_mock,
            patch(
                "app.routers.maintenance.log_action",
                new=AsyncMock(),
            ) as audit_mock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.put(
                    "/api/v1/admin/maintenance",
                    json={
                        "enabled": True,
                        "message": "Deploying hotfixes",
                        "severity": "critical",
                        "block_writes": True,
                        "estimated_end": None,
                    },
                )

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["severity"] == "critical"
        save_mock.assert_awaited_once()
        overlay_mock.assert_awaited_once_with(db)
        audit_mock.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_toggle_endpoint_flips_enabled_state(self) -> None:
        db = _mock_db()
        app = _maintenance_router_app(db, _user("sys_admin"))
        current = MaintenanceStatus(enabled=False, message="Heads up", severity="info")
        saved = MaintenanceStatus(enabled=True, message="Heads up", severity="info")

        with (
            patch(
                "app.routers.maintenance.get_maintenance_status",
                new=AsyncMock(return_value=current),
            ),
            patch(
                "app.routers.maintenance.save_maintenance_status",
                new=AsyncMock(return_value=saved),
            ) as save_mock,
            patch("app.routers.maintenance.load_settings_overlay", new=AsyncMock()),
            patch("app.routers.maintenance.log_action", new=AsyncMock()),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/api/v1/admin/maintenance/toggle", json={})

        assert response.status_code == 200
        assert response.json()["enabled"] is True
        assert save_mock.await_args.args[1].enabled is True


class TestMaintenanceMiddleware:
    def _app(self) -> FastAPI:
        app = FastAPI()
        app.state.db_pool_ready = True
        app.add_middleware(MaintenanceModeMiddleware)

        @app.post("/api/v1/widgets")
        async def create_widget() -> dict[str, bool]:
            return {"ok": True}

        @app.post("/api/v1/auth/login")
        async def login() -> dict[str, bool]:
            return {"ok": True}

        @app.put("/api/v1/admin/maintenance")
        async def update_maintenance() -> dict[str, bool]:
            return {"ok": True}

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        return app

    @pytest.mark.asyncio
    async def test_blocks_non_admin_writes_with_maintenance_header(self) -> None:
        app = self._app()
        active = MaintenanceStatus(
            enabled=True,
            message="Maintenance",
            severity="warning",
            block_writes=True,
        )

        with (
            patch(
                "app.middleware.maintenance._get_active_maintenance_status",
                new=AsyncMock(return_value=active),
            ),
            patch(
                "app.middleware.maintenance._is_admin_request",
                new=AsyncMock(return_value=False),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/api/v1/widgets", json={"name": "demo"})

        assert response.status_code == 503
        assert response.headers["X-Maintenance-Mode"] == "true"
        assert response.json()["error"]["code"] == "service_unavailable"

    @pytest.mark.asyncio
    async def test_allows_exempt_paths_during_maintenance(self) -> None:
        app = self._app()
        active = MaintenanceStatus(
            enabled=True,
            message="Maintenance",
            severity="warning",
            block_writes=True,
        )

        with (
            patch(
                "app.middleware.maintenance._get_active_maintenance_status",
                new=AsyncMock(return_value=active),
            ),
            patch(
                "app.middleware.maintenance._is_admin_request",
                new=AsyncMock(return_value=False),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                auth_response = await client.post("/api/v1/auth/login", json={})
                admin_response = await client.put("/api/v1/admin/maintenance", json={})
                health_response = await client.get("/health")

        assert auth_response.status_code == 200
        assert admin_response.status_code == 200
        assert health_response.status_code == 200
        assert auth_response.headers["X-Maintenance-Mode"] == "true"

    @pytest.mark.asyncio
    async def test_allows_admin_writes_during_maintenance(self) -> None:
        app = self._app()
        active = MaintenanceStatus(
            enabled=True,
            message="Maintenance",
            severity="warning",
            block_writes=True,
        )

        with (
            patch(
                "app.middleware.maintenance._get_active_maintenance_status",
                new=AsyncMock(return_value=active),
            ),
            patch(
                "app.middleware.maintenance._is_admin_request",
                new=AsyncMock(return_value=True),
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post("/api/v1/widgets", json={"name": "demo"})

        assert response.status_code == 200
        assert response.headers["X-Maintenance-Mode"] == "true"
