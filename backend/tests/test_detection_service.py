"""Unit tests for the detection service: confidence scoring, field conditions,
suppression checks, and the core pipeline logic."""

from __future__ import annotations

from app.services.detection_service import (
    compute_confidence_score,
    evaluate_field_condition,
)

# ─── Confidence scoring ───────────────────────────────────────────────────────


class TestComputeConfidenceScore:
    def test_base_score_returns_clamped_value(self):
        score, tier = compute_confidence_score(0.5)
        assert 0.0 <= score <= 1.0
        assert tier == "medium"

    def test_high_count_boosts_confidence(self):
        score_base, _ = compute_confidence_score(0.6)
        score_boosted, _ = compute_confidence_score(0.6, observed_count=20, threshold=5)
        assert score_boosted > score_base

    def test_proxy_boosts_confidence(self):
        score_no_proxy, _ = compute_confidence_score(0.6)
        score_proxy, _ = compute_confidence_score(0.6, is_proxy=True)
        assert score_proxy > score_no_proxy

    def test_service_account_lowers_confidence(self):
        score_normal, _ = compute_confidence_score(0.6)
        score_sa, _ = compute_confidence_score(0.6, is_service_account=True)
        assert score_sa < score_normal

    def test_cold_start_lowers_confidence(self):
        score_normal, _ = compute_confidence_score(0.6)
        score_cold, _ = compute_confidence_score(0.6, is_cold_start=True)
        assert score_cold < score_normal

    def test_vpn_lowers_confidence(self):
        score_normal, _ = compute_confidence_score(0.6)
        score_vpn, _ = compute_confidence_score(0.6, one_ip_is_vpn=True)
        assert score_vpn < score_normal

    def test_score_clamped_to_zero_minimum(self):
        score, _ = compute_confidence_score(
            0.01,
            is_service_account=True,
            is_cold_start=True,
            is_growing_history=True,
            one_ip_is_vpn=True,
        )
        assert score >= 0.0

    def test_score_clamped_to_one_maximum(self):
        score, _ = compute_confidence_score(
            1.0,
            observed_count=100,
            threshold=5,
            is_proxy=True,
            distinct_ips=5,
            actor_has_baseline=True,
            is_sequence_complete=True,
        )
        assert score <= 1.0

    def test_tier_high(self):
        _, tier = compute_confidence_score(0.9)
        assert tier == "high"

    def test_tier_medium(self):
        _, tier = compute_confidence_score(0.5)
        assert tier == "medium"

    def test_tier_low(self):
        _, tier = compute_confidence_score(0.2)
        assert tier == "low"

    def test_z_score_double_threshold_boosts(self):
        score_base, _ = compute_confidence_score(0.6)
        score_z, _ = compute_confidence_score(0.6, z_score=4.0, z_threshold=2.0)
        assert score_z > score_base


# ─── Field condition evaluation ──────────────────────────────────────────────


class FakeEvent:
    """Minimal stand-in for AuditEvent for field condition tests."""

    def __init__(
        self, action: str = "repos.create", actor: str = "octocat", data: dict | None = None
    ):
        self.action = action
        self.actor = actor
        self.data = data or {}


class TestEvaluateFieldCondition:
    def _ev(self, **kwargs):
        e = FakeEvent()
        for k, v in kwargs.items():
            setattr(e, k, v)
        return e

    def test_eq_match(self):
        ev = self._ev(action="repos.create")
        assert evaluate_field_condition(
            ev, {"field": "action", "operator": "eq", "value": "repos.create"}
        )

    def test_eq_no_match(self):
        ev = self._ev(action="member.add")
        assert not evaluate_field_condition(
            ev, {"field": "action", "operator": "eq", "value": "repos.create"}
        )

    def test_ne_match(self):
        ev = self._ev(actor="alice")
        assert evaluate_field_condition(ev, {"field": "actor", "operator": "ne", "value": "bob"})

    def test_in_match(self):
        ev = self._ev(action="repos.create")
        assert evaluate_field_condition(
            ev, {"field": "action", "operator": "in", "value": ["repos.create", "repos.delete"]}
        )

    def test_in_no_match(self):
        ev = self._ev(action="member.add")
        assert not evaluate_field_condition(
            ev, {"field": "action", "operator": "in", "value": ["repos.create", "repos.delete"]}
        )

    def test_not_in_match(self):
        ev = self._ev(action="member.add")
        assert evaluate_field_condition(
            ev, {"field": "action", "operator": "not_in", "value": ["repos.create"]}
        )

    def test_contains_match(self):
        ev = self._ev(action="repos.create.admin")
        assert evaluate_field_condition(
            ev, {"field": "action", "operator": "contains", "value": "repos"}
        )

    def test_not_contains_match(self):
        ev = self._ev(action="member.add")
        assert evaluate_field_condition(
            ev, {"field": "action", "operator": "not_contains", "value": "repos"}
        )

    def test_exists_present(self):
        ev = self._ev(actor="alice")
        assert evaluate_field_condition(ev, {"field": "actor", "operator": "exists"})

    def test_not_exists_absent(self):
        ev = self._ev()
        ev.actor = None
        assert evaluate_field_condition(ev, {"field": "actor", "operator": "not_exists"})

    def test_matches_glob(self):
        ev = self._ev(action="repos.create")
        assert evaluate_field_condition(
            ev, {"field": "action", "operator": "matches_glob", "value": "repos.*"}
        )

    def test_matches_glob_no_match(self):
        ev = self._ev(action="member.add")
        assert not evaluate_field_condition(
            ev, {"field": "action", "operator": "matches_glob", "value": "repos.*"}
        )

    def test_data_field_access(self):
        ev = FakeEvent(data={"visibility": "private"})
        assert evaluate_field_condition(
            ev, {"field": "data.visibility", "operator": "eq", "value": "private"}
        )

    def test_gt_operator(self):
        ev = self._ev()
        ev.actor_id = 100
        assert evaluate_field_condition(ev, {"field": "actor_id", "operator": "gt", "value": 50})

    def test_lt_operator(self):
        ev = self._ev()
        ev.actor_id = 10
        assert evaluate_field_condition(ev, {"field": "actor_id", "operator": "lt", "value": 50})

    def test_unknown_operator_returns_false(self):
        ev = self._ev(action="repos.create")
        assert not evaluate_field_condition(
            ev, {"field": "action", "operator": "UNKNOWN_OP", "value": "x"}
        )


# ─── event_matches_rule ───────────────────────────────────────────────────────


class FakeRule:
    """Lightweight stub for RuleDefinition."""

    def __init__(self, logic_config: dict):
        self.logic_config = logic_config


class TestEventMatchesRule:
    """Tests for event_matches_rule() - action filters + field conditions."""

    from app.services.detection_service import event_matches_rule as _emr

    def _make_event(self, action: str = "repos.create", actor: str = "alice", **kwargs):
        ev = FakeEvent(action=action, actor=actor)
        for k, v in kwargs.items():
            setattr(ev, k, v)
        return ev

    def test_no_filters_matches_any_event(self):
        from app.services.detection_service import event_matches_rule

        rule = FakeRule({"action_filters": [], "field_conditions": []})
        assert event_matches_rule(self._make_event(), rule)  # type: ignore[arg-type]

    def test_action_filter_exact_match(self):
        from app.services.detection_service import event_matches_rule

        rule = FakeRule({"action_filters": ["repos.create"], "field_conditions": []})
        assert event_matches_rule(self._make_event(action="repos.create"), rule)  # type: ignore[arg-type]

    def test_action_filter_glob_match(self):
        from app.services.detection_service import event_matches_rule

        rule = FakeRule({"action_filters": ["repos.*"], "field_conditions": []})
        assert event_matches_rule(self._make_event(action="repos.delete"), rule)  # type: ignore[arg-type]

    def test_action_filter_no_match(self):
        from app.services.detection_service import event_matches_rule

        rule = FakeRule({"action_filters": ["member.*"], "field_conditions": []})
        assert not event_matches_rule(self._make_event(action="repos.create"), rule)  # type: ignore[arg-type]

    def test_field_condition_and_logic(self):
        from app.services.detection_service import event_matches_rule

        rule = FakeRule(
            {
                "action_filters": [],
                "field_conditions": [
                    {"field": "actor", "operator": "eq", "value": "alice"},
                    {"field": "action", "operator": "eq", "value": "repos.create"},
                ],
            }
        )
        assert event_matches_rule(self._make_event(actor="alice", action="repos.create"), rule)  # type: ignore[arg-type]

    def test_field_condition_fails_one(self):
        from app.services.detection_service import event_matches_rule

        rule = FakeRule(
            {
                "action_filters": [],
                "field_conditions": [
                    {"field": "actor", "operator": "eq", "value": "alice"},
                    {"field": "action", "operator": "eq", "value": "repos.delete"},
                ],
            }
        )
        # action mismatch → False
        assert not event_matches_rule(self._make_event(actor="alice", action="repos.create"), rule)  # type: ignore[arg-type]

    def test_action_and_field_conditions_combined(self):
        from app.services.detection_service import event_matches_rule

        rule = FakeRule(
            {
                "action_filters": ["repos.*"],
                "field_conditions": [
                    {"field": "actor", "operator": "ne", "value": "bot"},
                ],
            }
        )
        assert event_matches_rule(self._make_event(actor="alice", action="repos.create"), rule)  # type: ignore[arg-type]

    def test_action_filter_blocks_before_field_conditions(self):
        from app.services.detection_service import event_matches_rule

        rule = FakeRule(
            {
                "action_filters": ["member.*"],
                "field_conditions": [
                    {"field": "actor", "operator": "eq", "value": "alice"},
                ],
            }
        )
        # Action doesn't match → False immediately, conditions never evaluated
        assert not event_matches_rule(self._make_event(actor="alice", action="repos.create"), rule)  # type: ignore[arg-type]

    def test_missing_action_filters_key(self):
        from app.services.detection_service import event_matches_rule

        # If action_filters key is absent, treat as empty → all actions match
        rule = FakeRule({"field_conditions": []})
        assert event_matches_rule(self._make_event(), rule)  # type: ignore[arg-type]


# ─── Confidence scoring: combined factors ─────────────────────────────────────


class TestComputeConfidenceScoreEdgeCases:
    def test_marginal_threshold_penalty(self):
        """Marginal threshold (within 10%) lowers confidence slightly."""
        score_base, _ = compute_confidence_score(0.7, observed_count=10, threshold=10)
        score_marginal, _ = compute_confidence_score(
            0.7, observed_count=10, threshold=10, is_marginal_threshold=True
        )
        assert score_marginal <= score_base

    def test_multiple_positive_factors(self):
        base, _ = compute_confidence_score(0.5)
        boosted, _ = compute_confidence_score(
            0.5,
            observed_count=30,
            threshold=10,
            is_proxy=True,
            distinct_ips=3,
            actor_has_baseline=True,
        )
        assert boosted > base

    def test_growing_history_lowers_confidence(self):
        score_normal, _ = compute_confidence_score(0.7)
        score_growing, _ = compute_confidence_score(0.7, is_growing_history=True)
        assert score_growing < score_normal

    def test_sequence_complete_boosts_confidence(self):
        score_base, _ = compute_confidence_score(0.6)
        score_seq, _ = compute_confidence_score(0.6, is_sequence_complete=True)
        assert score_seq > score_base
