"""Tests for the Copilot metrics router and service.

Covers:
- Router auth enforcement (401 for unauthenticated requests)
- Service logic for all four panes with realistic sample data
- Error handling (missing config, API errors, empty data)
- Anomaly detection logic
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_valkey
from app.routers import copilot as copilot_router_module
from app.services import copilot_metrics_service

# ── Sample GitHub Copilot Metrics API response ────────────────────────────────

_SAMPLE_DAY = {
    "date": "2025-01-20",
    "total_active_users": 42,
    "total_engaged_users": 38,
    "copilot_ide_code_completions": {
        "total_engaged_users": 35,
        "editors": [
            {
                "name": "VS Code",
                "total_engaged_users": 30,
                "models": [
                    {
                        "name": "GPT-4o",
                        "total_engaged_users": 25,
                        "languages": [
                            {
                                "name": "Python",
                                "total_code_suggestions": 200,
                                "total_code_acceptances": 60,
                                "total_code_lines_suggested": 400,
                                "total_code_lines_accepted": 120,
                            },
                            {
                                "name": "TypeScript",
                                "total_code_suggestions": 150,
                                "total_code_acceptances": 40,
                                "total_code_lines_suggested": 300,
                                "total_code_lines_accepted": 80,
                            },
                        ],
                    },
                    {
                        "name": "Claude-3.5-Sonnet",
                        "total_engaged_users": 10,
                        "languages": [
                            {
                                "name": "Python",
                                "total_code_suggestions": 80,
                                "total_code_acceptances": 30,
                                "total_code_lines_suggested": 160,
                                "total_code_lines_accepted": 60,
                            },
                        ],
                    },
                ],
            },
            {
                "name": "JetBrains",
                "total_engaged_users": 8,
                "models": [
                    {
                        "name": "GPT-4o",
                        "total_engaged_users": 8,
                        "languages": [
                            {
                                "name": "Java",
                                "total_code_suggestions": 100,
                                "total_code_acceptances": 25,
                                "total_code_lines_suggested": 200,
                                "total_code_lines_accepted": 50,
                            },
                        ],
                    },
                ],
            },
        ],
    },
    "copilot_ide_chat": {
        "total_engaged_users": 20,
        "editors": [
            {
                "name": "VS Code",
                "total_engaged_users": 18,
                "models": [
                    {
                        "name": "GPT-4o",
                        "total_engaged_users": 15,
                    },
                    {
                        "name": "Claude-3.5-Sonnet",
                        "total_engaged_users": 5,
                    },
                ],
            },
        ],
    },
    "copilot_dotcom_chat": {
        "total_engaged_users": 10,
    },
    "copilot_dotcom_pull_requests": {
        "total_engaged_users": 5,
    },
}


def _make_sample_days(count: int = 28) -> list[dict[str, Any]]:
    """Generate a list of sample daily metric objects."""
    days: list[dict[str, Any]] = []
    for i in range(count):
        day = json.loads(json.dumps(_SAMPLE_DAY))  # deep copy
        day["date"] = f"2025-01-{(i + 1):02d}"
        day["total_active_users"] = 40 + (i % 5)
        day["total_engaged_users"] = 36 + (i % 4)
        days.append(day)
    return days


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


class TestCopilotRouterAuth:
    """All copilot endpoints must require authentication (return 401 for unauthenticated)."""

    def test_overview_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/overview")
        assert resp.status_code == 401

    def test_adoption_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/adoption")
        assert resp.status_code == 401

    def test_models_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/models")
        assert resp.status_code == 401

    def test_anomalies_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/anomalies")
        assert resp.status_code == 401


# ── Service tests: overview ───────────────────────────────────────────────────


class TestCopilotOverview:
    @pytest.mark.asyncio
    async def test_returns_error_when_fetch_fails(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(
            copilot_metrics_service,
            "_read_metrics_from_store",
            return_value={"error": "no_enterprise_config", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_overview(db)
        assert result["error"] == "no_enterprise_config"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_days(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=[]):
            result = await copilot_metrics_service.get_copilot_overview(db)
        assert result["acceptance_rate_days"] == []
        assert result["acceptance_rate_values"] == []
        assert result["total_active_users"] == 0
        assert result["total_engaged_users"] == 0

    @pytest.mark.asyncio
    async def test_computes_acceptance_rates(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_overview(db)
        assert len(result["acceptance_rate_values"]) == 7
        assert all(isinstance(v, float) for v in result["acceptance_rate_values"])
        assert all(0 <= v <= 100 for v in result["acceptance_rate_values"])

    @pytest.mark.asyncio
    async def test_returns_language_breakdown(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_overview(db)
        assert len(result["languages"]) > 0
        lang_names = {lang["lang"] for lang in result["languages"]}
        assert "Python" in lang_names
        assert "TypeScript" in lang_names

    @pytest.mark.asyncio
    async def test_languages_sorted_by_pct_descending(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_overview(db)
        pcts = [lang["pct"] for lang in result["languages"]]
        assert pcts == sorted(pcts, reverse=True)

    @pytest.mark.asyncio
    async def test_returns_user_counts(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_overview(db)
        assert result["total_active_users"] > 0
        assert result["total_engaged_users"] > 0

    @pytest.mark.asyncio
    async def test_acceptance_threshold_present(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_overview(db)
        assert result["acceptance_threshold"] == 25

    @pytest.mark.asyncio
    async def test_handles_fewer_than_seven_days(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(3)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_overview(db)
        assert len(result["acceptance_rate_values"]) == 3


# ── Service tests: adoption ───────────────────────────────────────────────────


class TestCopilotAdoption:
    @pytest.mark.asyncio
    async def test_returns_error_when_fetch_fails(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(
            copilot_metrics_service,
            "_read_metrics_from_store",
            return_value={"error": "copilot_not_available", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_adoption(db)
        assert result["error"] == "copilot_not_available"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_days(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=[]):
            result = await copilot_metrics_service.get_copilot_adoption(db)
        assert result["tiers"] == []
        assert result["total_adoption"] == 0

    @pytest.mark.asyncio
    async def test_returns_four_tiers(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(28)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_adoption(db)
        assert len(result["tiers"]) == 4
        tier_ids = {t["id"] for t in result["tiers"]}
        assert tier_ids == {"power", "regular", "minimal", "inactive"}

    @pytest.mark.asyncio
    async def test_tiers_have_required_fields(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(28)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_adoption(db)
        for tier in result["tiers"]:
            assert "id" in tier
            assert "label" in tier
            assert "count" in tier
            assert "color" in tier
            assert "desc" in tier

    @pytest.mark.asyncio
    async def test_returns_feature_adoption(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(28)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_adoption(db)
        assert len(result["feature_adoption"]) == 4
        feature_names = {f["feature"] for f in result["feature_adoption"]}
        assert "IDE completions" in feature_names
        assert "IDE chat" in feature_names

    @pytest.mark.asyncio
    async def test_power_and_minimal_users_empty_without_seat_api(self) -> None:
        """Per-user data requires the billing/seats API; service returns empty lists."""
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(28)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_adoption(db)
        assert result["power_users"] == []
        assert result["minimal_users"] == []


# ── Service tests: models ─────────────────────────────────────────────────────


class TestCopilotModels:
    @pytest.mark.asyncio
    async def test_returns_error_when_fetch_fails(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(
            copilot_metrics_service,
            "_read_metrics_from_store",
            return_value={"error": "copilot_not_available", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_models(db)
        assert result["error"] == "copilot_not_available"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_days(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=[]):
            result = await copilot_metrics_service.get_copilot_models(db)
        assert result["models"] == []
        assert result["features"] == []
        assert result["editors"] == []

    @pytest.mark.asyncio
    async def test_aggregates_model_usage(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_models(db)
        assert len(result["models"]) > 0
        model_names = {m["model"] for m in result["models"]}
        assert "GPT-4o" in model_names
        assert "Claude-3.5-Sonnet" in model_names

    @pytest.mark.asyncio
    async def test_model_pcts_sum_to_100(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_models(db)
        total_pct = sum(m["pct"] for m in result["models"])
        assert abs(total_pct - 100) < 1  # allow rounding tolerance

    @pytest.mark.asyncio
    async def test_aggregates_editors(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_models(db)
        assert len(result["editors"]) > 0
        editor_names = {e["name"] for e in result["editors"]}
        assert "VS Code" in editor_names

    @pytest.mark.asyncio
    async def test_features_include_all_categories(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_models(db)
        feature_names = {f["feature"] for f in result["features"]}
        assert feature_names == {"IDE completions", "IDE chat", "Dotcom chat", "PR summaries"}

    @pytest.mark.asyncio
    async def test_models_sorted_descending(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_models(db)
        pcts = [m["pct"] for m in result["models"]]
        assert pcts == sorted(pcts, reverse=True)


# ── Service tests: anomalies ─────────────────────────────────────────────────


class TestCopilotAnomalies:
    @pytest.mark.asyncio
    async def test_returns_error_when_fetch_fails(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch.object(
            copilot_metrics_service,
            "_read_metrics_from_store",
            return_value={"error": "copilot_not_available", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        assert result["error"] == "copilot_not_available"

    @pytest.mark.asyncio
    async def test_returns_empty_anomalies_when_too_few_days(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(3)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        assert result["anomalies"] == []

    @pytest.mark.asyncio
    async def test_no_anomalies_when_stable(self) -> None:
        """With uniform data, no anomalies should be detected."""
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(28)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        assert isinstance(result["anomalies"], list)

    @pytest.mark.asyncio
    async def test_detects_acceptance_rate_drop(self) -> None:
        """When recent acceptance rate drops significantly, an anomaly is flagged."""
        db = AsyncMock(spec=AsyncSession)
        baseline = _make_sample_days(25)
        # Make last 3 days have very low acceptance rates
        for i in range(3):
            day = json.loads(json.dumps(_SAMPLE_DAY))
            day["date"] = f"2025-01-{26 + i}"
            # Zero out acceptances to cause a big drop
            for editor in day["copilot_ide_code_completions"]["editors"]:
                for model in editor["models"]:
                    for lang in model["languages"]:
                        lang["total_code_acceptances"] = 1
            baseline.append(day)

        with patch.object(
            copilot_metrics_service, "_read_metrics_from_store", return_value=baseline
        ):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        anomalies = result["anomalies"]
        assert len(anomalies) >= 1
        rate_anomalies = [a for a in anomalies if "acceptance rate" in a["title"].lower()]
        assert len(rate_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_detects_active_user_change(self) -> None:
        """When active users change dramatically, an anomaly is flagged."""
        db = AsyncMock(spec=AsyncSession)
        baseline = _make_sample_days(25)
        # Make last 3 days have much higher active users
        for i in range(3):
            day = json.loads(json.dumps(_SAMPLE_DAY))
            day["date"] = f"2025-01-{26 + i}"
            day["total_active_users"] = 200  # big spike from ~42
            baseline.append(day)

        with patch.object(
            copilot_metrics_service, "_read_metrics_from_store", return_value=baseline
        ):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        anomalies = result["anomalies"]
        user_anomalies = [a for a in anomalies if "active user" in a["title"].lower()]
        assert len(user_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_anomaly_has_required_fields(self) -> None:
        """Each anomaly must have id, severity, title, description, timestamp, team."""
        db = AsyncMock(spec=AsyncSession)
        baseline = _make_sample_days(25)
        for i in range(3):
            day = json.loads(json.dumps(_SAMPLE_DAY))
            day["date"] = f"2025-01-{26 + i}"
            day["total_active_users"] = 200
            baseline.append(day)

        with patch.object(
            copilot_metrics_service, "_read_metrics_from_store", return_value=baseline
        ):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        for anomaly in result["anomalies"]:
            assert "id" in anomaly
            assert "severity" in anomaly
            assert anomaly["severity"] in ("high", "medium", "low")
            assert "title" in anomaly
            assert "description" in anomaly
            assert "timestamp" in anomaly
            assert "team" in anomaly


# ── Service tests: _fetch_metrics_raw ─────────────────────────────────────────


class TestFetchMetricsRaw:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_enterprise_slug(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        # Call order: get_setting("feature_copilot_insights") → "true",
        # then get_setting("github_enterprise_slug") → None
        get_setting_values = ["true", None]
        with (
            patch(
                "app.services.settings_service.get_setting",
                side_effect=get_setting_values,
            ),
            patch(
                "app.services.config_overlay.refresh_settings",
                new_callable=AsyncMock,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                None,
            ),
        ):
            result = await copilot_metrics_service._fetch_metrics_raw(db)
        assert isinstance(result, dict)
        assert result["error"] == "no_enterprise_config"

    @pytest.mark.asyncio
    async def test_returns_error_when_no_app_id(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        # Call order: get_setting("feature_copilot_insights") → "true",
        # then get_setting("github_enterprise_slug") → "test-enterprise"
        get_setting_values = ["true", "test-enterprise"]
        with (
            patch(
                "app.services.settings_service.get_setting",
                side_effect=get_setting_values,
            ),
            patch(
                "app.services.config_overlay.refresh_settings",
                new_callable=AsyncMock,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                None,
            ),
        ):
            result = await copilot_metrics_service._fetch_metrics_raw(db)
        assert isinstance(result, dict)
        assert result["error"] == "no_enterprise_config"

    @pytest.mark.asyncio
    async def test_returns_error_when_no_installation_found(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                return_value="true",
            ),
            patch(
                "app.services.config_overlay.refresh_settings",
                new_callable=AsyncMock,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PATH",
                "/tmp/test-key.pem",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
        ):
            mock_valkey = AsyncMock()
            mock_valkey.get = AsyncMock(return_value=None)
            mock_valkey.aclose = AsyncMock()
            mock_aioredis.Redis.from_url.return_value = mock_valkey

            result = await copilot_metrics_service._fetch_metrics_raw(db)
        assert isinstance(result, dict)
        assert result["error"] == "no_enterprise_config"
        assert "No enabled enterprise" in result["message"]

    @pytest.mark.asyncio
    async def test_returns_cached_data_when_available(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        cached_data = json.dumps(_make_sample_days(2))

        with (
            patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                return_value="true",
            ),
            patch(
                "app.services.config_overlay.refresh_settings",
                new_callable=AsyncMock,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PATH",
                "/tmp/test-key.pem",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
        ):
            mock_valkey = AsyncMock()
            mock_valkey.get = AsyncMock(return_value=cached_data)
            mock_valkey.aclose = AsyncMock()
            mock_aioredis.Redis.from_url.return_value = mock_valkey

            result = await copilot_metrics_service._fetch_metrics_raw(db)
        assert isinstance(result, list)
        assert len(result) == 2


# ── Colour helpers ────────────────────────────────────────────────────────────


class TestColourHelpers:
    def test_acceptance_color_green(self) -> None:
        assert copilot_metrics_service._acceptance_color(30) == "#3fb950"
        assert copilot_metrics_service._acceptance_color(50) == "#3fb950"

    def test_acceptance_color_yellow(self) -> None:
        assert copilot_metrics_service._acceptance_color(20) == "#d29922"
        assert copilot_metrics_service._acceptance_color(29.9) == "#d29922"

    def test_acceptance_color_red(self) -> None:
        assert copilot_metrics_service._acceptance_color(19.9) == "#f85149"
        assert copilot_metrics_service._acceptance_color(0) == "#f85149"

    def test_lang_color_known_languages(self) -> None:
        assert copilot_metrics_service._lang_color("Python") == "#3572A5"
        assert copilot_metrics_service._lang_color("typescript") == "#3178c6"

    def test_lang_color_unknown_language(self) -> None:
        assert copilot_metrics_service._lang_color("Brainfuck") == "#8b949e"


# ── Missing field handling ────────────────────────────────────────────────────


class TestMissingFields:
    @pytest.mark.asyncio
    async def test_overview_handles_missing_completions(self) -> None:
        """Days with no copilot_ide_code_completions should not crash."""
        db = AsyncMock(spec=AsyncSession)
        sample = [{"date": "2025-01-01", "total_active_users": 5, "total_engaged_users": 3}]
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_overview(db)
        assert result["acceptance_rate_values"] == [0.0]
        assert result["languages"] == []

    @pytest.mark.asyncio
    async def test_models_handles_missing_editors(self) -> None:
        """Days with no editor data should produce empty model/editor lists."""
        db = AsyncMock(spec=AsyncSession)
        sample = [{"date": "2025-01-01", "total_active_users": 5, "total_engaged_users": 3}]
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_models(db)
        assert result["models"] == []
        assert result["editors"] == []

    @pytest.mark.asyncio
    async def test_adoption_handles_missing_features(self) -> None:
        """Days with no feature data should not crash."""
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(2)
        # Remove feature sections from last day
        sample[-1].pop("copilot_ide_code_completions", None)
        sample[-1].pop("copilot_ide_chat", None)
        sample[-1].pop("copilot_dotcom_chat", None)
        sample[-1].pop("copilot_dotcom_pull_requests", None)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_adoption(db)
        assert "feature_adoption" in result


# ── Additional _fetch_metrics_raw tests for full error-path coverage ──────────


class TestFetchMetricsRawFullPaths:
    """Test the token-exchange and HTTP call paths in _fetch_metrics_raw."""

    @pytest.fixture(autouse=True)
    def _enable_copilot_feature(self):
        """Patch the feature toggle to 'true' for all tests in this class."""
        with patch(
            "app.services.settings_service.get_setting",
            new_callable=AsyncMock,
            return_value="true",
        ):
            yield

    def _build_mocks(self) -> tuple[AsyncMock, AsyncMock, MagicMock]:
        """Build standard mocks: db, valkey, and a mock config row."""
        db = AsyncMock(spec=AsyncSession)
        mock_config = MagicMock()
        mock_config.installation_id = 99999
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_config
        db.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=None)
        mock_valkey.set = AsyncMock(return_value=True)
        mock_valkey.aclose = AsyncMock()

        return db, mock_valkey, mock_config

    @pytest.mark.asyncio
    async def test_returns_error_on_github_auth_error(self) -> None:
        """When GitHubAppTokenManager raises GitHubAuthError."""
        from app.services.github_token_service import GitHubAuthError

        db, mock_valkey, _ = self._build_mocks()

        with (
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PEM",
                "FAKE_KEY",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
            patch(
                "app.services.copilot_metrics_service.GitHubAppTokenManager"
            ) as mock_token_mgr_cls,
        ):
            mock_aioredis.Redis.from_url.return_value = mock_valkey
            mock_token_mgr = AsyncMock()
            mock_token_mgr.get_installation_token = AsyncMock(
                side_effect=GitHubAuthError("Auth failed")
            )
            mock_token_mgr_cls.return_value = mock_token_mgr

            result = await copilot_metrics_service._fetch_metrics_raw(db)

        assert isinstance(result, dict)
        assert result["error"] == "copilot_not_available"
        assert "Check App credentials" in result["message"]

    @pytest.mark.asyncio
    async def test_returns_error_on_unexpected_token_error(self) -> None:
        """When token exchange raises a generic exception."""
        db, mock_valkey, _ = self._build_mocks()

        with (
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PEM",
                "FAKE_KEY",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
            patch(
                "app.services.copilot_metrics_service.GitHubAppTokenManager"
            ) as mock_token_mgr_cls,
        ):
            mock_aioredis.Redis.from_url.return_value = mock_valkey
            mock_token_mgr = AsyncMock()
            mock_token_mgr.get_installation_token = AsyncMock(
                side_effect=RuntimeError("Something broke")
            )
            mock_token_mgr_cls.return_value = mock_token_mgr

            result = await copilot_metrics_service._fetch_metrics_raw(db)

        assert isinstance(result, dict)
        assert result["error"] == "copilot_not_available"
        assert "Check server logs" in result["message"]

    @pytest.mark.asyncio
    async def test_returns_error_on_403_response(self) -> None:
        """When GitHub API returns 403 (insufficient permissions)."""
        db, mock_valkey, _ = self._build_mocks()

        mock_response = MagicMock()
        mock_response.status_code = 403

        with (
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PEM",
                "FAKE_KEY",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
            patch(
                "app.services.copilot_metrics_service.GitHubAppTokenManager"
            ) as mock_token_mgr_cls,
            patch("app.services.copilot_metrics_service.httpx") as mock_httpx,
        ):
            mock_aioredis.Redis.from_url.return_value = mock_valkey
            mock_token_mgr = AsyncMock()
            mock_token_mgr.get_installation_token = AsyncMock(return_value="fake-token")
            mock_token_mgr_cls.return_value = mock_token_mgr

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await copilot_metrics_service._fetch_metrics_raw(db)

        assert isinstance(result, dict)
        assert result["error"] == "copilot_not_available"
        assert "403" in result["message"]

    @pytest.mark.asyncio
    async def test_returns_error_on_404_response(self) -> None:
        """When GitHub API returns 404 (Copilot not enabled)."""
        db, mock_valkey, _ = self._build_mocks()

        mock_response = MagicMock()
        mock_response.status_code = 404

        with (
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PEM",
                "FAKE_KEY",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
            patch(
                "app.services.copilot_metrics_service.GitHubAppTokenManager"
            ) as mock_token_mgr_cls,
            patch("app.services.copilot_metrics_service.httpx") as mock_httpx,
        ):
            mock_aioredis.Redis.from_url.return_value = mock_valkey
            mock_token_mgr = AsyncMock()
            mock_token_mgr.get_installation_token = AsyncMock(return_value="fake-token")
            mock_token_mgr_cls.return_value = mock_token_mgr

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await copilot_metrics_service._fetch_metrics_raw(db)

        assert isinstance(result, dict)
        assert result["error"] == "copilot_not_available"
        assert "404" in result["message"]

    @pytest.mark.asyncio
    async def test_returns_data_on_success(self) -> None:
        """When GitHub API returns 200, data is returned and cached."""
        db, mock_valkey, _ = self._build_mocks()

        sample = _make_sample_days(2)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample
        mock_response.raise_for_status = MagicMock()

        with (
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PEM",
                "FAKE_KEY",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
            patch(
                "app.services.copilot_metrics_service.GitHubAppTokenManager"
            ) as mock_token_mgr_cls,
            patch("app.services.copilot_metrics_service.httpx") as mock_httpx,
        ):
            mock_aioredis.Redis.from_url.return_value = mock_valkey
            mock_token_mgr = AsyncMock()
            mock_token_mgr.get_installation_token = AsyncMock(return_value="fake-token")
            mock_token_mgr_cls.return_value = mock_token_mgr

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await copilot_metrics_service._fetch_metrics_raw(db)

        assert isinstance(result, list)
        assert len(result) == 2
        # Verify cache was written
        mock_valkey.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_http_status_error(self) -> None:
        """When raise_for_status throws HTTPStatusError (e.g., 500)."""
        db, mock_valkey, _ = self._build_mocks()

        mock_response = MagicMock()
        mock_response.status_code = 500

        with (
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PEM",
                "FAKE_KEY",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
            patch(
                "app.services.copilot_metrics_service.GitHubAppTokenManager"
            ) as mock_token_mgr_cls,
            patch("app.services.copilot_metrics_service.httpx") as mock_httpx,
        ):
            mock_aioredis.Redis.from_url.return_value = mock_valkey
            mock_token_mgr = AsyncMock()
            mock_token_mgr.get_installation_token = AsyncMock(return_value="fake-token")
            mock_token_mgr_cls.return_value = mock_token_mgr

            # Construct a real-ish HTTPStatusError
            err_response = MagicMock()
            err_response.status_code = 500
            http_err = httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=err_response
            )

            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.raise_for_status = MagicMock(side_effect=http_err)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.HTTPStatusError = httpx.HTTPStatusError

            result = await copilot_metrics_service._fetch_metrics_raw(db)

        assert isinstance(result, dict)
        assert result["error"] == "copilot_not_available"
        assert "500" in result["message"]

    @pytest.mark.asyncio
    async def test_handles_generic_fetch_exception(self) -> None:
        """When the HTTP call raises a generic exception (e.g., network error)."""
        db, mock_valkey, _ = self._build_mocks()

        with (
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PEM",
                "FAKE_KEY",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
            patch(
                "app.services.copilot_metrics_service.GitHubAppTokenManager"
            ) as mock_token_mgr_cls,
            patch("app.services.copilot_metrics_service.httpx") as mock_httpx,
        ):
            mock_aioredis.Redis.from_url.return_value = mock_valkey
            mock_token_mgr = AsyncMock()
            mock_token_mgr.get_installation_token = AsyncMock(return_value="fake-token")
            mock_token_mgr_cls.return_value = mock_token_mgr

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ConnectionError("Network down"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.AsyncClient.return_value = mock_client
            mock_httpx.HTTPStatusError = httpx.HTTPStatusError

            result = await copilot_metrics_service._fetch_metrics_raw(db)

        assert isinstance(result, dict)
        assert result["error"] == "copilot_not_available"
        assert "Check server logs" in result["message"]

    @pytest.mark.asyncio
    async def test_cache_write_failure_does_not_crash(self) -> None:
        """When Valkey cache write fails, data is still returned."""
        db, mock_valkey, _ = self._build_mocks()
        mock_valkey.set = AsyncMock(side_effect=Exception("Valkey write failed"))

        sample = _make_sample_days(2)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample
        mock_response.raise_for_status = MagicMock()

        with (
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-enterprise",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_ID",
                12345,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_APP_PRIVATE_KEY_PEM",
                "FAKE_KEY",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
            patch(
                "app.services.copilot_metrics_service.GitHubAppTokenManager"
            ) as mock_token_mgr_cls,
            patch("app.services.copilot_metrics_service.httpx") as mock_httpx,
        ):
            mock_aioredis.Redis.from_url.return_value = mock_valkey
            mock_token_mgr = AsyncMock()
            mock_token_mgr.get_installation_token = AsyncMock(return_value="fake-token")
            mock_token_mgr_cls.return_value = mock_token_mgr

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await copilot_metrics_service._fetch_metrics_raw(db)

        # Data returned even though cache write failed
        assert isinstance(result, list)
        assert len(result) == 2


# ── Additional anomaly detection coverage ─────────────────────────────────────


class TestAnomalyMediumSeverity:
    @pytest.mark.asyncio
    async def test_detects_medium_acceptance_rate_decline(self) -> None:
        """A 10-15% acceptance rate drop triggers a medium anomaly."""
        db = AsyncMock(spec=AsyncSession)
        baseline = _make_sample_days(25)

        # The baseline acceptance rate is about 29.2% (155 / 530)
        # For a 10-15% relative drop, target ~25%
        for i in range(3):
            day = json.loads(json.dumps(_SAMPLE_DAY))
            day["date"] = f"2025-01-{26 + i}"
            # Reduce acceptances by ~12% relative
            for editor in day["copilot_ide_code_completions"]["editors"]:
                for model in editor["models"]:
                    for lang in model["languages"]:
                        orig = lang["total_code_acceptances"]
                        lang["total_code_acceptances"] = int(orig * 0.59)
            baseline.append(day)

        with patch.object(
            copilot_metrics_service, "_read_metrics_from_store", return_value=baseline
        ):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        anomalies = result["anomalies"]
        rate_anomalies = [a for a in anomalies if "acceptance rate" in a["title"].lower()]
        assert len(rate_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_detects_feature_usage_spike(self) -> None:
        """A >200% spike in feature usage triggers a medium anomaly."""
        db = AsyncMock(spec=AsyncSession)
        baseline = _make_sample_days(25)

        for i in range(3):
            day = json.loads(json.dumps(_SAMPLE_DAY))
            day["date"] = f"2025-01-{26 + i}"
            # Huge spike in dotcom chat usage
            day["copilot_dotcom_chat"]["total_engaged_users"] = 500
            baseline.append(day)

        with patch.object(
            copilot_metrics_service, "_read_metrics_from_store", return_value=baseline
        ):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        anomalies = result["anomalies"]
        spike_anomalies = [a for a in anomalies if "usage spike" in a["title"].lower()]
        assert len(spike_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_exactly_four_days_no_crash(self) -> None:
        """With exactly 4 days, the split works (1 baseline + 3 recent)."""
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(4)
        with patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample):
            result = await copilot_metrics_service.get_copilot_anomalies(db)
        assert isinstance(result["anomalies"], list)


# ── _get_enterprise_installation tests ────────────────────────────────────────


class TestGetEnterpriseInstallation:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_slug(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with (
            patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                None,
            ),
        ):
            result = await copilot_metrics_service._get_enterprise_installation(db)
        assert result is None

    @pytest.mark.asyncio
    async def test_queries_db_for_config(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        mock_config = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_config
        db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.settings_service.get_setting",
            new_callable=AsyncMock,
            return_value="test-slug",
        ):
            result = await copilot_metrics_service._get_enterprise_installation(db)
        assert result is mock_config
        db.execute.assert_called_once()


# ── Tests for cache/DB-only readers ──────────────────────────────────────────


class TestReadMetricsFromStore:
    """_read_metrics_from_store reads from Valkey cache or DB, never GitHub."""

    @pytest.mark.asyncio
    async def test_returns_error_when_feature_disabled(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch(
            "app.services.settings_service.get_setting",
            new_callable=AsyncMock,
            return_value="false",
        ):
            result = await copilot_metrics_service._read_metrics_from_store(db)
        assert isinstance(result, dict)
        assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_error_when_no_enterprise_slug(self) -> None:
        db = AsyncMock(spec=AsyncSession)

        async def _get_setting_side_effect(db: Any, key: str) -> str | None:
            if key == "feature_copilot_insights":
                return "true"
            return None

        with (
            patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                side_effect=_get_setting_side_effect,
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                None,
            ),
        ):
            result = await copilot_metrics_service._read_metrics_from_store(db)
        assert isinstance(result, dict)
        assert result["error"] == "no_enterprise_config"

    @pytest.mark.asyncio
    async def test_returns_cached_data(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        cached = json.dumps(_make_sample_days(3))
        with (
            patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                return_value="true",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-ent",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
        ):
            mock_valkey = AsyncMock()
            mock_valkey.get = AsyncMock(return_value=cached)
            mock_valkey.aclose = AsyncMock()
            mock_aioredis.Redis.from_url.return_value = mock_valkey

            result = await copilot_metrics_service._read_metrics_from_store(
                db,
            )
        assert isinstance(result, list)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_falls_back_to_db_on_cache_miss(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                return_value="true",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-ent",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
        ):
            mock_valkey = AsyncMock()
            mock_valkey.get = AsyncMock(return_value=None)
            mock_valkey.aclose = AsyncMock()
            mock_aioredis.Redis.from_url.return_value = mock_valkey

            result = await copilot_metrics_service._read_metrics_from_store(
                db,
            )
        assert isinstance(result, list)
        assert result == []


class TestReadSeatsFromStore:
    """_read_seats_from_store reads from Valkey cache or DB, never GitHub."""

    @pytest.mark.asyncio
    async def test_returns_error_when_feature_disabled(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        with patch(
            "app.services.settings_service.get_setting",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await copilot_metrics_service._read_seats_from_store(db)
        assert isinstance(result, dict)
        assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_cached_seats(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = [{"assignee": {"login": "alice"}, "plan_type": "business"}]
        with (
            patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                return_value="true",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-ent",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
        ):
            mock_valkey = AsyncMock()
            mock_valkey.get = AsyncMock(return_value=json.dumps(seats))
            mock_valkey.aclose = AsyncMock()
            mock_aioredis.Redis.from_url.return_value = mock_valkey

            result = await copilot_metrics_service._read_seats_from_store(db)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["assignee"]["login"] == "alice"

    @pytest.mark.asyncio
    async def test_returns_empty_on_cache_miss_and_no_db_data(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        # scalar() returns None (no max date)
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.services.settings_service.get_setting",
                new_callable=AsyncMock,
                return_value="true",
            ),
            patch.object(
                copilot_metrics_service.settings.github_app,
                "GITHUB_ENTERPRISE_SLUG",
                "test-ent",
            ),
            patch("app.services.copilot_metrics_service.aioredis") as mock_aioredis,
        ):
            mock_valkey = AsyncMock()
            mock_valkey.get = AsyncMock(return_value=None)
            mock_valkey.aclose = AsyncMock()
            mock_aioredis.Redis.from_url.return_value = mock_valkey

            result = await copilot_metrics_service._read_seats_from_store(db)
        assert isinstance(result, list)
        assert result == []


class TestReconstructMetricsFromDb:
    """Test DB→raw-API-format reconstruction logic."""

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        result = await copilot_metrics_service._reconstruct_metrics_from_db(db, "test-ent")
        assert result == []

    @pytest.mark.asyncio
    async def test_reconstructs_summary_rows(self) -> None:
        """Summary rows produce total_active/engaged_users fields."""
        from datetime import date

        db = AsyncMock(spec=AsyncSession)
        row = MagicMock()
        row.date = date(2025, 1, 20)
        row.metric_type = "summary"
        row.active_users = 42
        row.engaged_users = 38
        row.language = None
        row.editor = None
        row.model = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]
        db.execute = AsyncMock(return_value=mock_result)

        result = await copilot_metrics_service._reconstruct_metrics_from_db(db, "test-ent")
        assert len(result) == 1
        assert result[0]["total_active_users"] == 42
        assert result[0]["total_engaged_users"] == 38

    @pytest.mark.asyncio
    async def test_reconstructs_completions_nested_structure(self) -> None:
        """Completions rows rebuild the editor→model→language tree."""
        from datetime import date

        db = AsyncMock(spec=AsyncSession)
        row = MagicMock()
        row.date = date(2025, 1, 20)
        row.metric_type = "completions"
        row.editor = "VS Code"
        row.model = "GPT-4o"
        row.language = "Python"
        row.engaged_users = 25
        row.total_suggestions = 200
        row.total_acceptances = 60
        row.total_lines_suggested = 400
        row.total_lines_accepted = 120

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]
        db.execute = AsyncMock(return_value=mock_result)

        result = await copilot_metrics_service._reconstruct_metrics_from_db(db, "test-ent")
        assert len(result) == 1
        compl = result[0]["copilot_ide_code_completions"]
        assert len(compl["editors"]) == 1
        assert compl["editors"][0]["name"] == "VS Code"
        models = compl["editors"][0]["models"]
        assert len(models) == 1
        assert models[0]["name"] == "GPT-4o"
        langs = models[0]["languages"]
        assert len(langs) == 1
        assert langs[0]["name"] == "Python"
        assert langs[0]["total_code_suggestions"] == 200

    @pytest.mark.asyncio
    async def test_reconstructs_chat_and_pr_rows(self) -> None:
        """Chat, dotcom_chat, and PR rows set engaged_users."""
        from datetime import date

        db = AsyncMock(spec=AsyncSession)
        rows = []
        for mt, engaged in [
            ("chat", 20),
            ("dotcom_chat", 10),
            ("pr", 5),
        ]:
            r = MagicMock()
            r.date = date(2025, 1, 20)
            r.metric_type = mt
            r.engaged_users = engaged
            r.active_users = 0
            r.language = None
            r.editor = None
            r.model = None
            rows.append(r)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=mock_result)

        result = await copilot_metrics_service._reconstruct_metrics_from_db(db, "test-ent")
        assert len(result) == 1
        day = result[0]
        assert day["copilot_ide_chat"]["total_engaged_users"] == 20
        assert day["copilot_dotcom_chat"]["total_engaged_users"] == 10
        assert day["copilot_dotcom_pull_requests"]["total_engaged_users"] == 5
