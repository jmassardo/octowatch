"""Unit tests for the aggregate evaluation engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.aggregate_evaluation import (
    _evaluate_condition,
    _safe_column_name,
    evaluate_classification_rules,
    evaluate_composite_risk,
    evaluate_iqr_anomaly,
)

# ─── _evaluate_condition tests ────────────────────────────────────────────────


class TestEvaluateCondition:
    """Tests for the _evaluate_condition helper."""

    def test_gte_true(self) -> None:
        metrics = {"code_events": 100, "total_events": 200}
        assert _evaluate_condition(metrics, {"field": "code_events", "op": "gte", "value": 100})

    def test_gte_false(self) -> None:
        metrics = {"code_events": 50, "total_events": 200}
        assert not _evaluate_condition(metrics, {"field": "code_events", "op": "gte", "value": 100})

    def test_gt_true(self) -> None:
        metrics = {"code_events": 101, "total_events": 200}
        assert _evaluate_condition(metrics, {"field": "code_events", "op": "gt", "value": 100})

    def test_gt_false_on_equal(self) -> None:
        metrics = {"code_events": 100, "total_events": 200}
        assert not _evaluate_condition(metrics, {"field": "code_events", "op": "gt", "value": 100})

    def test_lte_true(self) -> None:
        metrics = {"code_events": 50, "total_events": 200}
        assert _evaluate_condition(metrics, {"field": "code_events", "op": "lte", "value": 50})

    def test_lte_false(self) -> None:
        metrics = {"code_events": 51, "total_events": 200}
        assert not _evaluate_condition(metrics, {"field": "code_events", "op": "lte", "value": 50})

    def test_lt_true(self) -> None:
        metrics = {"code_events": 49, "total_events": 200}
        assert _evaluate_condition(metrics, {"field": "code_events", "op": "lt", "value": 50})

    def test_lt_false_on_equal(self) -> None:
        metrics = {"code_events": 50, "total_events": 200}
        assert not _evaluate_condition(metrics, {"field": "code_events", "op": "lt", "value": 50})

    def test_eq_true(self) -> None:
        metrics = {"actor_is_bot": True, "total_events": 10}
        assert _evaluate_condition(metrics, {"field": "actor_is_bot", "op": "eq", "value": True})

    def test_eq_false(self) -> None:
        metrics = {"actor_is_bot": False, "total_events": 10}
        assert not _evaluate_condition(
            metrics, {"field": "actor_is_bot", "op": "eq", "value": True}
        )

    def test_pct_gt_true(self) -> None:
        # code_events=80 out of total_events=100 → 80%, threshold 50%
        metrics = {"code_events": 80, "total_events": 100}
        assert _evaluate_condition(metrics, {"field": "code_events", "op": "pct_gt", "value": 50})

    def test_pct_gt_false(self) -> None:
        # code_events=30 out of total_events=100 → 30%, threshold 50%
        metrics = {"code_events": 30, "total_events": 100}
        assert not _evaluate_condition(
            metrics, {"field": "code_events", "op": "pct_gt", "value": 50}
        )

    def test_pct_gt_zero_total(self) -> None:
        metrics = {"code_events": 5, "total_events": 0}
        assert not _evaluate_condition(
            metrics, {"field": "code_events", "op": "pct_gt", "value": 10}
        )

    def test_missing_field_returns_false(self) -> None:
        metrics = {"total_events": 100}
        assert not _evaluate_condition(metrics, {"field": "code_events", "op": "gte", "value": 10})

    def test_unknown_op_returns_false(self) -> None:
        metrics = {"code_events": 50, "total_events": 100}
        assert not _evaluate_condition(
            metrics, {"field": "code_events", "op": "invalid_op", "value": 10}
        )


# ─── evaluate_classification_rules tests ─────────────────────────────────────


class TestEvaluateClassificationRules:
    """Tests for the classification rule evaluation engine."""

    def test_first_match_wins_by_priority(self) -> None:
        rules = [
            {
                "priority": 2,
                "conditions": [{"field": "admin_events", "op": "gte", "value": 50}],
                "output_persona": "Admin",
                "confidence": 0.9,
            },
            {
                "priority": 1,
                "conditions": [{"field": "code_events", "op": "pct_gt", "value": 60}],
                "output_persona": "Developer",
                "confidence": 0.85,
            },
        ]
        metrics = {"code_events": 80, "admin_events": 100, "total_events": 120}
        persona, confidence = evaluate_classification_rules(metrics, rules)
        # Priority 1 rule (Developer) is evaluated first and matches
        assert persona == "Developer"
        assert confidence == 0.85

    def test_second_rule_matches_when_first_does_not(self) -> None:
        rules = [
            {
                "priority": 1,
                "conditions": [{"field": "admin_events", "op": "gte", "value": 200}],
                "output_persona": "Admin",
                "confidence": 0.9,
            },
            {
                "priority": 2,
                "conditions": [{"field": "code_events", "op": "gte", "value": 10}],
                "output_persona": "Developer",
                "confidence": 0.8,
            },
        ]
        metrics = {"code_events": 50, "admin_events": 5, "total_events": 55}
        persona, confidence = evaluate_classification_rules(metrics, rules)
        assert persona == "Developer"
        assert confidence == 0.8

    def test_fallback_when_no_rules_match(self) -> None:
        rules = [
            {
                "priority": 1,
                "conditions": [{"field": "admin_events", "op": "gte", "value": 999}],
                "output_persona": "Admin",
                "confidence": 0.9,
            },
        ]
        metrics = {"code_events": 10, "admin_events": 5, "total_events": 15}
        persona, confidence = evaluate_classification_rules(metrics, rules)
        assert persona == "Viewer"
        assert confidence == 0.5

    def test_fallback_with_empty_rules(self) -> None:
        persona, confidence = evaluate_classification_rules({"total_events": 10}, [])
        assert persona == "Viewer"
        assert confidence == 0.5

    def test_multiple_conditions_and_logic(self) -> None:
        rules = [
            {
                "priority": 1,
                "conditions": [
                    {"field": "admin_events", "op": "gte", "value": 50},
                    {"field": "total_events", "op": "gte", "value": 100},
                ],
                "output_persona": "Admin",
                "confidence": 0.95,
            },
        ]
        # Only one condition met → no match
        metrics = {"admin_events": 60, "total_events": 80, "code_events": 20}
        persona, confidence = evaluate_classification_rules(metrics, rules)
        assert persona == "Viewer"

        # Both conditions met → match
        metrics2 = {"admin_events": 60, "total_events": 150, "code_events": 90}
        persona2, confidence2 = evaluate_classification_rules(metrics2, rules)
        assert persona2 == "Admin"
        assert confidence2 == 0.95

    def test_legacy_single_condition_format(self) -> None:
        rules = [
            {
                "priority": 1,
                "condition": {"field": "actor_is_bot", "op": "eq", "value": True},
                "output_persona": "Bot",
                "confidence": 0.99,
            },
        ]
        metrics = {"actor_is_bot": True, "total_events": 500}
        persona, confidence = evaluate_classification_rules(metrics, rules)
        assert persona == "Bot"
        assert confidence == 0.99


# ─── evaluate_iqr_anomaly tests ──────────────────────────────────────────────


class TestEvaluateIqrAnomaly:
    """Tests for the IQR-based anomaly detection."""

    @pytest.mark.asyncio
    async def test_no_baseline_returns_none(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        # First query (baseline) returns no rows
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None
        db.execute.return_value = mock_result

        rule = {
            "slug": "copilot-overuse",
            "id": 1,
            "logic_config": {"metric_field": "copilot_suggestions", "multiplier": 3.0},
            "default_severity": "medium",
            "default_confidence": "medium",
        }
        result = await evaluate_iqr_anomaly(db, rule, "user1", "my-org")
        assert result is None

    @pytest.mark.asyncio
    async def test_insufficient_baseline_days_returns_none(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        now = datetime.now(tz=UTC)
        # Baseline with only 5 days of history
        baseline_row = {
            "p25": 10.0,
            "p75": 50.0,
            "mean": 30.0,
            "stddev": 15.0,
            "sample_count": 5,
            "window_start": now - timedelta(days=5),
            "window_end": now,
        }
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = baseline_row
        db.execute.return_value = mock_result

        rule = {
            "slug": "copilot-overuse",
            "id": 1,
            "logic_config": {
                "metric_field": "copilot_suggestions",
                "multiplier": 3.0,
                "min_baseline_days": 14,
            },
            "default_severity": "medium",
            "default_confidence": "medium",
        }
        result = await evaluate_iqr_anomaly(db, rule, "user1", "my-org")
        assert result is None

    @pytest.mark.asyncio
    async def test_normal_value_returns_none(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        now = datetime.now(tz=UTC)

        baseline_row = {
            "p25": 10.0,
            "p75": 50.0,
            "mean": 30.0,
            "stddev": 15.0,
            "sample_count": 30,
            "window_start": now - timedelta(days=30),
            "window_end": now,
        }
        # IQR = 40, threshold = 50 + 3*40 = 170
        current_row = {"current_value": 100.0, "metric_date": now.date()}

        mock_baseline_result = MagicMock()
        mock_baseline_result.mappings.return_value.first.return_value = baseline_row
        mock_current_result = MagicMock()
        mock_current_result.mappings.return_value.first.return_value = current_row

        db.execute.side_effect = [mock_baseline_result, mock_current_result]

        rule = {
            "slug": "copilot-overuse",
            "id": 1,
            "logic_config": {
                "metric_field": "copilot_suggestions",
                "multiplier": 3.0,
                "min_baseline_days": 14,
            },
            "default_severity": "medium",
            "default_confidence": "medium",
        }
        result = await evaluate_iqr_anomaly(db, rule, "user1", "my-org")
        assert result is None

    @pytest.mark.asyncio
    async def test_anomalous_value_returns_detection(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        now = datetime.now(tz=UTC)

        baseline_row = {
            "p25": 10.0,
            "p75": 50.0,
            "mean": 30.0,
            "stddev": 15.0,
            "sample_count": 30,
            "window_start": now - timedelta(days=30),
            "window_end": now,
        }
        # IQR = 40, threshold = 50 + 3*40 = 170
        current_row = {"current_value": 200.0, "metric_date": now.date()}

        mock_baseline_result = MagicMock()
        mock_baseline_result.mappings.return_value.first.return_value = baseline_row
        mock_current_result = MagicMock()
        mock_current_result.mappings.return_value.first.return_value = current_row

        db.execute.side_effect = [mock_baseline_result, mock_current_result]

        rule = {
            "slug": "copilot-overuse",
            "id": 1,
            "logic_config": {
                "metric_field": "copilot_suggestions",
                "multiplier": 3.0,
                "min_baseline_days": 14,
            },
            "default_severity": "high",
            "default_confidence": "high",
        }
        result = await evaluate_iqr_anomaly(db, rule, "user1", "my-org")
        assert result is not None
        assert result["rule_slug"] == "copilot-overuse"
        assert result["actor_login"] == "user1"
        assert result["org_slug"] == "my-org"
        assert result["current_value"] == 200.0
        assert result["threshold"] == 170.0
        assert result["severity"] == "high"


# ─── evaluate_composite_risk tests ───────────────────────────────────────────


class TestEvaluateCompositeRisk:
    """Tests for the composite risk scoring function."""

    def test_empty_triggered_returns_zero(self) -> None:
        rule = {
            "logic_config": {
                "contributing_rules": ["rule-a", "rule-b"],
                "weights": {"iqr_anomaly": 1.0},
                "recency_decay_days": 30,
            }
        }
        score = evaluate_composite_risk([], rule)
        assert score == 0.0

    def test_no_matching_slugs_returns_zero(self) -> None:
        rule = {
            "logic_config": {
                "contributing_rules": ["rule-a"],
                "weights": {"iqr_anomaly": 1.0},
                "recency_decay_days": 30,
            }
        }
        triggered = [
            {
                "rule_slug": "rule-b",
                "logic_type": "iqr_anomaly",
                "severity": "high",
                "triggered_at": datetime.now(tz=UTC),
            }
        ]
        score = evaluate_composite_risk(triggered, rule)
        assert score == 0.0

    def test_single_recent_high_severity(self) -> None:
        rule = {
            "logic_config": {
                "contributing_rules": ["rule-a"],
                "weights": {"iqr_anomaly": 1.0},
                "recency_decay_days": 30,
            }
        }
        triggered = [
            {
                "rule_slug": "rule-a",
                "logic_type": "iqr_anomaly",
                "severity": "high",
                "triggered_at": datetime.now(tz=UTC),
            }
        ]
        score = evaluate_composite_risk(triggered, rule)
        # high severity = 0.8, weight 1.0, decay ~1.0 (just triggered)
        assert 0.75 <= score <= 0.85

    def test_recency_decay_reduces_score(self) -> None:
        rule = {
            "logic_config": {
                "contributing_rules": ["rule-a"],
                "weights": {"iqr_anomaly": 1.0},
                "recency_decay_days": 7,
            }
        }
        # Triggered 14 days ago (2 half-lives)
        old_time = datetime.now(tz=UTC) - timedelta(days=14)
        triggered = [
            {
                "rule_slug": "rule-a",
                "logic_type": "iqr_anomaly",
                "severity": "high",
                "triggered_at": old_time,
            }
        ]
        score = evaluate_composite_risk(triggered, rule)
        # 2 half-lives → decay = 0.25, high severity = 0.8 → score ≈ 0.2
        assert score < 0.3

    def test_multiple_rules_averaged(self) -> None:
        rule = {
            "logic_config": {
                "contributing_rules": ["rule-a", "rule-b"],
                "weights": {"iqr_anomaly": 2.0, "threshold": 1.0},
                "recency_decay_days": 30,
            }
        }
        now = datetime.now(tz=UTC)
        triggered = [
            {
                "rule_slug": "rule-a",
                "logic_type": "iqr_anomaly",
                "severity": "critical",
                "triggered_at": now,
            },
            {
                "rule_slug": "rule-b",
                "logic_type": "threshold",
                "severity": "low",
                "triggered_at": now,
            },
        ]
        score = evaluate_composite_risk(triggered, rule)
        # critical=1.0 * weight=2.0 + low=0.25 * weight=1.0 = 2.25
        # total_weight = 3.0 → raw = 0.75
        assert 0.7 <= score <= 0.8

    def test_score_clamped_to_one(self) -> None:
        rule = {
            "logic_config": {
                "contributing_rules": ["rule-a"],
                "weights": {"iqr_anomaly": 10.0},
                "recency_decay_days": 30,
            }
        }
        triggered = [
            {
                "rule_slug": "rule-a",
                "logic_type": "iqr_anomaly",
                "severity": "critical",
                "triggered_at": datetime.now(tz=UTC),
            }
        ]
        score = evaluate_composite_risk(triggered, rule)
        assert score <= 1.0


# ─── _safe_column_name tests ─────────────────────────────────────────────────


class TestSafeColumnName:
    """Tests for the SQL injection prevention helper."""

    def test_valid_column(self) -> None:
        assert _safe_column_name("copilot_suggestions") == "copilot_suggestions"
        assert _safe_column_name("git_pushes") == "git_pushes"

    def test_invalid_column_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid metric field"):
            _safe_column_name("DROP TABLE users;--")

    def test_all_allowed_columns(self) -> None:
        allowed = [
            "actions_minutes",
            "actions_runs",
            "copilot_suggestions",
            "copilot_acceptances",
            "copilot_credits",
            "ghas_alerts_dismissed",
            "git_clones",
            "git_pushes",
            "packages_published",
            "storage_bytes",
        ]
        for col in allowed:
            assert _safe_column_name(col) == col
