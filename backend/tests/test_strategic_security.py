"""Tests for strategic security endpoints and service functions.

Covers all 4 strategic service functions and all 4 router endpoints.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.routers import health_signals as health_signals_module
from app.services import health_signal_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    scoped_orgs: list[str] | None = None,
    scope_type: str = "org",
) -> AuthenticatedUser:
    return AuthenticatedUser(
        github_login="testuser",
        github_id=42,
        roles=["analyst"],
        scoped_orgs=scoped_orgs or ["test-org"],
        scoped_repos=[],
        scope_type=scope_type,
        jti="test-jti",
        session_expires_at="2099-01-01T00:00:00+00:00",
    )


def _mock_session_with_mappings(
    *result_sets: list[dict[str, Any]],
) -> AsyncMock:
    session = AsyncMock()
    mocks = []
    for rows in result_sets:
        mapping_mock = MagicMock()
        mapping_mock.all.return_value = rows
        mapping_mock.first.return_value = rows[0] if rows else None
        mock_result = MagicMock()
        mock_result.mappings.return_value = mapping_mock
        mock_result.fetchall.return_value = rows
        mock_result.fetchone.return_value = rows[0] if rows else None
        mocks.append(mock_result)
    session.execute = AsyncMock(side_effect=mocks)
    return session


def _build_app() -> tuple[FastAPI, AsyncMock]:
    app = FastAPI()
    app.include_router(health_signals_module.router, prefix="/api/v1")

    user = _make_user()
    mock_db = AsyncMock()

    rbac_result = MagicMock()
    rbac_mapping = MagicMock()
    rbac_mapping.all.return_value = [{"org": "test-org"}]
    rbac_result.mappings.return_value = rbac_mapping
    rbac_result.fetchall.return_value = [{"org": "test-org"}]
    mock_db.execute = AsyncMock(return_value=rbac_result)

    async def override_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user

    return app, mock_db


# ===========================================================================
# Service layer tests
# ===========================================================================


class TestGetMttrTrends:
    """Test get_mttr_trends service function."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_orgs(self) -> None:
        result = await health_signal_service.get_mttr_trends(AsyncMock(), scoped_orgs=[])
        assert result["current_mttr_hours"] == 0.0
        assert result["previous_mttr_hours"] == 0.0
        assert result["trend_pct"] == 0.0
        assert result["by_severity"] == []
        assert result["time_series"] == []
        assert len(result["by_tool"]) == 3

    @pytest.mark.asyncio
    async def test_returns_expected_structure(self) -> None:
        summary = {"current_mttr_hours": Decimal("48.50"), "previous_mttr_hours": Decimal("72.00")}
        severity = [
            {"severity": "critical", "mttr_hours": Decimal("24.00"), "sample_size": 5},
            {"severity": "high", "mttr_hours": Decimal("48.00"), "sample_size": 10},
        ]
        tool = [
            {"tool": "code_scanning", "mttr_hours": Decimal("36.00")},
            {"tool": "secret_scanning", "mttr_hours": Decimal("12.00")},
            {"tool": "dependabot", "mttr_hours": Decimal("60.00")},
        ]
        series = [
            {"date": "2024-01-15", "mttr_hours": Decimal("40.00")},
            {"date": "2024-01-16", "mttr_hours": Decimal("50.00")},
        ]

        session = _mock_session_with_mappings([summary], severity, tool, series)
        result = await health_signal_service.get_mttr_trends(
            session, scoped_orgs=["test-org"], period="30d"
        )

        assert result["current_mttr_hours"] == 48.5
        assert result["previous_mttr_hours"] == 72.0
        assert result["trend_pct"] < 0  # improving
        assert len(result["by_severity"]) == 2
        assert len(result["by_tool"]) == 3
        assert len(result["time_series"]) == 2

    @pytest.mark.asyncio
    async def test_trend_pct_zero_when_no_previous(self) -> None:
        summary = {"current_mttr_hours": Decimal("48.50"), "previous_mttr_hours": Decimal("0")}
        session = _mock_session_with_mappings([summary], [], [], [])
        result = await health_signal_service.get_mttr_trends(session, scoped_orgs=["test-org"])
        assert result["trend_pct"] == 0.0


class TestGetCoverageGrowth:
    """Test get_coverage_growth service function."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_orgs(self) -> None:
        result = await health_signal_service.get_coverage_growth(AsyncMock(), scoped_orgs=[])
        assert result["total_repos"] == 0
        assert result["feature_coverage"]["ghas"]["pct"] == 0.0
        assert result["feature_coverage"]["code_scanning"]["pct"] == 0.0
        assert result["time_series"] == []
        assert result["uncovered_repos"] == []

    @pytest.mark.asyncio
    async def test_returns_expected_structure(self) -> None:
        repo_count = [{"total_repos": 100}]
        coverage = [
            {"feature": "code_scanning", "repo_count": 80},
            {"feature": "secret_scanning", "repo_count": 90},
        ]
        timeline = [
            {
                "date": "2024-01-01",
                "ghas_repos": 70,
                "code_scanning_repos": 70,
                "secret_scanning_repos": 80,
                "dependabot_repos": 75,
                "push_protection_repos": 60,
            },
        ]
        uncovered = [
            {"repo_full_name": "test-org/repo1", "missing_features": ["code_scanning"]},
        ]

        session = _mock_session_with_mappings(repo_count, coverage, timeline, uncovered)
        result = await health_signal_service.get_coverage_growth(
            session, scoped_orgs=["test-org"], period="90d"
        )

        assert result["total_repos"] == 100
        assert "feature_coverage" in result
        assert len(result["time_series"]) == 1
        assert len(result["uncovered_repos"]) == 1


class TestGetAlertAging:
    """Test get_alert_aging service function."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_orgs(self) -> None:
        result = await health_signal_service.get_alert_aging(AsyncMock(), scoped_orgs=[])
        assert len(result["age_buckets"]) == 4
        for bucket in result["age_buckets"]:
            assert bucket["total_count"] == 0
        assert result["oldest_critical"] == []
        assert result["burndown_projection"]["current_open"] == 0

    @pytest.mark.asyncio
    async def test_returns_expected_structure(self) -> None:
        buckets = [
            {"bucket": "<7d", "total_count": 10, "critical_count": 2, "high_count": 3},
            {"bucket": "7-30d", "total_count": 8, "critical_count": 1, "high_count": 2},
            {"bucket": "30-90d", "total_count": 5, "critical_count": 0, "high_count": 1},
            {"bucket": ">90d", "total_count": 3, "critical_count": 1, "high_count": 0},
        ]
        oldest = [
            {
                "tool": "code_scanning",
                "alert_number": 42,
                "repo_full_name": "test-org/repo1",
                "created_at": "2023-06-01T00:00:00",
                "severity": "critical",
                "age_days": Decimal("200.00"),
                "rule_info": "sql-injection",
                "rule_description": "SQL injection vulnerability",
            },
        ]
        burndown = [
            {"current_open": 26, "closed_last_30_days": 21},
        ]

        session = _mock_session_with_mappings(buckets, oldest, burndown)
        result = await health_signal_service.get_alert_aging(session, scoped_orgs=["test-org"])

        assert len(result["age_buckets"]) == 4
        assert result["age_buckets"][0]["total_count"] == 10
        assert len(result["oldest_critical"]) == 1
        assert result["burndown_projection"]["current_open"] == 26
        assert result["burndown_projection"]["weeks_to_zero"] is not None


class TestGetSecurityScore:
    """Test get_security_score service function."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_orgs(self) -> None:
        result = await health_signal_service.get_security_score(AsyncMock(), scoped_orgs=[])
        # Empty orgs still produce a score from default component calculations
        assert 0.0 <= result["score"] <= 100.0
        assert len(result["components"]) == 5
        assert isinstance(result["suggestions"], list)

    @pytest.mark.asyncio
    async def test_returns_expected_structure(self) -> None:
        from unittest.mock import patch

        mock_coverage = {
            "total_repos": 100,
            "feature_coverage": {
                "ghas": {"repos": 85, "pct": 85.0},
                "code_scanning": {"repos": 85, "pct": 85.0},
                "secret_scanning": {"repos": 85, "pct": 85.0},
                "dependabot": {"repos": 85, "pct": 85.0},
                "push_protection": {"repos": 85, "pct": 85.0},
            },
            "time_series": [],
            "uncovered_repos": [],
        }
        mock_mttr = {
            "current_mttr_hours": 48.0,
            "previous_mttr_hours": 60.0,
            "trend_pct": -20.0,
            "by_severity": [],
            "time_series": [],
            "by_tool": [],
        }
        mock_aging = {
            "age_buckets": [
                {"bucket": "<7d", "total_count": 5, "critical_count": 1, "high_count": 2},
                {"bucket": "7-30d", "total_count": 5, "critical_count": 0, "high_count": 1},
                {"bucket": "30-90d", "total_count": 5, "critical_count": 0, "high_count": 1},
                {"bucket": ">90d", "total_count": 5, "critical_count": 1, "high_count": 0},
            ],
            "oldest_critical": [],
            "burndown_projection": {
                "current_open": 20,
                "avg_close_rate_per_week": 5.0,
                "weeks_to_zero": 4.0,
                "time_series": [],
            },
        }

        session = AsyncMock()
        with (
            patch.object(health_signal_service, "get_coverage_growth", return_value=mock_coverage),
            patch.object(health_signal_service, "get_mttr_trends", return_value=mock_mttr),
            patch.object(health_signal_service, "get_alert_aging", return_value=mock_aging),
        ):
            result = await health_signal_service.get_security_score(
                session, scoped_orgs=["test-org"]
            )

        assert 0.0 <= result["score"] <= 100.0
        assert len(result["components"]) == 5
        component_names = {c["name"] for c in result["components"]}
        assert "Coverage" in component_names
        assert "MTTR" in component_names
        assert "Alert Volume" in component_names
        assert "Aging" in component_names
        assert "Trend" in component_names

        for comp in result["components"]:
            assert 0.0 <= comp["score"] <= 100.0
            assert comp["weight"] > 0

    @pytest.mark.asyncio
    async def test_score_high_for_good_metrics(self) -> None:
        from unittest.mock import patch

        mock_coverage = {
            "total_repos": 100,
            "feature_coverage": {
                "ghas": {"repos": 95, "pct": 95.0},
                "code_scanning": {"repos": 95, "pct": 95.0},
                "secret_scanning": {"repos": 95, "pct": 95.0},
                "dependabot": {"repos": 95, "pct": 95.0},
                "push_protection": {"repos": 95, "pct": 95.0},
            },
            "time_series": [],
            "uncovered_repos": [],
        }
        mock_mttr = {
            "current_mttr_hours": 24.0,
            "previous_mttr_hours": 48.0,
            "trend_pct": -50.0,
            "by_severity": [],
            "time_series": [],
            "by_tool": [],
        }
        mock_aging = {
            "age_buckets": [
                {"bucket": "<7d", "total_count": 2, "critical_count": 0, "high_count": 0},
                {"bucket": "7-30d", "total_count": 0, "critical_count": 0, "high_count": 0},
                {"bucket": "30-90d", "total_count": 0, "critical_count": 0, "high_count": 0},
                {"bucket": ">90d", "total_count": 0, "critical_count": 0, "high_count": 0},
            ],
            "oldest_critical": [],
            "burndown_projection": {
                "current_open": 2,
                "avg_close_rate_per_week": 10.0,
                "weeks_to_zero": 0.2,
                "time_series": [],
            },
        }

        session = AsyncMock()
        with (
            patch.object(health_signal_service, "get_coverage_growth", return_value=mock_coverage),
            patch.object(health_signal_service, "get_mttr_trends", return_value=mock_mttr),
            patch.object(health_signal_service, "get_alert_aging", return_value=mock_aging),
        ):
            result = await health_signal_service.get_security_score(
                session, scoped_orgs=["test-org"]
            )

        assert result["score"] >= 80.0


# ===========================================================================
# Router endpoint tests
# ===========================================================================


class TestStrategicEndpoints:
    """Test the 4 strategic security router endpoints."""

    def test_mttr_trends_endpoint_accepts_period(self) -> None:
        from unittest.mock import patch

        app, mock_db = _build_app()

        mock_data: dict[str, Any] = {
            "current_mttr_hours": 48.0,
            "previous_mttr_hours": 72.0,
            "trend_pct": -33.33,
            "by_severity": [],
            "time_series": [],
            "by_tool": [
                {"tool": "code_scanning", "mttr_hours": 36.0},
                {"tool": "secret_scanning", "mttr_hours": 12.0},
                {"tool": "dependabot", "mttr_hours": 60.0},
            ],
        }

        with patch.object(
            health_signal_service, "get_mttr_trends", new_callable=AsyncMock
        ) as mock_fn:
            mock_fn.return_value = mock_data
            with TestClient(app) as client:
                resp = client.get("/api/v1/health-signals/strategic/mttr-trends?period=30d")

            assert resp.status_code == 200
            data = resp.json()
            assert "current_mttr_hours" in data
            assert "by_tool" in data
            assert len(data["by_tool"]) == 3

    def test_mttr_trends_rejects_invalid_period(self) -> None:
        from unittest.mock import patch

        app, _ = _build_app()

        with patch.object(health_signal_service, "get_mttr_trends", new_callable=AsyncMock):
            with TestClient(app) as client:
                resp = client.get("/api/v1/health-signals/strategic/mttr-trends?period=999d")
            assert resp.status_code == 422

    def test_coverage_growth_endpoint(self) -> None:
        from unittest.mock import patch

        app, _ = _build_app()

        mock_data: dict[str, Any] = {
            "total_repos": 100,
            "feature_coverage": {
                "ghas": {"repos": 80, "pct": 80.0},
                "code_scanning": {"repos": 80, "pct": 80.0},
                "secret_scanning": {"repos": 90, "pct": 90.0},
                "dependabot": {"repos": 85, "pct": 85.0},
                "push_protection": {"repos": 70, "pct": 70.0},
            },
            "time_series": [],
            "uncovered_repos": [],
        }

        with patch.object(
            health_signal_service, "get_coverage_growth", new_callable=AsyncMock
        ) as mock_fn:
            mock_fn.return_value = mock_data
            with TestClient(app) as client:
                resp = client.get("/api/v1/health-signals/strategic/coverage-growth?period=90d")

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_repos"] == 100

    def test_alert_aging_endpoint(self) -> None:
        from unittest.mock import patch

        app, _ = _build_app()

        mock_data: dict[str, Any] = {
            "age_buckets": [
                {"bucket": "<7d", "total_count": 10, "critical_count": 2, "high_count": 3},
                {"bucket": "7-30d", "total_count": 8, "critical_count": 1, "high_count": 2},
                {"bucket": "30-90d", "total_count": 5, "critical_count": 0, "high_count": 1},
                {"bucket": ">90d", "total_count": 3, "critical_count": 1, "high_count": 0},
            ],
            "oldest_critical": [],
            "burndown_projection": {
                "current_open": 26,
                "avg_close_rate_per_week": 5.0,
                "weeks_to_zero": 5.2,
                "time_series": [],
            },
        }

        with patch.object(
            health_signal_service, "get_alert_aging", new_callable=AsyncMock
        ) as mock_fn:
            mock_fn.return_value = mock_data
            with TestClient(app) as client:
                resp = client.get("/api/v1/health-signals/strategic/alert-aging")

            assert resp.status_code == 200
            data = resp.json()
            assert len(data["age_buckets"]) == 4
            assert data["burndown_projection"]["current_open"] == 26

    def test_security_score_endpoint(self) -> None:
        from unittest.mock import patch

        app, _ = _build_app()

        mock_data: dict[str, Any] = {
            "score": 78.5,
            "components": [
                {
                    "name": "Coverage",
                    "score": 85.0,
                    "weight": 30,
                    "description": "GHAS feature coverage",
                },
                {
                    "name": "MTTR",
                    "score": 75.0,
                    "weight": 25,
                    "description": "Mean time to remediate",
                },
                {
                    "name": "Alert Volume",
                    "score": 80.0,
                    "weight": 20,
                    "description": "Open alerts per repo",
                },
                {
                    "name": "Aging",
                    "score": 70.0,
                    "weight": 15,
                    "description": "Alert aging penalty",
                },
                {
                    "name": "Trend",
                    "score": 60.0,
                    "weight": 10,
                    "description": "MTTR trend direction",
                },
            ],
            "suggestions": [
                {
                    "name": "Aging",
                    "impact": 450,
                    "suggestion": "Address alerts older than 30 days",
                },
            ],
        }

        with patch.object(
            health_signal_service, "get_security_score", new_callable=AsyncMock
        ) as mock_fn:
            mock_fn.return_value = mock_data
            with TestClient(app) as client:
                resp = client.get("/api/v1/health-signals/strategic/security-score")

            assert resp.status_code == 200
            data = resp.json()
            assert data["score"] == 78.5
            assert len(data["components"]) == 5
            assert len(data["suggestions"]) >= 1
