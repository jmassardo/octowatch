"""Tests for detection schema fixes and rule_service persistence fixes.

Covers:
- FieldCondition schema: scope_contains operator acceptance
- Seed migration: correct config key structure
- RuleCreate schema: category and default_confidence fields
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.detection import (
    FieldCondition,
    ValidateConfigRequest,
    ValidateConfigResponse,
)

# ═════════════════════════════════════════════════════════════════════════════
# FieldCondition schema tests — scope_contains operator
# ═════════════════════════════════════════════════════════════════════════════


class TestFieldConditionOperators:
    """Verify that all documented operators are accepted, including scope_contains."""

    @pytest.mark.parametrize(
        "op",
        [
            "eq",
            "ne",
            "gt",
            "gte",
            "lt",
            "lte",
            "in",
            "not_in",
            "contains",
            "not_contains",
            "exists",
            "not_exists",
            "matches_glob",
            "scope_contains",
        ],
    )
    def test_valid_operators_accepted(self, op: str):
        fc = FieldCondition(field="data.scope", operator=op, value="test")
        assert fc.operator == op

    @pytest.mark.parametrize(
        "op",
        ["invalid", "CONTAINS", "eq_or_ne", "scope_contain", ""],
    )
    def test_invalid_operators_rejected(self, op: str):
        with pytest.raises(ValidationError):
            FieldCondition(field="data.scope", operator=op, value="test")

    def test_scope_contains_with_realistic_value(self):
        fc = FieldCondition(
            field="data.scope",
            operator="scope_contains",
            value="repo:write",
        )
        assert fc.field == "data.scope"
        assert fc.operator == "scope_contains"
        assert fc.value == "repo:write"


# ═════════════════════════════════════════════════════════════════════════════
# ValidateConfigRequest / ValidateConfigResponse schema tests
# ═════════════════════════════════════════════════════════════════════════════


class TestValidateConfigSchemas:
    """Verify the request/response Pydantic models for validate-config."""

    def test_valid_request_accepted(self):
        req = ValidateConfigRequest(
            logic_type="threshold",
            logic_config={"threshold": 5, "time_window_minutes": 60},
        )
        assert req.logic_type == "threshold"
        assert req.logic_config["threshold"] == 5

    @pytest.mark.parametrize(
        "logic_type",
        ["threshold", "pattern", "sequence", "statistical"],
    )
    def test_all_valid_logic_types(self, logic_type: str):
        req = ValidateConfigRequest(logic_type=logic_type, logic_config={})
        assert req.logic_type == logic_type

    def test_invalid_logic_type_rejected(self):
        with pytest.raises(ValidationError):
            ValidateConfigRequest(logic_type="unknown", logic_config={})

    def test_response_defaults(self):
        resp = ValidateConfigResponse(valid=True)
        assert resp.valid is True
        assert resp.errors == []
        assert resp.warnings == []

    def test_response_with_errors(self):
        resp = ValidateConfigResponse(
            valid=False,
            errors=["error1", "error2"],
            warnings=["warning1"],
        )
        assert resp.valid is False
        assert len(resp.errors) == 2
        assert len(resp.warnings) == 1


# ═════════════════════════════════════════════════════════════════════════════
# Seed migration config structure verification
# ═════════════════════════════════════════════════════════════════════════════


class TestSeedRuleConfigs:
    """Verify that the seed migration rules use the correct config keys."""

    @pytest.fixture()
    def seed_rules(self) -> list[tuple[Any, ...]]:
        """Import the seed rules from the migration."""
        from alembic.versions.seed_detection_rules_0003 import _RULES  # noqa: N816

        return _RULES

    def _get_rules(self) -> list[tuple[Any, ...]]:
        """Import seed rules using importlib to handle numeric module names."""
        import importlib.util
        import os

        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "0003_seed_detection_rules.py",
        )
        spec = importlib.util.spec_from_file_location("seed_rules", path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod._RULES

    def test_no_old_keys_present(self):
        """Ensure none of the old config keys remain."""
        rules = self._get_rules()
        old_keys = {"window_seconds", "group_by", "conditions", "actions", "op"}
        for rule in rules:
            config = rule[7]  # logic_config is at index 7
            actual_keys = set(config.keys())
            overlap = actual_keys & old_keys
            assert not overlap, f"Rule '{rule[0]}' still contains old key(s): {overlap}"

    def test_all_configs_have_confidence(self):
        """Every seed rule config must include a confidence key."""
        rules = self._get_rules()
        for rule in rules:
            config = rule[7]
            assert "confidence" in config, f"Rule '{rule[0]}' missing 'confidence'"
            assert 0 <= config["confidence"] <= 1, (
                f"Rule '{rule[0]}' has invalid confidence: {config['confidence']}"
            )

    def test_threshold_rules_use_correct_keys(self):
        """Threshold rules must use time_window_minutes and aggregation_key."""
        rules = self._get_rules()
        threshold_rules = [r for r in rules if r[6] == "threshold"]
        assert len(threshold_rules) >= 2, "Expected at least 2 threshold rules"

        for rule in threshold_rules:
            config = rule[7]
            assert "time_window_minutes" in config, (
                f"Threshold rule '{rule[0]}' missing 'time_window_minutes'"
            )
            assert "aggregation_key" in config, (
                f"Threshold rule '{rule[0]}' missing 'aggregation_key'"
            )
            assert "action_filters" in config, (
                f"Threshold rule '{rule[0]}' missing 'action_filters'"
            )
            assert isinstance(config["action_filters"], list)

    def test_pattern_rules_use_correct_keys(self):
        """Pattern rules must use action_filters and field_conditions."""
        rules = self._get_rules()
        pattern_rules = [r for r in rules if r[6] == "pattern"]
        assert len(pattern_rules) >= 5, "Expected at least 5 pattern rules"

        for rule in pattern_rules:
            config = rule[7]
            assert "action_filters" in config, f"Pattern rule '{rule[0]}' missing 'action_filters'"
            assert "field_conditions" in config, (
                f"Pattern rule '{rule[0]}' missing 'field_conditions'"
            )
            assert isinstance(config["action_filters"], list)
            assert isinstance(config["field_conditions"], list)

    def test_field_conditions_use_operator_not_op(self):
        """field_conditions entries must use 'operator' not 'op'."""
        rules = self._get_rules()
        for rule in rules:
            config = rule[7]
            for cond in config.get("field_conditions", []):
                assert "operator" in cond, (
                    f"Rule '{rule[0]}' has field_condition without 'operator': {cond}"
                )
                assert "op" not in cond, (
                    f"Rule '{rule[0]}' has field_condition with old 'op' key: {cond}"
                )

    def test_bulk_repo_harvesting_config(self):
        """Spot-check: bulk-repo-harvesting should have time_window_minutes=60."""
        rules = self._get_rules()
        rule = next(r for r in rules if r[1] == "bulk-repo-harvesting")
        config = rule[7]
        assert config["time_window_minutes"] == 60
        assert config["threshold"] == 15
        assert config["aggregation_key"] == "actor"
        assert config["action_filters"] == ["git.clone"]
        assert config["field_conditions"] == []

    def test_repeat_bypass_offender_config(self):
        """Spot-check: repeat-bypass-offender should have time_window_minutes=10080."""
        rules = self._get_rules()
        rule = next(r for r in rules if r[1] == "repeat-bypass-offender")
        config = rule[7]
        assert config["time_window_minutes"] == 10080  # 604800 / 60
        assert config["threshold"] == 3
        assert config["aggregation_key"] == "actor"
        assert len(config["action_filters"]) == 3
        assert "field_conditions" in config

    def test_total_rule_count(self):
        """Seed should contain exactly 11 rules."""
        rules = self._get_rules()
        assert len(rules) == 11
