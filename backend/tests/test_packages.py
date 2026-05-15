"""Tests for the packages monitoring service and router."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import packages as packages_module
from app.services.package_monitoring_service import (
    PackageAlertList,
    PackageAlertRecord,
    PackageInventory,
    PackageInventoryItem,
    PackageSummary,
    StaleImageList,
    StaleImageRecord,
    _org_filter,
)

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "pkg-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 12345,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(roles: list[str] | None = None) -> str:
    return json.dumps(
        {
            "github_login": "testuser",
            "github_id": 12345,
            "roles": roles or ["analyst"],
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
    mock_result.scalar.return_value = 0

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    return mock_db


def _build_packages_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    """Create a FastAPI app with the packages router for testing."""
    app = FastAPI()
    app.include_router(packages_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db():  # type: ignore[return-value]
        yield mock_db

    async def override_valkey():  # type: ignore[return-value]
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ── org_filter helper tests ─────────────────────────────────────────────────


class TestOrgFilter:
    """Tests for _org_filter helper."""

    def test_empty_orgs_returns_empty(self) -> None:
        sql, params = _org_filter([])
        assert sql == ""
        assert params == {}

    def test_single_org(self) -> None:
        sql, params = _org_filter(["my-org"])
        assert "IN" in sql
        assert params == {"org_0": "my-org"}

    def test_multiple_orgs(self) -> None:
        sql, params = _org_filter(["org1", "org2", "org3"])
        assert ":org_0" in sql
        assert ":org_1" in sql
        assert ":org_2" in sql
        assert params["org_0"] == "org1"
        assert params["org_1"] == "org2"
        assert params["org_2"] == "org3"

    def test_custom_alias(self) -> None:
        sql, _ = _org_filter(["my-org"], table_alias="pkg")
        assert sql.startswith("AND pkg.org IN (")
        assert ":org_0" in sql


# ── Service function tests ───────────────────────────────────────────────────


class TestGetPackagesSummary:
    """Tests for get_packages_summary."""

    @pytest.mark.asyncio
    async def test_returns_summary_with_empty_db(self) -> None:
        from app.services.package_monitoring_service import get_packages_summary

        mock_db = _make_mock_db()
        result = await get_packages_summary(mock_db, ["my-org"])

        assert isinstance(result, PackageSummary)
        assert result.total_packages == 0
        assert result.public_packages == 0
        assert result.private_packages == 0
        assert result.by_type == {}

    @pytest.mark.asyncio
    async def test_returns_summary_with_global_scope(self) -> None:
        from app.services.package_monitoring_service import get_packages_summary

        mock_db = _make_mock_db()
        result = await get_packages_summary(mock_db, [])

        assert isinstance(result, PackageSummary)
        assert result.total_packages == 0


class TestGetPackageAlerts:
    """Tests for get_package_alerts."""

    @pytest.mark.asyncio
    async def test_returns_empty_alert_list(self) -> None:
        from app.services.package_monitoring_service import get_package_alerts

        mock_db = _make_mock_db()
        result = await get_package_alerts(mock_db, ["my-org"])

        assert isinstance(result, PackageAlertList)
        assert result.total == 0
        assert result.alerts == []

    @pytest.mark.asyncio
    async def test_accepts_status_filter(self) -> None:
        from app.services.package_monitoring_service import get_package_alerts

        mock_db = _make_mock_db()
        result = await get_package_alerts(mock_db, ["my-org"], alert_status="open")

        assert isinstance(result, PackageAlertList)

    @pytest.mark.asyncio
    async def test_accepts_severity_filter(self) -> None:
        from app.services.package_monitoring_service import get_package_alerts

        mock_db = _make_mock_db()
        result = await get_package_alerts(mock_db, ["my-org"], severity="high")

        assert isinstance(result, PackageAlertList)


class TestGetPackageInventory:
    """Tests for get_package_inventory."""

    @pytest.mark.asyncio
    async def test_returns_empty_inventory(self) -> None:
        from app.services.package_monitoring_service import get_package_inventory

        mock_db = _make_mock_db()
        result = await get_package_inventory(mock_db, ["my-org"])

        assert isinstance(result, PackageInventory)
        assert result.total == 0
        assert result.items == []
        assert result.page == 1
        assert result.page_size == 50

    @pytest.mark.asyncio
    async def test_accepts_type_filter(self) -> None:
        from app.services.package_monitoring_service import get_package_inventory

        mock_db = _make_mock_db()
        result = await get_package_inventory(mock_db, ["my-org"], package_type="npm")
        assert isinstance(result, PackageInventory)

    @pytest.mark.asyncio
    async def test_accepts_visibility_filter(self) -> None:
        from app.services.package_monitoring_service import get_package_inventory

        mock_db = _make_mock_db()
        result = await get_package_inventory(mock_db, ["my-org"], visibility="public")
        assert isinstance(result, PackageInventory)

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        from app.services.package_monitoring_service import get_package_inventory

        mock_db = _make_mock_db()
        result = await get_package_inventory(mock_db, ["my-org"], page=2, page_size=10)
        assert result.page == 2
        assert result.page_size == 10


class TestGetStaleImages:
    """Tests for get_stale_images."""

    @pytest.mark.asyncio
    async def test_returns_empty_stale_list(self) -> None:
        from app.services.package_monitoring_service import get_stale_images

        mock_db = _make_mock_db()
        result = await get_stale_images(mock_db, ["my-org"])

        assert isinstance(result, StaleImageList)
        assert result.total == 0
        assert result.images == []
        assert result.threshold_days == 90

    @pytest.mark.asyncio
    async def test_custom_threshold(self) -> None:
        from app.services.package_monitoring_service import get_stale_images

        mock_db = _make_mock_db()
        result = await get_stale_images(mock_db, ["my-org"], days_threshold=30)

        assert result.threshold_days == 30


# ── Router endpoint tests ───────────────────────────────────────────────────


class TestPackagesRouter:
    """Tests for the packages router endpoints."""

    def test_summary_requires_auth(self) -> None:
        app, _, _ = _build_packages_app(valkey_session=None)
        client = TestClient(app)
        resp = client.get("/api/v1/packages/summary")
        assert resp.status_code == 401

    def test_summary_returns_200(self) -> None:
        session_data = _make_session()
        app, mock_db, _ = _build_packages_app(valkey_session=session_data)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/packages/summary",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total_packages" in data
        assert "public_packages" in data
        assert "private_packages" in data

    def test_alerts_requires_auth(self) -> None:
        app, _, _ = _build_packages_app(valkey_session=None)
        client = TestClient(app)
        resp = client.get("/api/v1/packages/alerts")
        assert resp.status_code == 401

    def test_alerts_returns_200(self) -> None:
        session_data = _make_session()
        app, mock_db, _ = _build_packages_app(valkey_session=session_data)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/packages/alerts",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "total" in data

    def test_alerts_with_filters(self) -> None:
        session_data = _make_session()
        app, mock_db, _ = _build_packages_app(valkey_session=session_data)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/packages/alerts?status=open&severity=high",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200

    def test_inventory_requires_auth(self) -> None:
        app, _, _ = _build_packages_app(valkey_session=None)
        client = TestClient(app)
        resp = client.get("/api/v1/packages/inventory")
        assert resp.status_code == 401

    def test_inventory_returns_200(self) -> None:
        session_data = _make_session()
        app, mock_db, _ = _build_packages_app(valkey_session=session_data)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/packages/inventory",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data

    def test_inventory_with_filters(self) -> None:
        session_data = _make_session()
        app, mock_db, _ = _build_packages_app(valkey_session=session_data)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/packages/inventory?type=npm&visibility=public&page=2&page_size=10",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200

    def test_stale_images_requires_auth(self) -> None:
        app, _, _ = _build_packages_app(valkey_session=None)
        client = TestClient(app)
        resp = client.get("/api/v1/packages/stale-images")
        assert resp.status_code == 401

    def test_stale_images_returns_200(self) -> None:
        session_data = _make_session()
        app, mock_db, _ = _build_packages_app(valkey_session=session_data)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/packages/stale-images",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "images" in data
        assert "total" in data
        assert "threshold_days" in data

    def test_stale_images_custom_threshold(self) -> None:
        session_data = _make_session()
        app, mock_db, _ = _build_packages_app(valkey_session=session_data)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/packages/stale-images?days=30",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200


# ── Data class tests ─────────────────────────────────────────────────────────


class TestDataClasses:
    """Tests for service data classes."""

    def test_package_summary_defaults(self) -> None:
        summary = PackageSummary(
            total_packages=10,
            public_packages=3,
            private_packages=7,
        )
        assert summary.by_type == {}
        assert summary.newly_public == 0
        assert summary.stale_images == 0
        assert summary.open_alerts == 0

    def test_package_alert_record(self) -> None:
        alert = PackageAlertRecord(
            id=1,
            package_id=10,
            package_name="my-pkg",
            package_org="my-org",
            alert_type="public_exposure",
            severity="high",
            message="Package is public",
            detected_at="2024-01-01T00:00:00Z",
            resolved_at=None,
            status="open",
        )
        assert alert.id == 1
        assert alert.alert_type == "public_exposure"

    def test_package_inventory_item(self) -> None:
        item = PackageInventoryItem(
            id=1,
            org="my-org",
            repo="my-org/repo",
            name="my-pkg",
            package_type="npm",
            visibility="private",
            owner="user1",
            versions_count=5,
            latest_version="1.2.3",
            last_published_at="2024-01-01T00:00:00Z",
            is_stale=False,
            published_outside_actions=False,
            published_by_external=False,
        )
        assert item.name == "my-pkg"
        assert item.versions_count == 5

    def test_stale_image_record(self) -> None:
        image = StaleImageRecord(
            id=1,
            org="my-org",
            repo="my-org/myapp",
            name="myapp",
            last_published_at="2023-06-01T00:00:00Z",
            days_since_rebuild=180,
            owner="user1",
        )
        assert image.days_since_rebuild == 180

    def test_package_alert_list_defaults(self) -> None:
        alert_list = PackageAlertList()
        assert alert_list.alerts == []
        assert alert_list.total == 0

    def test_package_inventory_defaults(self) -> None:
        inv = PackageInventory()
        assert inv.items == []
        assert inv.total == 0
        assert inv.page == 1
        assert inv.page_size == 50

    def test_stale_image_list_defaults(self) -> None:
        stale = StaleImageList()
        assert stale.images == []
        assert stale.total == 0
        assert stale.threshold_days == 90


# ── Worker helper tests ──────────────────────────────────────────────────────


class TestPackageSyncWorker:
    """Tests for package sync worker helper functions."""

    def test_expected_registry_types(self) -> None:
        from app.workers.package_sync_worker import _EXPECTED_REGISTRY_TYPES

        assert "npm" in _EXPECTED_REGISTRY_TYPES
        assert "maven" in _EXPECTED_REGISTRY_TYPES
        assert "docker" in _EXPECTED_REGISTRY_TYPES
        assert "container" in _EXPECTED_REGISTRY_TYPES
        assert "nuget" in _EXPECTED_REGISTRY_TYPES
        assert "rubygems" in _EXPECTED_REGISTRY_TYPES

    def test_stale_threshold_days(self) -> None:
        from app.workers.package_sync_worker import _STALE_THRESHOLD_DAYS

        assert _STALE_THRESHOLD_DAYS == 90

    @pytest.mark.asyncio
    async def test_update_staleness_flags(self) -> None:
        from app.workers.package_sync_worker import _update_staleness_flags

        mock_result = MagicMock()
        mock_result.rowcount = 3

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        count = await _update_staleness_flags(mock_db)
        assert count == 6  # 3 stale + 3 unstale (both return rowcount=3)

    @pytest.mark.asyncio
    async def test_generate_alerts_with_empty_db(self) -> None:
        from app.workers.package_sync_worker import _generate_alerts

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        count = await _generate_alerts(mock_db)
        assert count == 0
