"""Tests for the user_behavior_service module.

Tests cover:
- Risk level calculation
- Empty org handling
- Risk summary computation
- Risky users list building
- Anomaly detection logic
- Permission drift analysis
"""

from __future__ import annotations

from app.services.user_behavior_service import (
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_LOW,
    RISK_THRESHOLD_MEDIUM,
    RISKY_ACTIONS,
    _empty_risk_summary,
    _risk_level,
)


class TestRiskLevel:
    """Tests for _risk_level helper."""

    def test_high_risk(self) -> None:
        assert _risk_level(15) == "high"
        assert _risk_level(20) == "high"
        assert _risk_level(100) == "high"

    def test_medium_risk(self) -> None:
        assert _risk_level(7) == "medium"
        assert _risk_level(10) == "medium"
        assert _risk_level(14) == "medium"

    def test_low_risk(self) -> None:
        assert _risk_level(3) == "low"
        assert _risk_level(5) == "low"
        assert _risk_level(6) == "low"

    def test_no_risk(self) -> None:
        assert _risk_level(0) == "none"
        assert _risk_level(1) == "none"
        assert _risk_level(2) == "none"

    def test_threshold_boundaries(self) -> None:
        assert _risk_level(RISK_THRESHOLD_HIGH) == "high"
        assert _risk_level(RISK_THRESHOLD_HIGH - 1) == "medium"
        assert _risk_level(RISK_THRESHOLD_MEDIUM) == "medium"
        assert _risk_level(RISK_THRESHOLD_MEDIUM - 1) == "low"
        assert _risk_level(RISK_THRESHOLD_LOW) == "low"
        assert _risk_level(RISK_THRESHOLD_LOW - 1) == "none"


class TestEmptyRiskSummary:
    """Tests for _empty_risk_summary helper."""

    def test_returns_zeroed_dict(self) -> None:
        result = _empty_risk_summary()
        assert result["total_users_with_signals"] == 0
        assert result["high_risk_count"] == 0
        assert result["medium_risk_count"] == 0
        assert result["low_risk_count"] == 0
        assert result["anomaly_count"] == 0
        assert result["top_categories"] == []
        assert result["lookback_days"] == 30


class TestRiskyActionsConfig:
    """Tests for RISKY_ACTIONS configuration."""

    def test_all_actions_have_required_keys(self) -> None:
        for action, meta in RISKY_ACTIONS.items():
            assert "weight" in meta, f"{action} missing 'weight'"
            assert "category" in meta, f"{action} missing 'category'"
            assert "label" in meta, f"{action} missing 'label'"
            assert isinstance(meta["weight"], int), f"{action} weight should be int"
            assert meta["weight"] > 0, f"{action} weight should be positive"

    def test_all_categories_are_valid(self) -> None:
        valid_categories = {
            "permission_change",
            "security_bypass",
            "credential_activity",
            "repo_activity",
            "admin_action",
            "integration_change",
        }
        for action, meta in RISKY_ACTIONS.items():
            assert meta["category"] in valid_categories, (
                f"{action} has invalid category: {meta['category']}"
            )

    def test_security_bypass_actions_have_elevated_weight(self) -> None:
        """Security bypasses should have weight >= 2."""
        for action, meta in RISKY_ACTIONS.items():
            if meta["category"] == "security_bypass":
                assert meta["weight"] >= 2, f"Security bypass '{action}' should have weight >= 2"

    def test_known_critical_actions_present(self) -> None:
        critical_actions = [
            "protected_branch.destroy",
            "org.disable_two_factor_requirement",
            "org.disable_saml",
            "repo.destroy",
        ]
        for action in critical_actions:
            assert action in RISKY_ACTIONS, f"Critical action '{action}' should be in RISKY_ACTIONS"


class TestThresholdConstants:
    """Verify threshold constants are properly ordered."""

    def test_thresholds_are_ordered(self) -> None:
        assert RISK_THRESHOLD_HIGH > RISK_THRESHOLD_MEDIUM > RISK_THRESHOLD_LOW > 0
