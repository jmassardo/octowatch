"""Tests for new sync entity types: outside collaborators, alert summaries,
license consumption, and delta sync support.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.github_sync import SyncScheduleUpdateRequest, SyncTriggerRequest

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Model Tests ──────────────────────────────────────────────────────────────


class TestOrgOutsideCollaboratorModel:
    """Tests for the OrgOutsideCollaborator ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import OrgOutsideCollaborator

        assert OrgOutsideCollaborator.__tablename__ == "org_outside_collaborators"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import OrgOutsideCollaborator

        constraints = {
            c.name for c in OrgOutsideCollaborator.__table__.constraints if hasattr(c, "name")
        }
        assert "uq_outside_collab_slug_org_login" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import OrgOutsideCollaborator

        cols = {c.name for c in OrgOutsideCollaborator.__table__.columns}
        expected = {
            "id",
            "enterprise_slug",
            "org",
            "login",
            "github_id",
            "avatar_url",
            "site_admin",
            "synced_at",
        }
        assert expected.issubset(cols)


class TestOrgSecretScanningAlertSummaryModel:
    """Tests for the OrgSecretScanningAlertSummary ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import OrgSecretScanningAlertSummary

        assert OrgSecretScanningAlertSummary.__tablename__ == "org_secret_scanning_alert_summaries"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import OrgSecretScanningAlertSummary

        constraints = {
            c.name
            for c in OrgSecretScanningAlertSummary.__table__.constraints
            if hasattr(c, "name")
        }
        assert "uq_secret_scanning_summary_slug_org" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import OrgSecretScanningAlertSummary

        cols = {c.name for c in OrgSecretScanningAlertSummary.__table__.columns}
        assert {
            "id",
            "enterprise_slug",
            "org",
            "open_count",
            "resolved_count",
            "total_count",
            "synced_at",
        }.issubset(cols)


class TestOrgDependabotAlertSummaryModel:
    """Tests for the OrgDependabotAlertSummary ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import OrgDependabotAlertSummary

        assert OrgDependabotAlertSummary.__tablename__ == "org_dependabot_alert_summaries"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import OrgDependabotAlertSummary

        constraints = {
            c.name for c in OrgDependabotAlertSummary.__table__.constraints if hasattr(c, "name")
        }
        assert "uq_dependabot_summary_slug_org" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import OrgDependabotAlertSummary

        cols = {c.name for c in OrgDependabotAlertSummary.__table__.columns}
        assert {
            "id",
            "enterprise_slug",
            "org",
            "open_count",
            "fixed_count",
            "dismissed_count",
            "total_count",
            "critical_count",
            "high_count",
            "medium_count",
            "low_count",
            "synced_at",
        }.issubset(cols)


class TestEnterpriseLicenseConsumptionModel:
    """Tests for the EnterpriseLicenseConsumption ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import EnterpriseLicenseConsumption

        assert EnterpriseLicenseConsumption.__tablename__ == "enterprise_license_consumption"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import EnterpriseLicenseConsumption

        constraints = {
            c.name for c in EnterpriseLicenseConsumption.__table__.constraints if hasattr(c, "name")
        }
        assert "uq_license_consumption_slug" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import EnterpriseLicenseConsumption

        cols = {c.name for c in EnterpriseLicenseConsumption.__table__.columns}
        assert {
            "id",
            "enterprise_slug",
            "total_seats_purchased",
            "total_seats_consumed",
            "seats",
            "synced_at",
        }.issubset(cols)


# ─── Schema Tests ─────────────────────────────────────────────────────────────


class TestNewScopeValues:
    """Tests that new entity types are accepted by schemas."""

    def test_trigger_request_outside_collaborators(self) -> None:
        req = SyncTriggerRequest(scope="outside_collaborators")
        assert req.scope == "outside_collaborators"

    def test_trigger_request_secret_scanning_alerts(self) -> None:
        req = SyncTriggerRequest(scope="secret_scanning_alerts")
        assert req.scope == "secret_scanning_alerts"

    def test_trigger_request_dependabot_alerts(self) -> None:
        req = SyncTriggerRequest(scope="dependabot_alerts")
        assert req.scope == "dependabot_alerts"

    def test_trigger_request_license_consumption(self) -> None:
        req = SyncTriggerRequest(scope="license_consumption")
        assert req.scope == "license_consumption"

    def test_schedule_request_new_scopes(self) -> None:
        for scope in [
            "outside_collaborators",
            "secret_scanning_alerts",
            "dependabot_alerts",
            "license_consumption",
        ]:
            req = SyncScheduleUpdateRequest(scope=scope)
            assert req.scope == scope


# ─── Sync Worker Tests ────────────────────────────────────────────────────────


class TestFetchPageNewEntities:
    """Tests for _fetch_page handling of new entity types."""

    @pytest.mark.asyncio
    async def test_fetch_secret_scanning_alerts_aggregates(self) -> None:
        """Verify secret scanning alerts are aggregated into a summary."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        open_alerts = [
            {"state": "open", "created_at": "2024-01-01T00:00:00Z"},
            {"state": "open", "created_at": "2024-02-01T00:00:00Z"},
        ]

        # First call returns open alerts, no more pages
        mock_resp_open = MagicMock()
        mock_resp_open.status_code = 200
        mock_resp_open.json.return_value = open_alerts
        mock_resp_open.headers = {}

        # Second call for resolved alerts returns empty
        mock_resp_resolved = MagicMock()
        mock_resp_resolved.status_code = 200
        mock_resp_resolved.json.return_value = []
        mock_resp_resolved.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(side_effect=[mock_resp_open, mock_resp_resolved]),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="secret_scanning_alerts",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        summary = items[0]
        assert summary["_org"] == "test-org"
        assert summary["open_count"] == 2
        assert summary["resolved_count"] == 0
        assert summary["total_count"] == 2
        assert next_cursor == "_done"

    @pytest.mark.asyncio
    async def test_fetch_secret_scanning_alerts_done_cursor(self) -> None:
        """After aggregation, passing '_done' cursor returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        items, next_cursor = await _fetch_page(
            entity_type="secret_scanning_alerts",
            org="test-org",
            token="test-token",
            cursor="_done",
            rate_limiter=mock_rate_limiter,
        )
        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_secret_scanning_403_returns_empty(self) -> None:
        """403 response means secret scanning isn't enabled — return empty."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="secret_scanning_alerts",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_dependabot_alerts_aggregates(self) -> None:
        """Verify dependabot alerts are aggregated into a summary."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        alerts = [
            {
                "state": "open",
                "security_vulnerability": {"severity": "critical"},
            },
            {
                "state": "open",
                "security_vulnerability": {"severity": "high"},
            },
            {
                "state": "fixed",
                "security_vulnerability": {"severity": "critical"},
            },
            {
                "state": "dismissed",
                "security_vulnerability": {"severity": "low"},
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = alerts
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="dependabot_alerts",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        summary = items[0]
        assert summary["_org"] == "test-org"
        assert summary["open_count"] == 2
        assert summary["fixed_count"] == 1
        assert summary["dismissed_count"] == 1
        assert summary["critical_count"] == 2
        assert summary["high_count"] == 1
        assert next_cursor == "_done"

    @pytest.mark.asyncio
    async def test_fetch_dependabot_done_cursor(self) -> None:
        """After aggregation, passing '_done' cursor returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        items, next_cursor = await _fetch_page(
            entity_type="dependabot_alerts",
            org="test-org",
            token="test-token",
            cursor="_done",
            rate_limiter=mock_rate_limiter,
        )
        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_license_consumption(self) -> None:
        """Verify license consumption data is fetched and structured."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        resp_data = {
            "total_seats_purchased": 500,
            "total_seats_consumed": 450,
            "users": [
                {"github_com_login": "user1"},
                {"github_com_login": "user2"},
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = resp_data
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="license_consumption",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        summary = items[0]
        assert summary["_enterprise_slug"] == "my-enterprise"
        assert summary["total_seats_purchased"] == 500
        assert summary["total_seats_consumed"] == 450
        assert next_cursor == "_done"

    @pytest.mark.asyncio
    async def test_fetch_license_consumption_no_slug(self) -> None:
        """License consumption without enterprise slug returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        items, next_cursor = await _fetch_page(
            entity_type="license_consumption",
            org=None,
            token="test-token",
            cursor=None,
            rate_limiter=mock_rate_limiter,
        )
        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_outside_collaborators(self) -> None:
        """Outside collaborators use the simple page-based pattern."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        collabs = [
            {"login": "external-user", "id": 99999},
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = collabs
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="outside_collaborators",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        assert items[0]["login"] == "external-user"
        assert next_cursor is None  # No Link header

    @pytest.mark.asyncio
    async def test_fetch_repos_delta_since_stops_early(self) -> None:
        """When delta_since is set, repos older than the cutoff stop pagination."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        now = datetime.now(UTC)
        since = now - timedelta(hours=12)

        repos = [
            {
                "name": "fresh-repo",
                "id": 1,
                "pushed_at": now.isoformat(),
                "visibility": "private",
            },
            {
                "name": "old-repo",
                "id": 2,
                "pushed_at": (now - timedelta(days=30)).isoformat(),
                "visibility": "private",
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = repos
        # Simulate there being more pages available
        mock_resp.headers = {"link": '<next>; rel="next"'}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="repositories",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
                delta_since=since,
            )

        # Only the fresh repo should be returned, pagination stops
        assert len(items) == 1
        assert items[0]["name"] == "fresh-repo"
        assert next_cursor is None


class TestEntityTypeDispatch:
    """Tests that new entity types are included in the orchestrator dispatch."""

    def test_scope_type_includes_new_entities(self) -> None:
        """All new entity types are in the ScopeType literal."""
        # The type annotation itself is compile-time, but we verify via the schema
        for scope in [
            "outside_collaborators",
            "secret_scanning_alerts",
            "dependabot_alerts",
            "license_consumption",
        ]:
            req = SyncTriggerRequest(scope=scope)
            assert req.scope == scope


# ─── Health Endpoint Tests ────────────────────────────────────────────────────


class TestLicenseConsumptionEndpoint:
    """Tests for the /health-signals/license-consumption endpoint."""

    def test_license_consumption_no_data(self, authenticated_valkey: AsyncMock) -> None:
        """When no license data exists, return zeros."""
        mock_db = AsyncMock()

        # Mock the license consumption query
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.deps import AuthenticatedUser, get_current_user, get_db
        from app.routers import health_signals

        app = FastAPI()
        app.include_router(health_signals.router)
        app.dependency_overrides[get_db] = lambda: mock_db

        test_user = AuthenticatedUser(
            github_login="test-user",
            github_id=1,
            roles=["admin"],
            scoped_orgs=["test-org"],
            scoped_repos=[],
            scope_type="enterprise",
            jti="test-jti",
            session_expires_at="2099-01-01T00:00:00Z",
        )
        app.dependency_overrides[get_current_user] = lambda: test_user

        rbac_patch = "app.services.rbac_service.get_scoped_orgs"
        with patch(rbac_patch, new=AsyncMock(return_value=["test-org"])):
            test_client = TestClient(app)
            resp = test_client.get("/health-signals/license-consumption")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_seats_purchased"] == 0
        assert data["total_seats_consumed"] == 0
        assert data["seats_available"] == 0
        assert data["utilization_pct"] == 0


class TestSecurityAlertsSummaryEndpoint:
    """Tests for the /health-signals/security-alerts-summary endpoint."""

    def test_security_alerts_summary_empty(self, authenticated_valkey: AsyncMock) -> None:
        """When no alert summaries exist, return empty lists."""
        mock_db = AsyncMock()

        # Mock both queries to return empty result sets
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.deps import AuthenticatedUser, get_current_user, get_db
        from app.routers import health_signals

        app = FastAPI()
        app.include_router(health_signals.router)
        app.dependency_overrides[get_db] = lambda: mock_db

        test_user = AuthenticatedUser(
            github_login="test-user",
            github_id=1,
            roles=["admin"],
            scoped_orgs=["test-org"],
            scoped_repos=[],
            scope_type="enterprise",
            jti="test-jti",
            session_expires_at="2099-01-01T00:00:00Z",
        )
        app.dependency_overrides[get_current_user] = lambda: test_user

        rbac_patch = "app.services.rbac_service.get_scoped_orgs"
        with patch(rbac_patch, new=AsyncMock(return_value=["test-org"])):
            test_client = TestClient(app)
            resp = test_client.get("/health-signals/security-alerts-summary")

        assert resp.status_code == 200
        data = resp.json()
        assert "secret_scanning" in data
        assert "dependabot" in data
        assert data["secret_scanning"] == []
        assert data["dependabot"] == []


# ─── Model Export Tests ───────────────────────────────────────────────────────


class TestModelExports:
    """Verify new models are exported from __init__.py."""

    def test_outside_collaborator_exported(self) -> None:
        from app.models import OrgOutsideCollaborator

        assert OrgOutsideCollaborator is not None

    def test_secret_scanning_summary_exported(self) -> None:
        from app.models import OrgSecretScanningAlertSummary

        assert OrgSecretScanningAlertSummary is not None

    def test_dependabot_summary_exported(self) -> None:
        from app.models import OrgDependabotAlertSummary

        assert OrgDependabotAlertSummary is not None

    def test_license_consumption_exported(self) -> None:
        from app.models import EnterpriseLicenseConsumption

        assert EnterpriseLicenseConsumption is not None
