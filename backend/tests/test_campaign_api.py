"""Tests for campaign API endpoints (GET, PATCH, POST /threat-intel/campaigns/...)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import contextmanager
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


_CAMPAIGN_1: dict[str, Any] = {
    "id": 1,
    "name": "Miasma",
    "slug": "miasma",
    "description": "Supply chain attack campaign",
    "first_seen_at": "2024-06-01T00:00:00+00:00",
    "last_updated": "2024-06-10T00:00:00+00:00",
    "severity": "critical",
    "status": "active",
    "source_feed_id": None,
    "metadata_json": {"mitre_tactics": ["TA0001"]},
    "indicator_count": 42,
}

_CAMPAIGN_DETAIL: dict[str, Any] = {
    **_CAMPAIGN_1,
    "indicators_by_type": [{"type": "domain", "count": 30}, {"type": "ip", "count": 12}],
    "rule_count": 5,
    "detection_count": 17,
    "mitre_tactics": ["TA0001"],
}


class TestListCampaigns:
    def test_empty_list(self) -> None:
        app, _mock_db = _build_app()
        with patch(
            "app.services.threat_intel_service.get_campaigns",
            AsyncMock(return_value=([], 0)),
        ):
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/campaigns")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_with_results(self) -> None:
        app, _mock_db = _build_app()
        with patch(
            "app.services.threat_intel_service.get_campaigns",
            AsyncMock(return_value=([_CAMPAIGN_1], 1)),
        ):
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/campaigns")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Miasma"
        assert data["total"] == 1

    def test_with_status_filter(self) -> None:
        app, _mock_db = _build_app()
        with patch(
            "app.services.threat_intel_service.get_campaigns",
            AsyncMock(return_value=([_CAMPAIGN_1], 1)),
        ) as mock_get:
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/campaigns?status=active")
        assert resp.status_code == 200
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs["status"] == "active"


class TestGetCampaignDetail:
    def test_found(self) -> None:
        app, _mock_db = _build_app()
        with patch(
            "app.services.threat_intel_service.get_campaign_detail",
            AsyncMock(return_value=_CAMPAIGN_DETAIL),
        ):
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/campaigns/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Miasma"
        assert data["rule_count"] == 5
        assert data["detection_count"] == 17
        assert data["mitre_tactics"] == ["TA0001"]

    def test_not_found(self) -> None:
        app, _mock_db = _build_app()
        with patch(
            "app.services.threat_intel_service.get_campaign_detail",
            AsyncMock(return_value=None),
        ):
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/campaigns/999")
        assert resp.status_code == 404


class TestUpdateCampaign:
    def test_update_status(self) -> None:
        app, _mock_db = _build_app()
        updated = {**_CAMPAIGN_1, "status": "archived"}
        with patch(
            "app.services.threat_intel_service.update_campaign",
            AsyncMock(return_value=updated),
        ) as mock_update:
            with _authorized_client(app) as client:
                resp = client.patch(
                    "/api/v1/threat-intel/campaigns/1",
                    json={"status": "archived"},
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"
        mock_update.assert_called_once()

    def test_not_found(self) -> None:
        app, _mock_db = _build_app()
        with patch(
            "app.services.threat_intel_service.update_campaign",
            AsyncMock(return_value=None),
        ):
            with _authorized_client(app) as client:
                resp = client.patch(
                    "/api/v1/threat-intel/campaigns/999",
                    json={"status": "archived"},
                )
        assert resp.status_code == 404


class TestGetCampaignDetections:
    def test_returns_detections(self) -> None:
        app, _mock_db = _build_app()
        detection_item = {
            "id": 10,
            "rule_id": 3,
            "title": "Suspicious domain",
            "severity": "high",
            "status": "open",
            "actor": "badactor",
            "org": "myorg",
            "repo": "myorg/myrepo",
            "triggered_at": "2024-06-05T12:00:00+00:00",
            "confidence_score": 0.92,
        }
        with patch(
            "app.services.threat_intel_service.get_campaign_detections",
            AsyncMock(return_value=([detection_item], 1)),
        ):
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/campaigns/1/detections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == 10

    def test_empty(self) -> None:
        app, _mock_db = _build_app()
        with patch(
            "app.services.threat_intel_service.get_campaign_detections",
            AsyncMock(return_value=([], 0)),
        ):
            with _authorized_client(app) as client:
                resp = client.get("/api/v1/threat-intel/campaigns/1/detections")
        assert resp.status_code == 200
        assert resp.json()["items"] == []


class TestPromoteCampaignRules:
    def test_promote_success(self) -> None:
        app, _mock_db = _build_app()
        result = {"campaign_id": 1, "promoted_count": 3, "rule_ids": [10, 11, 12]}
        with patch(
            "app.services.threat_intel_service.promote_campaign_rules",
            AsyncMock(return_value=result),
        ):
            with _authorized_client(app) as client:
                resp = client.post("/api/v1/threat-intel/campaigns/1/promote-rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["promoted_count"] == 3
        assert data["rule_ids"] == [10, 11, 12]

    def test_promote_none(self) -> None:
        app, _mock_db = _build_app()
        result = {"campaign_id": 1, "promoted_count": 0, "rule_ids": []}
        with patch(
            "app.services.threat_intel_service.promote_campaign_rules",
            AsyncMock(return_value=result),
        ):
            with _authorized_client(app) as client:
                resp = client.post("/api/v1/threat-intel/campaigns/1/promote-rules")
        assert resp.status_code == 200
        assert resp.json()["promoted_count"] == 0
