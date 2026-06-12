"""Tests for the new Copilot Metrics Viewer chart service functions.

Covers:
- get_copilot_activity
- get_copilot_chat_metrics
- get_copilot_language_breakdown
- get_copilot_pr_metrics
- get_copilot_agent_activity
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import copilot_metrics_service

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_db_with_rows(*row_batches: list[Any]) -> AsyncMock:
    """Return an AsyncMock db that returns rows sequentially for each execute() call."""
    db = AsyncMock(spec=AsyncSession)
    results = []
    for rows in row_batches:
        mock_result = MagicMock()
        mock_result.all.return_value = rows
        mock_result.scalar_one_or_none.return_value = None
        results.append(mock_result)
    db.execute = AsyncMock(side_effect=results)
    return db


def _mock_db_empty() -> AsyncMock:
    """Return a DB mock where all queries return empty results."""
    db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _make_row(**kwargs: Any) -> MagicMock:
    """Create a mock row object with attribute access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    # Also support index access for Row-like objects
    row.__getitem__ = lambda self, idx: list(kwargs.values())[idx]
    return row


def _patch_enabled():
    """Patch _check_feature_enabled to return None (enabled)."""
    return patch.object(copilot_metrics_service, "_check_feature_enabled", return_value=None)


# ── Test: get_copilot_activity ────────────────────────────────────────────────


class TestGetCopilotActivity:
    @pytest.mark.asyncio
    async def test_returns_error_when_disabled(self) -> None:
        db = _mock_db_empty()
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value={"error": "feature_disabled", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_activity(db)
        assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_empty_with_no_data(self) -> None:
        db = _mock_db_empty()
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_activity(db)
        assert result["dates"] == []
        assert result["ide_dau"] == []
        assert result["completions_count"] == []
        assert result["requests_per_mode"]["dates"] == []

    @pytest.mark.asyncio
    async def test_returns_expected_shape(self) -> None:
        today = date.today()
        d1 = today - timedelta(days=2)
        d2 = today - timedelta(days=1)

        # summary rows (query 1)
        summary_rows = [
            _make_row(date=d1, active_users=100),
            _make_row(date=d2, active_users=120),
        ]
        # completions rows (query 2)
        comp_rows = [
            _make_row(date=d1, suggestions=500, acceptances=200),
            _make_row(date=d2, suggestions=600, acceptances=250),
        ]
        # chat rows (query 3)
        chat_rows = [
            _make_row(date=d1, chat_requests=400),
            _make_row(date=d2, chat_requests=480),
        ]
        # mode rows (query 4)
        mode_rows = [
            _make_row(date=d1, metric_type="completions", requests=500),
            _make_row(date=d1, metric_type="chat", requests=400),
            _make_row(date=d2, metric_type="completions", requests=600),
            _make_row(date=d2, metric_type="chat", requests=480),
        ]

        db = _mock_db_with_rows(summary_rows, comp_rows, chat_rows, mode_rows)
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_activity(db)

        assert len(result["dates"]) == 2
        assert result["ide_dau"] == [100, 120]
        assert result["completions_count"] == [500, 600]
        assert result["completions_accepted"] == [200, 250]
        assert result["acceptance_rate_pct"][0] == round(200 / 500 * 100, 1)
        assert result["chat_requests_per_user"][0] == round(400 / 100, 1)
        assert result["requests_per_mode"]["completions"] == [500, 600]
        assert result["requests_per_mode"]["chat"] == [400, 480]

    @pytest.mark.asyncio
    async def test_wau_is_rolling_sum(self) -> None:
        """WAU should be a 7-day rolling sum of DAU."""
        today = date.today()
        # Create 3 days of data
        days = [today - timedelta(days=i) for i in range(2, -1, -1)]
        summary_rows = [_make_row(date=d, active_users=100) for d in days]

        db = _mock_db_with_rows(summary_rows, [], [], [])
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_activity(db)

        # WAU for day 3 = sum of all 3 days = 300
        assert result["ide_wau"][2] == 300
        # WAU for day 1 = just day 1 = 100
        assert result["ide_wau"][0] == 100


# ── Test: get_copilot_chat_metrics ────────────────────────────────────────────


class TestGetCopilotChatMetrics:
    @pytest.mark.asyncio
    async def test_returns_error_when_disabled(self) -> None:
        db = _mock_db_empty()
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value={"error": "feature_disabled", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_chat_metrics(db)
        assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_empty_with_no_data(self) -> None:
        db = _mock_db_empty()
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_chat_metrics(db)
        assert result["dates"] == []
        assert result["total_interactions"] == []
        assert result["code_actions"] == []
        assert result["active_chat_users"] == []
        assert result["action_rate_pct"] == []

    @pytest.mark.asyncio
    async def test_returns_correct_values(self) -> None:
        today = date.today()
        d1 = today - timedelta(days=1)
        rows = [
            _make_row(date=d1, interactions=800, code_actions=200, active_users=95),
        ]
        db = _mock_db_with_rows(rows)
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_chat_metrics(db)

        assert result["dates"] == [d1.isoformat()]
        assert result["total_interactions"] == [800]
        assert result["code_actions"] == [200]
        assert result["active_chat_users"] == [95]
        assert result["action_rate_pct"] == [25.0]

    @pytest.mark.asyncio
    async def test_action_rate_zero_when_no_interactions(self) -> None:
        today = date.today()
        d1 = today - timedelta(days=1)
        rows = [
            _make_row(date=d1, interactions=0, code_actions=0, active_users=0),
        ]
        db = _mock_db_with_rows(rows)
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_chat_metrics(db)
        assert result["action_rate_pct"] == [0.0]


# ── Test: get_copilot_language_breakdown ──────────────────────────────────────


class TestGetCopilotLanguageBreakdown:
    @pytest.mark.asyncio
    async def test_returns_error_when_disabled(self) -> None:
        db = _mock_db_empty()
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value={"error": "feature_disabled", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_language_breakdown(db)
        assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_empty_with_no_data(self) -> None:
        db = _mock_db_empty()
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_language_breakdown(db)
        assert result["dates"] == []
        assert result["language_per_day"] == {}
        assert result["language_distribution"] == []
        assert result["model_per_language"] == {"labels": [], "series": []}
        assert result["acceptance_by_editor"] == []
        assert result["top_by_generations"] == []
        assert result["top_by_lines"] == []

    @pytest.mark.asyncio
    async def test_returns_language_data(self) -> None:
        today = date.today()
        d1 = today - timedelta(days=1)

        # Query 1: top languages
        top_langs = [
            _make_row(language="TypeScript", total=5000),
            _make_row(language="Python", total=3000),
        ]
        # Query 2: language per day
        lang_day = [
            _make_row(date=d1, language="TypeScript", suggestions=500),
            _make_row(date=d1, language="Python", suggestions=300),
        ]
        # Query 3: model per language
        model_lang = [
            _make_row(language="TypeScript", model="gpt-4o", suggestions=400),
            _make_row(language="Python", model="gpt-4o", suggestions=250),
        ]
        # Query 4: acceptance by editor
        editors = [
            _make_row(editor="VS Code", suggestions=1000, acceptances=380),
        ]
        # Query 5: top by lines
        lines = [
            _make_row(language="TypeScript", lines=20000),
            _make_row(language="Python", lines=15000),
        ]

        db = _mock_db_with_rows(top_langs, lang_day, model_lang, editors, lines)
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_language_breakdown(db)

        assert result["dates"] == [d1.isoformat()]
        assert "TypeScript" in result["language_per_day"]
        assert "Python" in result["language_per_day"]
        assert len(result["language_distribution"]) == 2
        assert result["language_distribution"][0]["name"] == "TypeScript"
        assert result["language_distribution"][0]["value"] == 5000
        assert "color" in result["language_distribution"][0]
        assert result["model_per_language"]["labels"] == ["TypeScript", "Python"]
        assert len(result["model_per_language"]["series"]) == 1
        assert result["model_per_language"]["series"][0]["name"] == "gpt-4o"
        assert result["acceptance_by_editor"][0]["editor"] == "VS Code"
        assert result["acceptance_by_editor"][0]["rate"] == 38.0
        assert result["top_by_generations"][0]["language"] == "TypeScript"
        assert result["top_by_generations"][0]["count"] == 5000
        assert result["top_by_lines"][0]["language"] == "TypeScript"
        assert result["top_by_lines"][0]["lines"] == 20000


# ── Test: get_copilot_pr_metrics ──────────────────────────────────────────────


class TestGetCopilotPrMetrics:
    @pytest.mark.asyncio
    async def test_returns_error_when_disabled(self) -> None:
        db = _mock_db_empty()
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value={"error": "feature_disabled", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_pr_metrics(db)
        assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_empty_with_no_data(self) -> None:
        db = _mock_db_empty()
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_pr_metrics(db)
        assert result["dates"] == []
        assert result["pr_activity"] == []
        assert result["pr_contributions"] == []
        assert result["review_suggestions"] == []

    @pytest.mark.asyncio
    async def test_returns_correct_values(self) -> None:
        today = date.today()
        d1 = today - timedelta(days=2)
        d2 = today - timedelta(days=1)
        rows = [
            _make_row(date=d1, active_users=10, contributions=50, review_suggestions=30),
            _make_row(date=d2, active_users=12, contributions=55, review_suggestions=35),
        ]
        db = _mock_db_with_rows(rows)
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_pr_metrics(db)

        assert result["dates"] == [d1.isoformat(), d2.isoformat()]
        assert result["pr_activity"] == [10, 12]
        assert result["pr_contributions"] == [50, 55]
        assert result["review_suggestions"] == [30, 35]


# ── Test: get_copilot_agent_activity ──────────────────────────────────────────


class TestGetCopilotAgentActivity:
    @pytest.mark.asyncio
    async def test_returns_error_when_disabled(self) -> None:
        db = _mock_db_empty()
        with patch.object(
            copilot_metrics_service,
            "_check_feature_enabled",
            return_value={"error": "feature_disabled", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_agent_activity(db)
        assert result["error"] == "feature_disabled"

    @pytest.mark.asyncio
    async def test_returns_empty_with_no_data(self) -> None:
        db = _mock_db_empty()
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_agent_activity(db)
        assert result["dates"] == []
        assert result["daily_lines_added"] == []
        assert result["daily_lines_accepted"] == []
        assert result["lines_by_mode"] == {"completions": [], "chat": [], "pr": []}
        assert result["lines_by_model"] == []
        assert result["lines_by_language"] == []

    @pytest.mark.asyncio
    async def test_returns_correct_values(self) -> None:
        today = date.today()
        d1 = today - timedelta(days=1)

        # Query 1: daily totals
        daily_rows = [
            _make_row(date=d1, lines_added=5000, lines_accepted=3000),
        ]
        # Query 2: lines by mode
        mode_rows = [
            _make_row(date=d1, metric_type="completions", lines=4000),
            _make_row(date=d1, metric_type="chat", lines=800),
            _make_row(date=d1, metric_type="pr", lines=200),
        ]
        # Query 3: lines by model
        model_rows = [
            _make_row(model="gpt-4o", lines_added=25000, lines_accepted=15000),
            _make_row(model="claude-3.5", lines_added=10000, lines_accepted=6000),
        ]
        # Query 4: lines by language
        lang_rows = [
            _make_row(language="TypeScript", lines_added=20000, lines_accepted=12000),
            _make_row(language="Python", lines_added=15000, lines_accepted=9000),
        ]

        db = _mock_db_with_rows(daily_rows, mode_rows, model_rows, lang_rows)
        with _patch_enabled():
            result = await copilot_metrics_service.get_copilot_agent_activity(db)

        assert result["dates"] == [d1.isoformat()]
        assert result["daily_lines_added"] == [5000]
        assert result["daily_lines_accepted"] == [3000]
        assert result["lines_by_mode"]["completions"] == [4000]
        assert result["lines_by_mode"]["chat"] == [800]
        assert result["lines_by_mode"]["pr"] == [200]
        assert result["lines_by_model"][0]["model"] == "gpt-4o"
        assert result["lines_by_model"][0]["lines_added"] == 25000
        assert result["lines_by_language"][0]["language"] == "TypeScript"
        assert result["lines_by_language"][0]["lines_accepted"] == 12000


# ── Test: Router endpoints ────────────────────────────────────────────────────


class TestCopilotViewerRouterAuth:
    """New copilot viewer endpoints must require authentication."""

    def _get_client(self) -> Any:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.deps import get_db, get_valkey
        from app.routers import copilot as copilot_router_module

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
        return TestClient(app)

    def test_activity_returns_401_unauthenticated(self) -> None:
        client = self._get_client()
        resp = client.get("/api/v1/copilot/activity")
        assert resp.status_code == 401

    def test_chat_metrics_returns_401_unauthenticated(self) -> None:
        client = self._get_client()
        resp = client.get("/api/v1/copilot/chat-metrics")
        assert resp.status_code == 401

    def test_language_breakdown_returns_401_unauthenticated(self) -> None:
        client = self._get_client()
        resp = client.get("/api/v1/copilot/language-breakdown")
        assert resp.status_code == 401

    def test_pr_metrics_returns_401_unauthenticated(self) -> None:
        client = self._get_client()
        resp = client.get("/api/v1/copilot/pr-metrics")
        assert resp.status_code == 401

    def test_agent_activity_returns_401_unauthenticated(self) -> None:
        client = self._get_client()
        resp = client.get("/api/v1/copilot/agent-activity")
        assert resp.status_code == 401
