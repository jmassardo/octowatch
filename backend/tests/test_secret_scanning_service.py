"""Tests for the secret scanning service and router.

Covers:
  - Model column additions (validity, locations_count, resolved_by, updated_at)
  - Service functions (summary, trends, sync, audit correlation, push protection)
  - Router endpoint responses
  - Migration file structure
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Model Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecretScanningAlertModelExtended:
    """Tests for the new columns on SecretScanningAlert."""

    def test_new_columns_exist(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        cols = {c.name for c in SecretScanningAlert.__table__.columns}
        new_cols = {"validity", "locations_count", "resolved_by", "updated_at"}
        assert new_cols.issubset(cols), f"Missing columns: {new_cols - cols}"

    def test_validity_column_nullable(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        col = SecretScanningAlert.__table__.c.validity
        assert col.nullable is True

    def test_locations_count_has_server_default(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        col = SecretScanningAlert.__table__.c.locations_count
        assert col.server_default is not None

    def test_resolved_by_column_nullable(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        col = SecretScanningAlert.__table__.c.resolved_by
        assert col.nullable is True

    def test_updated_at_column_nullable(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        col = SecretScanningAlert.__table__.c.updated_at
        assert col.nullable is True

    def test_validity_index_exists(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        idx_names = {idx.name for idx in SecretScanningAlert.__table__.indexes}
        assert "idx_secret_scanning_alert_validity" in idx_names

    def test_all_original_columns_preserved(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        cols = {c.name for c in SecretScanningAlert.__table__.columns}
        original = {
            "id",
            "org_slug",
            "alert_number",
            "repo_full_name",
            "secret_type",
            "secret_type_display",
            "file_path",
            "commit_sha",
            "state",
            "resolution",
            "push_protection_bypassed",
            "push_protection_bypassed_by",
            "created_at",
            "resolved_at",
            "synced_at",
        }
        assert original.issubset(cols)


# ═══════════════════════════════════════════════════════════════════════════════
# Migration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigration0052:
    """Tests for the migration file structure."""

    def test_migration_file_exists(self) -> None:
        import importlib.util
        from pathlib import Path

        migration_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "0052_secret_scanning_extra_columns.py"
        )
        assert migration_path.exists(), f"Not found: {migration_path}"

        spec = importlib.util.spec_from_file_location("migration_0052", migration_path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.revision == "0052"
        assert mod.down_revision == "0051"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        import importlib.util
        from pathlib import Path

        migration_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "0052_secret_scanning_extra_columns.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0052", migration_path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert callable(getattr(mod, "upgrade", None))
        assert callable(getattr(mod, "downgrade", None))


# ═══════════════════════════════════════════════════════════════════════════════
# Service Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecretScanningServiceModule:
    """Test that the service module loads and has expected functions."""

    def test_module_exports(self) -> None:
        from app.services import secret_scanning_service

        assert callable(secret_scanning_service.sync_secret_alerts)
        assert callable(secret_scanning_service.get_secret_alert_summary)
        assert callable(secret_scanning_service.get_secret_alert_trends)
        assert callable(secret_scanning_service.correlate_with_audit_log)
        assert callable(secret_scanning_service.get_push_protection_stats)

    def test_sync_result_dataclass(self) -> None:
        from app.services.secret_scanning_service import SyncResult

        r = SyncResult(org="my-org", created=5, updated=3, total_fetched=8)
        assert r.org == "my-org"
        assert r.created == 5
        assert r.errors == []

    def test_secret_alert_summary_dataclass(self) -> None:
        from app.services.secret_scanning_service import SecretAlertSummary

        s = SecretAlertSummary(open_alerts=10, resolved_30d=5, mttr_hours=24.5)
        assert s.open_alerts == 10
        assert s.active_secrets == 0
        assert s.open_by_type == []

    def test_trend_point_dataclass(self) -> None:
        from app.services.secret_scanning_service import TrendPoint

        t = TrendPoint(date="2024-01-15", new_alerts=3, resolved_alerts=1)
        assert t.date == "2024-01-15"


class TestSyncSecretAlerts:
    """Test the sync_secret_alerts function."""

    @pytest.mark.asyncio
    async def test_sync_with_empty_response(self) -> None:
        from app.services.secret_scanning_service import sync_secret_alerts

        mock_session = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get_paginated.return_value = []

        result = await sync_secret_alerts(mock_session, "my-org", mock_client)
        assert result.org == "my-org"
        assert result.total_fetched == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_sync_with_alerts(self) -> None:
        from app.services.secret_scanning_service import sync_secret_alerts

        mock_session = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get_paginated.return_value = [
            {
                "number": 1,
                "secret_type": "github_personal_access_token",
                "secret_type_display_name": "GitHub PAT",
                "state": "open",
                "resolution": None,
                "push_protection_bypassed": False,
                "push_protection_bypassed_by": None,
                "validity": "active",
                "locations": [{"type": "commit"}],
                "resolved_by": None,
                "repository": {"full_name": "my-org/repo1"},
                "created_at": "2024-01-15T12:00:00Z",
                "updated_at": "2024-01-15T12:00:00Z",
                "resolved_at": None,
            },
            {
                "number": 2,
                "secret_type": "aws_access_key_id",
                "secret_type_display_name": "AWS Access Key",
                "state": "resolved",
                "resolution": "revoked",
                "push_protection_bypassed": True,
                "push_protection_bypassed_by": {"login": "octocat"},
                "validity": "inactive",
                "locations": [],
                "resolved_by": {"login": "admin-user"},
                "repository": {"full_name": "my-org/repo2"},
                "created_at": "2024-01-10T12:00:00Z",
                "updated_at": "2024-01-12T15:00:00Z",
                "resolved_at": "2024-01-12T15:00:00Z",
            },
        ]

        result = await sync_secret_alerts(mock_session, "my-org", mock_client)
        assert result.total_fetched == 2
        assert result.created == 2
        assert mock_session.execute.call_count == 2
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_handles_api_error(self) -> None:
        from app.services.secret_scanning_service import sync_secret_alerts

        mock_session = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get_paginated.side_effect = RuntimeError("API timeout")

        result = await sync_secret_alerts(mock_session, "my-org", mock_client)
        assert result.total_fetched == 0
        assert len(result.errors) == 1
        assert "API timeout" in result.errors[0]

    @pytest.mark.asyncio
    async def test_sync_handles_per_alert_error(self) -> None:
        from app.services.secret_scanning_service import sync_secret_alerts

        mock_session = AsyncMock()
        # First call succeeds, second raises
        mock_session.execute = AsyncMock(side_effect=[None, RuntimeError("DB error")])
        mock_client = AsyncMock()
        mock_client.get_paginated.return_value = [
            {
                "number": 1,
                "secret_type": "token",
                "state": "open",
                "repository": {"full_name": "o/r"},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": None,
                "resolved_at": None,
            },
            {
                "number": 2,
                "secret_type": "token",
                "state": "open",
                "repository": {"full_name": "o/r2"},
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": None,
                "resolved_at": None,
            },
        ]

        result = await sync_secret_alerts(mock_session, "my-org", mock_client)
        assert result.total_fetched == 2
        assert len(result.errors) == 1
        assert "Alert #2" in result.errors[0]


class TestGetSecretAlertSummary:
    """Test the get_secret_alert_summary function."""

    @pytest.mark.asyncio
    async def test_returns_summary_dataclass(self) -> None:
        from app.services.secret_scanning_service import get_secret_alert_summary

        mock_session = AsyncMock()
        # Mock the main summary query result
        mock_main_result = MagicMock()
        mock_main_row = {
            "open_alerts": 10,
            "resolved_30d": 5,
            "push_protection_bypasses": 2,
            "active_secrets": 3,
            "mttr_hours": 48.0,
        }
        mock_main_result.mappings.return_value.first.return_value = mock_main_row

        # Mock the open_by_type query
        mock_type_result = MagicMock()
        mock_type_result.mappings.return_value.all.return_value = [
            {"secret_type_label": "GitHub PAT", "count": 5},
            {"secret_type_label": "AWS Key", "count": 3},
        ]

        # Mock the resolution breakdown query
        mock_res_result = MagicMock()
        mock_res_result.mappings.return_value.all.return_value = [
            {"resolution": "revoked", "count": 3},
            {"resolution": "unresolved", "count": 10},
        ]

        mock_session.execute = AsyncMock(
            side_effect=[mock_main_result, mock_type_result, mock_res_result]
        )

        summary = await get_secret_alert_summary(mock_session, ["my-org"])
        assert summary.open_alerts == 10
        assert summary.resolved_30d == 5
        assert summary.push_protection_bypasses == 2
        assert summary.active_secrets == 3
        assert summary.mttr_hours == 48.0
        assert len(summary.open_by_type) == 2
        assert len(summary.resolution_breakdown) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_summary_when_no_data(self) -> None:
        from app.services.secret_scanning_service import get_secret_alert_summary

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        summary = await get_secret_alert_summary(mock_session, ["empty-org"])
        assert summary.open_alerts == 0
        assert summary.mttr_hours == 0.0


class TestGetSecretAlertTrends:
    """Test the get_secret_alert_trends function."""

    @pytest.mark.asyncio
    async def test_returns_trend_points(self) -> None:
        from app.services.secret_scanning_service import get_secret_alert_trends

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"date": "2024-01-01", "new_alerts": 2, "resolved_alerts": 1},
            {"date": "2024-01-02", "new_alerts": 0, "resolved_alerts": 3},
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        trends = await get_secret_alert_trends(mock_session, ["my-org"], period=7)
        assert len(trends) == 2
        assert trends[0].date == "2024-01-01"
        assert trends[0].new_alerts == 2
        assert trends[1].resolved_alerts == 3


class TestCorrelateWithAuditLog:
    """Test the correlate_with_audit_log function."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_missing_alert(self) -> None:
        from app.services.secret_scanning_service import correlate_with_audit_log

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        events = await correlate_with_audit_log(mock_session, 999)
        assert events == []

    @pytest.mark.asyncio
    async def test_returns_events_for_existing_alert(self) -> None:
        from app.services.secret_scanning_service import correlate_with_audit_log

        mock_session = AsyncMock()

        # First call: alert lookup
        mock_alert_result = MagicMock()
        mock_alert_result.mappings.return_value.first.return_value = {
            "org_slug": "my-org",
            "alert_number": 42,
            "secret_type": "github_personal_access_token",
            "created_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
            "repo_full_name": "my-org/repo1",
        }

        # Second call: event search
        mock_events_result = MagicMock()
        mock_events_result.mappings.return_value.all.return_value = [
            {
                "id": 1,
                "action": "secret_scanning_alert.create",
                "actor": "github-bot",
                "org": "my-org",
                "repo": "my-org/repo1",
                "created_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC),
                "data": {},
            }
        ]

        mock_session.execute = AsyncMock(side_effect=[mock_alert_result, mock_events_result])

        events = await correlate_with_audit_log(mock_session, 1)
        assert len(events) == 1
        assert events[0]["action"] == "secret_scanning_alert.create"


class TestPushProtectionStats:
    """Test the get_push_protection_stats function."""

    @pytest.mark.asyncio
    async def test_returns_stats(self) -> None:
        from app.services.secret_scanning_service import get_push_protection_stats

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = {
            "total_alerts": 100,
            "bypassed": 15,
            "blocked": 85,
        }
        mock_session.execute = AsyncMock(return_value=mock_result)

        stats = await get_push_protection_stats(mock_session, ["my-org"])
        assert stats["total"] == 100
        assert stats["bypassed"] == 15
        assert stats["blocked"] == 85
        assert stats["effectiveness_pct"] == 85.0

    @pytest.mark.asyncio
    async def test_returns_zeros_when_no_data(self) -> None:
        from app.services.secret_scanning_service import get_push_protection_stats

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        stats = await get_push_protection_stats(mock_session, ["my-org"])
        assert stats["total"] == 0
        assert stats["effectiveness_pct"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Router Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecretScanningRouter:
    """Tests for the secret_scanning router module."""

    def test_router_has_correct_prefix(self) -> None:
        from app.routers.secret_scanning import router

        assert router.prefix == "/secret-scanning"

    def test_router_has_correct_tags(self) -> None:
        from app.routers.secret_scanning import router

        assert "secret-scanning" in router.tags

    def test_router_has_expected_routes(self) -> None:
        from app.routers.secret_scanning import router

        route_paths = {r.path for r in router.routes}
        expected = {
            "/secret-scanning/alerts",
            "/secret-scanning/summary",
            "/secret-scanning/trends",
            "/secret-scanning/alerts/{alert_id}",
            "/secret-scanning/sync",
            "/secret-scanning/alerts/{alert_id}/audit-trail",
            "/secret-scanning/push-protection-stats",
        }
        assert expected.issubset(route_paths), f"Missing routes: {expected - route_paths}"

    def test_router_methods(self) -> None:
        from app.routers.secret_scanning import router

        route_map: dict[str, set[str]] = {}
        for route in router.routes:
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", set())
            route_map[path] = methods

        assert "GET" in route_map.get("/secret-scanning/alerts", set())
        assert "GET" in route_map.get("/secret-scanning/summary", set())
        assert "GET" in route_map.get("/secret-scanning/trends", set())
        assert "GET" in route_map.get("/secret-scanning/alerts/{alert_id}", set())
        assert "POST" in route_map.get("/secret-scanning/sync", set())
        assert "GET" in route_map.get("/secret-scanning/alerts/{alert_id}/audit-trail", set())

    def test_list_alerts_endpoint_has_query_params(self) -> None:
        """Verify the list_alerts function accepts expected filter parameters."""
        import inspect

        from app.routers.secret_scanning import list_alerts

        sig = inspect.signature(list_alerts)
        param_names = set(sig.parameters.keys())
        expected = {
            "limit",
            "offset",
            "state",
            "secret_type",
            "validity",
            "push_protection_bypassed",
        }
        assert expected.issubset(param_names)


class TestSecretScanningRouterRegistration:
    """Test that the router is registered in main.py."""

    def test_router_imported_in_main(self) -> None:
        import app.main

        # Check that the router module was imported
        assert hasattr(app.routers, "secret_scanning")

    def test_router_module_has_router(self) -> None:
        from app.routers import secret_scanning

        assert hasattr(secret_scanning, "router")
