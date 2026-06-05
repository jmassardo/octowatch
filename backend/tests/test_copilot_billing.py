"""Tests for Copilot billing/UBB endpoints and usage model.

Covers:
- Router auth enforcement for new billing endpoints
- Service functions for billing overview, user budgets, billing trends
- Usage report persistence logic in the worker
- Model integrity
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_valkey
from app.models.copilot_usage import CopilotUsageReport
from app.routers import copilot as copilot_router_module
from app.services import copilot_metrics_service

# ── Router auth tests ─────────────────────────────────────────────────────────


def _build_copilot_app() -> FastAPI:
    """Build a minimal FastAPI app with the copilot router (no auth overrides)."""
    app = FastAPI()
    app.include_router(copilot_router_module.router, prefix="/api/v1")

    mock_db = AsyncMock(spec=AsyncSession)

    async def override_db() -> Any:
        yield mock_db

    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=None)
    mock_valkey.ping = AsyncMock(return_value=True)

    async def override_valkey() -> Any:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app


class TestCopilotBillingRouterAuth:
    """All billing endpoints must require authentication."""

    def test_billing_overview_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/billing-overview")
        assert resp.status_code == 401

    def test_user_budgets_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/user-budgets")
        assert resp.status_code == 401

    def test_billing_trends_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/billing-trends")
        assert resp.status_code == 401


# ── Service tests: billing overview ──────────────────────────────────────────


class TestCopilotBillingOverview:
    @pytest.mark.asyncio
    async def test_returns_error_when_feature_disabled(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value={"error": "feature_disabled", "message": "disabled"},
        ):
            result = await copilot_metrics_service.get_copilot_billing_overview(db)
            assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_overview_with_data(self) -> None:
        db = AsyncMock(spec=AsyncSession)

        # Mock the feature check
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value=None,
        ):
            # Mock the database query
            mock_result = MagicMock()
            mock_result.one.return_value = (1500.0, 5000.0, 25, 15)
            db.execute = AsyncMock(return_value=mock_result)

            # Mock settings
            with patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                return_value="10000",
            ):
                result = await copilot_metrics_service.get_copilot_billing_overview(db)

            assert result["total_consumed"] == 1500.0
            assert result["unique_users"] == 25
            assert result["pool_total"] == 10000.0
            assert result["pool_remaining"] == 8500.0
            assert "projected_eom" in result


class TestCopilotUserBudgets:
    @pytest.mark.asyncio
    async def test_returns_error_when_feature_disabled(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value={"error": "feature_disabled", "message": "disabled"},
        ):
            result = await copilot_metrics_service.get_copilot_user_budgets(db)
            assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_user_budgets_with_buckets(self) -> None:
        db = AsyncMock(spec=AsyncSession)

        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value=None,
        ):
            # Mock query results - simulate 3 users with different utilization
            mock_rows = [
                ("user1", "org1", 450.0, 500.0, 450.0, False),  # 90% - near
                ("user2", "org1", 200.0, 500.0, 200.0, False),  # 40% - ok
                ("user3", "org1", 550.0, 500.0, 550.0, True),  # 110% - blocked
            ]
            mock_result = MagicMock()
            mock_result.fetchall.return_value = mock_rows
            db.execute = AsyncMock(return_value=mock_result)

            result = await copilot_metrics_service.get_copilot_user_budgets(db)

            assert result["total_users"] == 3
            assert "buckets" in result
            assert "users" in result

            users = result["users"]
            assert users[0]["login"] == "user1"
            assert users[0]["status"] == "near"
            assert users[1]["login"] == "user2"
            assert users[1]["status"] == "ok"
            assert users[2]["login"] == "user3"
            assert users[2]["status"] == "blocked"


class TestCopilotBillingTrends:
    @pytest.mark.asyncio
    async def test_returns_error_when_feature_disabled(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value={"error": "feature_disabled", "message": "disabled"},
        ):
            result = await copilot_metrics_service.get_copilot_billing_trends(db)
            assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_trends_data(self) -> None:
        db = AsyncMock(spec=AsyncSession)

        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value=None,
        ):
            today = date.today()
            mock_rows = [
                (today - timedelta(days=2), 100.0, 60.0, 25.0, 10.0, 5.0, 15),
                (today - timedelta(days=1), 120.0, 70.0, 30.0, 12.0, 8.0, 18),
                (today, 110.0, 65.0, 28.0, 11.0, 6.0, 16),
            ]
            mock_result = MagicMock()
            mock_result.fetchall.return_value = mock_rows
            db.execute = AsyncMock(return_value=mock_result)

            result = await copilot_metrics_service.get_copilot_billing_trends(db)

            assert result["period_days"] == 30
            assert len(result["trends"]) == 3
            assert result["trends"][0]["total"] == 100.0
            assert result["trends"][1]["active_users"] == 18


# ── Model tests ──────────────────────────────────────────────────────────────


class TestCopilotUsageReportModel:
    def test_model_tablename(self) -> None:
        assert CopilotUsageReport.__tablename__ == "copilot_usage_reports"

    def test_model_has_expected_columns(self) -> None:
        column_names = {c.name for c in CopilotUsageReport.__table__.columns}
        expected = {
            "id",
            "report_date",
            "org_slug",
            "github_login",
            "total_credits_consumed",
            "completions_credits",
            "chat_credits",
            "pr_credits",
            "other_credits",
            "budget_amount",
            "budget_consumed",
            "is_blocked",
            "synced_at",
        }
        assert expected.issubset(column_names)

    def test_model_unique_constraint(self) -> None:
        constraints = {c.name for c in CopilotUsageReport.__table__.constraints}
        assert "uq_copilot_usage_composite" in constraints


# ── Worker tests: _persist_usage_reports ─────────────────────────────────────


class TestPersistUsageReports:
    @pytest.mark.asyncio
    async def test_empty_records_returns_zero(self) -> None:
        from app.workers.copilot_metrics_worker import _persist_usage_reports

        db = AsyncMock()
        result = await _persist_usage_reports(db, [])
        assert result == 0

    @pytest.mark.asyncio
    async def test_records_without_login_are_skipped(self) -> None:
        from app.workers.copilot_metrics_worker import _persist_usage_reports

        db = AsyncMock()
        records = [{"total_credits_consumed": 10.0}]  # No login field
        result = await _persist_usage_reports(db, records)
        assert result == 0

    @pytest.mark.asyncio
    async def test_valid_records_are_persisted(self) -> None:
        from app.workers.copilot_metrics_worker import _persist_usage_reports

        db = AsyncMock()
        db.execute = AsyncMock()

        records = [
            {
                "login": "testuser",
                "date": "2025-01-15",
                "_org_slug": "myorg",
                "total_credits_consumed": 25.5,
                "breakdown": {"completions": 15.0, "chat": 8.0, "pull_requests": 2.5},
            },
            {
                "github_login": "anotheruser",
                "day": "2025-01-15",
                "_org_slug": "myorg",
                "total_credits_consumed": 10.0,
                "completions_credits": 7.0,
                "chat_credits": 3.0,
            },
        ]

        with patch(
            "sqlalchemy.dialects.postgresql.insert",
        ) as mock_pg_insert:
            mock_stmt = MagicMock()
            mock_stmt.on_conflict_do_update = MagicMock(return_value=mock_stmt)
            mock_insert_result = MagicMock()
            mock_insert_result.values = MagicMock(return_value=mock_stmt)
            mock_pg_insert.return_value = mock_insert_result

            result = await _persist_usage_reports(db, records)

        assert result == 2
        db.execute.assert_called_once()
