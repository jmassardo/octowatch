"""Tests for Copilot session anomaly detection rules (#387, #509).

Covers:
- Tool-call-volume anomaly rule (trigger + non-trigger, baseline + cold-start)
- Session-duration anomaly rule (trigger + non-trigger, baseline + cold-start)
- Rule fixture validity and seeding
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.detection import RuleDefinition
from app.services.detection_service import (
    evaluate_copilot_session_duration_anomaly,
    evaluate_copilot_tool_call_volume,
    seed_copilot_session_rules,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "fixtures" / "copilot_session_rules.json"
)


def _make_copilot_session(
    *,
    session_id: str = "session-1",
    actor: str = "testuser",
    org: str = "my-org",
    repository: str = "my-org/hello-world",
    tool_call_count: int | None = 5,
    duration_seconds: int | None = 300,
    created_at: datetime | None = None,
) -> MagicMock:
    """Create a mock CopilotSession with specified attributes."""
    cs = MagicMock()
    cs.session_id = session_id
    cs.actor = actor
    cs.org = org
    cs.repository = repository
    cs.tool_call_count = tool_call_count
    cs.duration_seconds = duration_seconds
    cs.created_at = created_at or datetime.now(UTC)
    return cs


def _make_rule(
    *,
    rule_id: int = 1,
    slug: str = "test-copilot-rule",
    engine: str = "copilot_tool_call_volume",
    z_multiplier: float = 3.0,
    fallback_threshold: int = 20,
    default_severity: str = "medium",
    version: int = 1,
) -> MagicMock:
    """Create a mock RuleDefinition configured for a Copilot session engine."""
    rule = MagicMock(spec=RuleDefinition)
    rule.id = rule_id
    rule.slug = slug
    rule.logic_type = "statistical"
    rule.logic_config = {
        "x_config": {
            "engine": engine,
            "z_multiplier": z_multiplier,
            "fallback_threshold": fallback_threshold,
        },
        "time_window_minutes": 60,
        "confidence": 0.55,
    }
    rule.default_severity = default_severity
    rule.default_confidence = "medium"
    rule.version = version
    return rule


def _make_baseline(*, mean: float, stddev: float) -> MagicMock:
    baseline = MagicMock()
    baseline.baseline_type = "actor"
    baseline.scope_key = "actor:testuser:org:my-org"
    baseline.mean = mean
    baseline.stddev = stddev
    return baseline


# ═══════════════════════════════════════════════════════════════════════════
# Tool-call volume anomaly
# ═══════════════════════════════════════════════════════════════════════════


class TestCopilotToolCallVolumeAnomaly:
    @pytest.mark.asyncio
    async def test_flags_session_above_baseline(self) -> None:
        """A session well above the actor's baseline mean+z*stddev should trigger."""
        session = AsyncMock()
        baseline = _make_baseline(mean=5.0, stddev=2.0)

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=baseline,
        ):
            rule = _make_rule(z_multiplier=3.0)
            cs = _make_copilot_session(tool_call_count=50)
            results = await evaluate_copilot_tool_call_volume(session, rule, [cs])

        assert len(results) == 1
        ctx = results[0]["context_data"]
        assert ctx["tool_call_count"] == 50
        assert ctx["z_score"] > 3.0
        assert results[0]["aggregation_key_value"] == "testuser"

    @pytest.mark.asyncio
    async def test_does_not_flag_session_within_baseline(self) -> None:
        """A session close to the actor's baseline mean should not trigger."""
        session = AsyncMock()
        baseline = _make_baseline(mean=5.0, stddev=2.0)

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=baseline,
        ):
            rule = _make_rule(z_multiplier=3.0)
            cs = _make_copilot_session(tool_call_count=6)
            results = await evaluate_copilot_tool_call_volume(session, rule, [cs])

        assert results == []

    @pytest.mark.asyncio
    async def test_cold_start_uses_fallback_threshold(self) -> None:
        """With no baseline at all, falls back to the fixed threshold."""
        session = AsyncMock()

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=None,
        ):
            rule = _make_rule(fallback_threshold=20)
            above = _make_copilot_session(tool_call_count=25)
            below = _make_copilot_session(tool_call_count=10)
            results = await evaluate_copilot_tool_call_volume(session, rule, [above, below])

        assert len(results) == 1
        assert results[0]["context_data"]["tool_call_count"] == 25
        assert results[0]["context_data"]["baseline_type"] == "fixed_threshold"

    @pytest.mark.asyncio
    async def test_sessions_with_no_tool_call_count_are_skipped(self) -> None:
        session = AsyncMock()
        with patch(
            "app.services.detection_service._load_baseline",
            return_value=None,
        ):
            rule = _make_rule()
            cs = _make_copilot_session(tool_call_count=None)
            results = await evaluate_copilot_tool_call_volume(session, rule, [cs])
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════
# Session duration anomaly
# ═══════════════════════════════════════════════════════════════════════════


class TestCopilotSessionDurationAnomaly:
    @pytest.mark.asyncio
    async def test_flags_session_far_above_baseline(self) -> None:
        session = AsyncMock()
        baseline = _make_baseline(mean=300.0, stddev=60.0)

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=baseline,
        ):
            rule = _make_rule(engine="copilot_session_duration_anomaly", z_multiplier=3.0)
            cs = _make_copilot_session(duration_seconds=5000)
            results = await evaluate_copilot_session_duration_anomaly(session, rule, [cs])

        assert len(results) == 1
        ctx = results[0]["context_data"]
        assert ctx["duration_seconds"] == 5000
        assert ctx["z_score"] > 3.0

    @pytest.mark.asyncio
    async def test_flags_session_far_below_baseline(self) -> None:
        """Unusually short sessions should also trigger (not just long ones)."""
        session = AsyncMock()
        baseline = _make_baseline(mean=300.0, stddev=60.0)

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=baseline,
        ):
            rule = _make_rule(engine="copilot_session_duration_anomaly", z_multiplier=3.0)
            cs = _make_copilot_session(duration_seconds=5)
            results = await evaluate_copilot_session_duration_anomaly(session, rule, [cs])

        assert len(results) == 1
        assert results[0]["context_data"]["duration_seconds"] == 5

    @pytest.mark.asyncio
    async def test_does_not_flag_session_within_baseline(self) -> None:
        session = AsyncMock()
        baseline = _make_baseline(mean=300.0, stddev=60.0)

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=baseline,
        ):
            rule = _make_rule(engine="copilot_session_duration_anomaly", z_multiplier=3.0)
            cs = _make_copilot_session(duration_seconds=310)
            results = await evaluate_copilot_session_duration_anomaly(session, rule, [cs])

        assert results == []

    @pytest.mark.asyncio
    async def test_cold_start_uses_fallback_threshold(self) -> None:
        session = AsyncMock()

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=None,
        ):
            rule = _make_rule(engine="copilot_session_duration_anomaly", fallback_threshold=3600)
            above = _make_copilot_session(duration_seconds=7200)
            below = _make_copilot_session(duration_seconds=300)
            results = await evaluate_copilot_session_duration_anomaly(session, rule, [above, below])

        assert len(results) == 1
        assert results[0]["context_data"]["duration_seconds"] == 7200
        assert results[0]["context_data"]["baseline_type"] == "fixed_threshold"


# ═══════════════════════════════════════════════════════════════════════════
# Fixture validity and seeding
# ═══════════════════════════════════════════════════════════════════════════


class TestCopilotSessionRuleFixtures:
    def _load_fixtures(self) -> list[dict[str, Any]]:
        with open(_FIXTURE_PATH) as f:
            data: list[dict[str, Any]] = json.load(f)
            return data

    def test_fixture_file_exists(self) -> None:
        assert _FIXTURE_PATH.exists(), f"Not found: {_FIXTURE_PATH}"

    def test_fixture_is_valid_json_with_two_rules(self) -> None:
        rules = self._load_fixtures()
        assert isinstance(rules, list)
        assert len(rules) == 2

    def test_fixture_rules_have_required_fields(self) -> None:
        required_fields = {
            "name",
            "slug",
            "description",
            "category",
            "default_severity",
            "default_confidence",
            "logic_type",
            "logic_config",
            "created_by",
        }
        for rule in self._load_fixtures():
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule '{rule.get('name')}' missing fields: {missing}"

    def test_fixture_slugs_unique(self) -> None:
        rules = self._load_fixtures()
        slugs = [r["slug"] for r in rules]
        assert len(slugs) == len(set(slugs))

    def test_fixture_engines_match_dispatch_set(self) -> None:
        from app.services.detection_service import _COPILOT_SESSION_ENGINES

        rules = self._load_fixtures()
        engines = {r["logic_config"]["x_config"]["engine"] for r in rules}
        assert engines == set(_COPILOT_SESSION_ENGINES)


class TestSeedCopilotSessionRules:
    @pytest.mark.asyncio
    async def test_seeds_both_rules_when_absent(self) -> None:
        session = AsyncMock()
        existing_result = MagicMock()
        existing_result.scalar.return_value = None
        session.execute.return_value = existing_result

        created = await seed_copilot_session_rules(session)

        assert created == 2
        assert session.add.call_count == 2
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_rules_that_already_exist(self) -> None:
        session = AsyncMock()
        existing_result = MagicMock()
        existing_result.scalar.return_value = 1  # every slug "already exists"
        session.execute.return_value = existing_result

        created = await seed_copilot_session_rules(session)

        assert created == 0
        session.add.assert_not_called()
        session.flush.assert_not_awaited()
