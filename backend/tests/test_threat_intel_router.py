from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, verify_csrf
from app.routers import threat_intel


def _build_app() -> tuple[FastAPI, AsyncSession]:
    app = FastAPI()
    app.include_router(threat_intel.router, prefix="/api/v1")
    mock_db = cast(AsyncSession, AsyncMock(spec=AsyncSession))

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_db

    async def override_user() -> AuthenticatedUser:
        return AuthenticatedUser(
            github_login="testuser",
            github_id=12345,
            roles=["sys_admin"],
            scoped_orgs=[],
            scoped_repos=[],
            scope_type="global",
            jti="test-jti",
            session_expires_at="2099-01-01T00:00:00+00:00",
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[verify_csrf] = lambda: None
    return app, mock_db


@contextmanager
def _authorized_client(app: FastAPI) -> Iterator[TestClient]:
    with patch(
        "app.services.rbac_service.check_permission",
        AsyncMock(return_value=True),
    ):
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client


class TestThreatIntelFeedRoutes:
    def test_update_feed_success(self) -> None:
        app, mock_db = _build_app()
        feed: dict[str, Any] = {
            "id": 7,
            "name": "Updated Feed",
            "url": "https://example.com/feed.txt",
            "feed_type": "domain",
            "enabled": True,
            "refresh_interval_minutes": 60,
            "last_fetched_at": None,
            "last_fetch_status": None,
            "last_indicator_count": 12,
            "created_by": "testuser",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
        }

        with patch(
            "app.services.threat_intel_service.update_feed",
            AsyncMock(return_value=feed),
        ) as mock_update:
            with _authorized_client(app) as client:
                resp = client.patch(
                    "/api/v1/threat-intel/feeds/7",
                    json={"name": "Updated Feed", "enabled": True},
                )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Feed"
        mock_update.assert_awaited_once_with(
            mock_db,
            7,
            updates={"name": "Updated Feed", "enabled": True},
        )

    def test_update_feed_not_found(self) -> None:
        app, _ = _build_app()

        with patch(
            "app.services.threat_intel_service.update_feed",
            AsyncMock(return_value=None),
        ):
            with _authorized_client(app) as client:
                resp = client.patch(
                    "/api/v1/threat-intel/feeds/404",
                    json={"name": "Missing Feed"},
                )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Feed not found"

    def test_delete_feed_success(self) -> None:
        app, mock_db = _build_app()

        with patch(
            "app.services.threat_intel_service.delete_feed",
            AsyncMock(return_value=True),
        ) as mock_delete:
            with _authorized_client(app) as client:
                resp = client.delete("/api/v1/threat-intel/feeds/9")

        assert resp.status_code == 204
        assert resp.content == b""
        mock_delete.assert_awaited_once_with(mock_db, 9)

    def test_delete_feed_not_found(self) -> None:
        app, _ = _build_app()

        with patch(
            "app.services.threat_intel_service.delete_feed",
            AsyncMock(return_value=False),
        ):
            with _authorized_client(app) as client:
                resp = client.delete("/api/v1/threat-intel/feeds/404")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Feed not found"

    def test_refresh_feed_success(self) -> None:
        app, mock_db = _build_app()

        with patch(
            "app.services.threat_intel_service.refresh_feed",
            AsyncMock(return_value={"id": 3, "name": "OSINT", "last_indicator_count": 42}),
        ) as mock_refresh:
            with _authorized_client(app) as client:
                resp = client.post("/api/v1/threat-intel/feeds/3/refresh")

        assert resp.status_code == 200
        assert resp.json() == {
            "feed_id": 3,
            "status": "refreshing",
            "indicator_count": 42,
            "message": "Feed 'OSINT' refresh initiated",
        }
        mock_refresh.assert_awaited_once_with(mock_db, 3)

    def test_refresh_feed_not_found(self) -> None:
        app, _ = _build_app()

        with patch(
            "app.services.threat_intel_service.refresh_feed",
            AsyncMock(return_value=None),
        ):
            with _authorized_client(app) as client:
                resp = client.post("/api/v1/threat-intel/feeds/404/refresh")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Feed not found"


class TestThreatIntelIndicatorRoutes:
    def test_bulk_create_indicators_success(self) -> None:
        app, mock_db = _build_app()

        with patch(
            "app.services.threat_intel_service.bulk_create_indicators",
            AsyncMock(return_value={"created": 2, "duplicates": 1, "errors": 0}),
        ) as mock_bulk:
            with _authorized_client(app) as client:
                resp = client.post(
                    "/api/v1/threat-intel/indicators/bulk",
                    json={
                        "indicators": [
                            {"indicator_type": "domain", "value": "evil.example"},
                            {"indicator_type": "ip", "value": "10.0.0.2", "confidence": 0.5},
                        ]
                    },
                )

        assert resp.status_code == 200
        assert resp.json() == {"created": 2, "duplicates": 1, "errors": 0}
        mock_bulk.assert_awaited_once_with(
            mock_db,
            indicators=[
                {
                    "indicator_type": "domain",
                    "value": "evil.example",
                    "source": "manual-bulk",
                    "confidence": 0.8,
                },
                {
                    "indicator_type": "ip",
                    "value": "10.0.0.2",
                    "source": "manual-bulk",
                    "confidence": 0.5,
                },
            ],
            added_by="testuser",
        )


class TestThreatIntelReadRoutes:
    def test_list_matches_success(self) -> None:
        app, mock_db = _build_app()
        matches = [
            {
                "detection_id": 11,
                "title": "Matched IOC",
                "severity": "high",
                "status": "open",
                "actor": "octocat",
                "org": "acme",
                "repo": "acme/repo",
                "triggered_at": datetime(2024, 1, 2, tzinfo=UTC),
                "matched_indicator_value": "evil.example",
                "matched_indicator_type": "domain",
                "matched_feed_name": "OSINT",
            }
        ]

        with patch(
            "app.services.threat_intel_service.get_matches",
            AsyncMock(return_value=(matches, 1, 1, 1, "OSINT")),
        ) as mock_matches:
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/matches?page=0&page_size=500")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["total_24h"] == 1
        assert data["unique_indicators"] == 1
        assert data["top_feed"] == "OSINT"
        assert data["items"][0]["matched_indicator_value"] == "evil.example"
        mock_matches.assert_awaited_once_with(mock_db, page=1, page_size=50)

    def test_get_analytics_success(self) -> None:
        app, mock_db = _build_app()
        analytics: dict[str, Any] = {
            "total_feeds": 4,
            "active_feeds": 3,
            "total_indicators": 100,
            "active_indicators": 80,
            "matches_30d": 12,
            "coverage_score": 0.8,
            "matches_over_time": [{"date": "2024-01-01", "count": 5}],
            "matches_by_feed": [{"name": "OSINT", "count": 10}],
            "indicator_type_distribution": [{"type": "domain", "count": 80}],
        }

        with patch(
            "app.services.threat_intel_service.get_analytics",
            AsyncMock(return_value=analytics),
        ) as mock_analytics:
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/analytics")

        assert resp.status_code == 200
        assert resp.json() == analytics
        mock_analytics.assert_awaited_once_with(mock_db)
