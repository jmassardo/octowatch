"""Unit tests for the detection service: confidence scoring, field conditions,
suppression checks, and the core pipeline logic."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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

    # ── scope_contains operator ──────────────────────────────────────────

    def test_scope_contains_comma_separated(self):
        """scope_contains matches a whole token in comma-separated values."""
        ev = FakeEvent(data={"scope": "repo,workflow,admin:org"})
        assert evaluate_field_condition(
            ev, {"field": "data.scope", "operator": "scope_contains", "value": "repo"}
        )

    def test_scope_contains_space_separated(self):
        """scope_contains matches a whole token in space-separated values."""
        ev = FakeEvent(data={"scope": "repo workflow admin:org"})
        assert evaluate_field_condition(
            ev, {"field": "data.scope", "operator": "scope_contains", "value": "workflow"}
        )

    def test_scope_contains_mixed_separators(self):
        """scope_contains handles mixed commas and spaces."""
        ev = FakeEvent(data={"scope": "repo, workflow, admin:org"})
        assert evaluate_field_condition(
            ev, {"field": "data.scope", "operator": "scope_contains", "value": "admin:org"}
        )

    def test_scope_contains_no_prefix_match(self):
        """scope_contains must NOT match prefixes — 'repo' should NOT match 'repo:status'."""
        ev = FakeEvent(data={"scope": "repo:status,workflow"})
        assert not evaluate_field_condition(
            ev, {"field": "data.scope", "operator": "scope_contains", "value": "repo"}
        )

    def test_scope_contains_none_returns_false(self):
        """scope_contains on a None value returns False."""
        ev = FakeEvent(data={})
        assert not evaluate_field_condition(
            ev, {"field": "data.scope", "operator": "scope_contains", "value": "repo"}
        )

    def test_scope_contains_single_value(self):
        """scope_contains matches when the scope is a single word."""
        ev = FakeEvent(data={"scope": "repo"})
        assert evaluate_field_condition(
            ev, {"field": "data.scope", "operator": "scope_contains", "value": "repo"}
        )

    def test_scope_contains_no_match(self):
        """scope_contains returns False when the token is not present."""
        ev = FakeEvent(data={"scope": "workflow,admin:org"})
        assert not evaluate_field_condition(
            ev, {"field": "data.scope", "operator": "scope_contains", "value": "repo"}
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


# ─── _SAFE_DISTINCT_COLUMNS whitelist ─────────────────────────────────────────


class TestSafeDistinctColumns:
    """Tests for the _SAFE_DISTINCT_COLUMNS constant (§1.1)."""

    from app.services.detection_service import _SAFE_DISTINCT_COLUMNS

    def test_contains_required_columns(self):
        expected = {"actor", "org", "repo", "source_ip", "user_agent", "geo_country_code", "action"}
        assert expected == self._SAFE_DISTINCT_COLUMNS

    def test_is_frozenset(self):
        assert isinstance(self._SAFE_DISTINCT_COLUMNS, frozenset)

    def test_does_not_contain_unsafe_columns(self):
        unsafe = {"password", "secret", "token", "data", "id"}
        assert not unsafe & self._SAFE_DISTINCT_COLUMNS


# ─── evaluate_threshold_rule validation ───────────────────────────────────────


class TestEvaluateThresholdRuleValidation:
    """Tests for validation logic in evaluate_threshold_rule (§1.2–§1.6).

    These tests exercise early-exit paths that do NOT require a real DB session.
    """

    import pytest as _pytest

    @_pytest.mark.anyio
    async def test_empty_action_filters_returns_empty(self):
        """§1.4: Empty action_filters → return [] immediately."""
        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": [],
                "threshold": 1,
                "time_window_minutes": 60,
                "aggregation_key": "actor",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")
        result = await evaluate_threshold_rule(None, rule, [ev], ["my-org"])  # type: ignore[arg-type]
        assert result == []

    @_pytest.mark.anyio
    async def test_wildcard_only_action_filters_matches_all(self):
        """§1.4: action_filters=['*'] → matches all actions (wildcard)."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["*"],
                "threshold": 100,
                "time_window_minutes": 60,
                "aggregation_key": "actor",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        result = await evaluate_threshold_rule(mock_session, rule, [ev], ["my-org"])  # type: ignore[arg-type]
        assert result == []

    @_pytest.mark.anyio
    async def test_invalid_agg_key_raises_value_error(self):
        """§1.6: Invalid aggregation_key not in whitelist → ValueError."""
        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["repos.create"],
                "threshold": 1,
                "time_window_minutes": 60,
                "aggregation_key": "drop_table",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")
        with self._pytest.raises(
            ValueError, match="aggregation_key 'drop_table' is not a permitted column"
        ):
            await evaluate_threshold_rule(None, rule, [ev], ["my-org"])  # type: ignore[arg-type]

    @_pytest.mark.anyio
    async def test_valid_agg_key_from_whitelist_does_not_raise(self):
        """§1.6: 'source_ip' is in _SAFE_DISTINCT_COLUMNS → no ValueError."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["repos.create"],
                "threshold": 100,
                "time_window_minutes": 60,
                "aggregation_key": "source_ip",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")
        ev.source_ip = "1.2.3.4"

        # Mock session — threshold is high so no hits expected
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value=0)
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Should not raise
        result = await evaluate_threshold_rule(mock_session, rule, [ev], ["my-org"])  # type: ignore[arg-type]
        assert result == []

    @_pytest.mark.anyio
    async def test_invalid_distinct_count_field_raises_value_error(self):
        """§1.3: Invalid distinct_count_field not in whitelist → ValueError."""
        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["repos.create"],
                "threshold": 1,
                "time_window_minutes": 60,
                "aggregation_key": "actor",
                "distinct_count_field": "password_hash",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")
        with self._pytest.raises(
            ValueError, match="distinct_count_field 'password_hash' is not a permitted"
        ):
            await evaluate_threshold_rule(None, rule, [ev], ["my-org"])  # type: ignore[arg-type]

    @_pytest.mark.anyio
    async def test_valid_distinct_count_field_does_not_raise(self):
        """§1.3: 'repo' is in _SAFE_DISTINCT_COLUMNS → no ValueError."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["repos.create"],
                "threshold": 100,
                "time_window_minutes": 60,
                "aggregation_key": "actor",
                "distinct_count_field": "repo",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")

        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value=0)
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await evaluate_threshold_rule(mock_session, rule, [ev], ["my-org"])  # type: ignore[arg-type]
        assert result == []

    @_pytest.mark.anyio
    async def test_agg_key_filter_appears_in_sql(self):
        """§1.2: The batched SQL query must include AND {agg_key} = ANY(:agg_values)."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["repos.create"],
                "threshold": 1,
                "time_window_minutes": 60,
                "aggregation_key": "actor",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")
        ev.id = 42

        mock_row = MagicMock()
        mock_row.agg_val = "alice"
        mock_row.cnt = 5
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await evaluate_threshold_rule(mock_session, rule, [ev], ["my-org"])  # type: ignore[arg-type]

        # Verify the batched SQL query was called with the agg_key filter
        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "AND actor = ANY(:agg_values)" in sql_text
        # Verify agg_values param was passed as a list
        params = call_args[0][1]
        assert params["agg_values"] == ["alice"]

    @_pytest.mark.anyio
    async def test_distinct_count_field_in_sql(self):
        """§1.3: When distinct_count_field is set, SQL uses COUNT(DISTINCT col)."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["repos.create"],
                "threshold": 100,
                "time_window_minutes": 60,
                "aggregation_key": "actor",
                "distinct_count_field": "repo",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")

        mock_row = MagicMock()
        mock_row.agg_val = "alice"
        mock_row.cnt = 0
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await evaluate_threshold_rule(mock_session, rule, [ev], ["my-org"])  # type: ignore[arg-type]

        sql_text = str(mock_session.execute.call_args[0][0])
        assert "COUNT(DISTINCT repo)" in sql_text

    @_pytest.mark.anyio
    async def test_no_matching_events_returns_empty(self):
        """When no events match the rule, return []."""
        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["member.add"],
                "threshold": 1,
                "time_window_minutes": 60,
                "aggregation_key": "actor",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice")
        result = await evaluate_threshold_rule(None, rule, [ev], ["my-org"])  # type: ignore[arg-type]
        assert result == []

    @_pytest.mark.anyio
    async def test_data_dot_agg_key_allowed(self):
        """data.* aggregation keys bypass the whitelist but get regex-validated."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_threshold_rule

        rule = FakeRule(
            {
                "action_filters": ["repos.create"],
                "threshold": 100,
                "time_window_minutes": 60,
                "aggregation_key": "data.visibility",
            }
        )
        ev = FakeEvent(action="repos.create", actor="alice", data={"visibility": "private"})

        mock_row = MagicMock()
        mock_row.agg_val = "private"
        mock_row.cnt = 0
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Should not raise — data.* keys are allowed
        result = await evaluate_threshold_rule(mock_session, rule, [ev], ["my-org"])  # type: ignore[arg-type]
        assert result == []


# ─── Cross-namespace sequence helpers ─────────────────────────────────────────


class TestEvaluateDictFieldCondition:
    """Tests for _evaluate_dict_field_condition() — dict-based field condition matching."""

    def _edc(self, event: dict, condition: dict) -> bool:
        from app.services.detection_service import _evaluate_dict_field_condition

        return _evaluate_dict_field_condition(event, condition)

    def test_eq_match(self) -> None:
        ev = {"action": "repo.create"}
        cond = {"field": "action", "operator": "eq", "value": "repo.create"}
        assert self._edc(ev, cond)

    def test_eq_no_match(self) -> None:
        ev = {"action": "repo.delete"}
        cond = {"field": "action", "operator": "eq", "value": "repo.create"}
        assert not self._edc(ev, cond)

    def test_ne_match(self) -> None:
        ev = {"action": "repo.delete"}
        cond = {"field": "action", "operator": "ne", "value": "repo.create"}
        assert self._edc(ev, cond)

    def test_gt_match(self) -> None:
        assert self._edc({"count": 10}, {"field": "count", "operator": "gt", "value": 5})

    def test_gt_none_returns_false(self) -> None:
        assert not self._edc({}, {"field": "count", "operator": "gt", "value": 5})

    def test_gte_match(self) -> None:
        assert self._edc({"count": 5}, {"field": "count", "operator": "gte", "value": 5})

    def test_lt_match(self) -> None:
        assert self._edc({"count": 3}, {"field": "count", "operator": "lt", "value": 5})

    def test_lte_match(self) -> None:
        assert self._edc({"count": 5}, {"field": "count", "operator": "lte", "value": 5})

    def test_in_match(self) -> None:
        cond = {"field": "action", "operator": "in", "value": ["a", "b"]}
        assert self._edc({"action": "a"}, cond)

    def test_in_empty_value_returns_false(self) -> None:
        assert not self._edc({"action": "a"}, {"field": "action", "operator": "in", "value": []})

    def test_not_in_match(self) -> None:
        cond = {"field": "action", "operator": "not_in", "value": ["a", "b"]}
        assert self._edc({"action": "c"}, cond)

    def test_contains_match(self) -> None:
        ev = {"msg": "hello world"}
        cond = {"field": "msg", "operator": "contains", "value": "world"}
        assert self._edc(ev, cond)

    def test_contains_none_actual_returns_false(self) -> None:
        assert not self._edc({}, {"field": "msg", "operator": "contains", "value": "x"})

    def test_not_contains_match(self) -> None:
        ev = {"msg": "hello"}
        cond = {"field": "msg", "operator": "not_contains", "value": "world"}
        assert self._edc(ev, cond)

    def test_exists_present(self) -> None:
        assert self._edc({"action": "a"}, {"field": "action", "operator": "exists"})

    def test_not_exists_absent(self) -> None:
        assert self._edc({}, {"field": "missing", "operator": "not_exists"})

    def test_matches_glob(self) -> None:
        ev = {"action": "repo.create"}
        cond = {"field": "action", "operator": "matches_glob", "value": "repo.*"}
        assert self._edc(ev, cond)

    def test_matches_glob_no_match(self) -> None:
        ev = {"action": "team.add"}
        cond = {"field": "action", "operator": "matches_glob", "value": "repo.*"}
        assert not self._edc(ev, cond)

    def test_scope_contains(self) -> None:
        ev = {"scopes": "read write admin"}
        cond = {
            "field": "scopes",
            "operator": "scope_contains",
            "value": "write",
        }
        assert self._edc(ev, cond)

    def test_scope_contains_none_returns_false(self) -> None:
        cond = {
            "field": "scopes",
            "operator": "scope_contains",
            "value": "write",
        }
        assert not self._edc({}, cond)

    def test_unknown_operator_returns_false(self) -> None:
        assert not self._edc({"a": 1}, {"field": "a", "operator": "xyzzy", "value": 1})

    def test_data_dot_field_access(self) -> None:
        assert self._edc(
            {"data": {"visibility": "private"}},
            {"field": "data.visibility", "operator": "eq", "value": "private"},
        )

    def test_data_dot_field_missing_data(self) -> None:
        assert not self._edc(
            {"data": None},
            {"field": "data.visibility", "operator": "exists"},
        )

    def test_data_not_dict_returns_none(self) -> None:
        assert not self._edc(
            {"data": "not-a-dict"},
            {"field": "data.key", "operator": "exists"},
        )


class TestEventDictMatchesStep:
    """Tests for _event_dict_matches_step() — step-level matching."""

    def _edms(self, event: dict, step: dict) -> bool:
        from app.services.detection_service import _event_dict_matches_step

        return _event_dict_matches_step(event, step)

    def test_matches_action(self) -> None:
        step = {"action_filters": ["repo.create"], "field_conditions": []}
        assert self._edms({"action": "repo.create"}, step)

    def test_no_match_action(self) -> None:
        step = {"action_filters": ["repo.create"], "field_conditions": []}
        assert not self._edms({"action": "repo.delete"}, step)

    def test_empty_action_filters_matches_any(self) -> None:
        step = {"action_filters": [], "field_conditions": []}
        assert self._edms({"action": "anything"}, step)

    def test_field_condition_filters(self) -> None:
        step = {
            "action_filters": ["repo.create"],
            "field_conditions": [
                {"field": "org", "operator": "eq", "value": "my-org"},
            ],
        }
        assert self._edms({"action": "repo.create", "org": "my-org"}, step)
        assert not self._edms({"action": "repo.create", "org": "other"}, step)

    def test_multiple_field_conditions_all_must_pass(self) -> None:
        step = {
            "action_filters": ["repo.create"],
            "field_conditions": [
                {"field": "org", "operator": "eq", "value": "my-org"},
                {"field": "actor", "operator": "eq", "value": "alice"},
            ],
        }
        assert self._edms({"action": "repo.create", "org": "my-org", "actor": "alice"}, step)
        assert not self._edms({"action": "repo.create", "org": "my-org", "actor": "bob"}, step)

    def test_no_field_conditions_key(self) -> None:
        step = {"action_filters": ["repo.create"]}
        assert self._edms({"action": "repo.create"}, step)


class TestMatchSequenceSteps:
    """Tests for _match_sequence_steps() — pure sequence matching logic."""

    from datetime import datetime, timedelta

    def _mss(
        self,
        events: list[dict],
        steps: list[dict],
        window_minutes: int,
        require_distinct: bool,
    ) -> list[dict] | None:
        from app.services.detection_service import _match_sequence_steps

        return _match_sequence_steps(events, steps, window_minutes, require_distinct)

    def _make_event(self, eid: int, action: str, minutes_offset: int = 0, **extra: object) -> dict:
        base = self.datetime(2024, 1, 1, 12, 0, 0)
        ev: dict = {
            "id": eid,
            "action": action,
            "created_at": base + self.timedelta(minutes=minutes_offset),
        }
        ev.update(extra)
        return ev

    def test_simple_two_step_match(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0),
            self._make_event(2, "repo.create_actions_secret", 10),
        ]
        steps = [
            {"step": 1, "action_filters": ["repo.create"]},
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is not None
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_no_match_when_step_missing(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0),
        ]
        steps = [
            {"step": 1, "action_filters": ["repo.create"]},
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is None

    def test_no_match_outside_window(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0),
            self._make_event(2, "repo.create_actions_secret", 130),
        ]
        steps = [
            {"step": 1, "action_filters": ["repo.create"]},
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is None

    def test_order_matters(self) -> None:
        # step 2 action appears before step 1 action — should not match unless
        # a later event provides step 1 followed by step 2
        events = [
            self._make_event(1, "repo.create_actions_secret", 0),
            self._make_event(2, "repo.create", 10),
        ]
        steps = [
            {"step": 1, "action_filters": ["repo.create"]},
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is None

    def test_require_distinct_prevents_reuse(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0),
        ]
        steps = [
            {"step": 1, "action_filters": ["repo.create"]},
            {"step": 2, "action_filters": ["repo.create"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is None

    def test_require_distinct_false_allows_reuse(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0),
            self._make_event(2, "repo.create", 5),
        ]
        steps = [
            {"step": 1, "action_filters": ["repo.create"]},
            {"step": 2, "action_filters": ["repo.create"]},
        ]
        result = self._mss(events, steps, 120, False)
        assert result is not None

    def test_min_count_greater_than_one(self) -> None:
        events = [
            self._make_event(1, "auth.login_failure", 0),
            self._make_event(2, "auth.login_failure", 5),
            self._make_event(3, "auth.login_failure", 10),
            self._make_event(4, "auth.login_success", 15),
        ]
        steps = [
            {"step": 1, "action_filters": ["auth.login_failure"], "min_count": 3},
            {"step": 2, "action_filters": ["auth.login_success"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is not None
        assert len(result) == 4

    def test_min_count_not_met(self) -> None:
        events = [
            self._make_event(1, "auth.login_failure", 0),
            self._make_event(2, "auth.login_failure", 5),
            self._make_event(3, "auth.login_success", 15),
        ]
        steps = [
            {"step": 1, "action_filters": ["auth.login_failure"], "min_count": 3},
            {"step": 2, "action_filters": ["auth.login_success"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is None

    def test_three_step_sequence(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0),
            self._make_event(2, "repo.create_actions_secret", 10),
            self._make_event(3, "actions.workflow_dispatch", 20),
        ]
        steps = [
            {"step": 1, "action_filters": ["repo.create"]},
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
            {"step": 3, "action_filters": ["actions.workflow_dispatch"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is not None
        assert len(result) == 3

    def test_empty_steps_returns_none(self) -> None:
        events = [self._make_event(1, "repo.create", 0)]
        result = self._mss(events, [], 120, True)
        assert result is None

    def test_empty_events_returns_none(self) -> None:
        steps = [{"step": 1, "action_filters": ["repo.create"]}]
        result = self._mss([], steps, 120, True)
        assert result is None

    def test_single_step_rule(self) -> None:
        events = [self._make_event(1, "repo.create", 0)]
        steps = [{"step": 1, "action_filters": ["repo.create"]}]
        result = self._mss(events, steps, 120, True)
        assert result is not None
        assert len(result) == 1

    def test_skips_non_matching_events(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0),
            self._make_event(2, "org.update", 5),  # noise
            self._make_event(3, "repo.create_actions_secret", 10),
        ]
        steps = [
            {"step": 1, "action_filters": ["repo.create"]},
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is not None
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 3

    def test_steps_out_of_order_in_config(self) -> None:
        """Steps specified out of order in config are sorted by step number."""
        events = [
            self._make_event(1, "repo.create", 0),
            self._make_event(2, "repo.create_actions_secret", 10),
        ]
        steps = [
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
            {"step": 1, "action_filters": ["repo.create"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is not None
        assert len(result) == 2

    def test_field_conditions_in_step(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0, org="my-org"),
            self._make_event(2, "repo.create_actions_secret", 10, org="my-org"),
        ]
        steps = [
            {
                "step": 1,
                "action_filters": ["repo.create"],
                "field_conditions": [{"field": "org", "operator": "eq", "value": "my-org"}],
            },
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is not None

    def test_field_conditions_block_match(self) -> None:
        events = [
            self._make_event(1, "repo.create", 0, org="other-org"),
            self._make_event(2, "repo.create_actions_secret", 10, org="other-org"),
        ]
        steps = [
            {
                "step": 1,
                "action_filters": ["repo.create"],
                "field_conditions": [{"field": "org", "operator": "eq", "value": "my-org"}],
            },
            {"step": 2, "action_filters": ["repo.create_actions_secret"]},
        ]
        result = self._mss(events, steps, 120, True)
        assert result is None


class TestEvaluateCrossNamespaceSequence:
    """Tests for evaluate_cross_namespace_sequence() — SQL + grouping + matching."""

    import pytest as _pytest

    @_pytest.mark.anyio
    async def test_empty_steps_returns_empty(self) -> None:
        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "actor",
                "time_window_minutes": 120,
                "require_distinct_steps": True,
                "steps": [],
            }
        )
        result = await evaluate_cross_namespace_sequence(None, rule, ["my-org"])  # type: ignore[arg-type]
        assert result == []

    @_pytest.mark.anyio
    async def test_empty_action_filters_returns_empty(self) -> None:
        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "actor",
                "time_window_minutes": 120,
                "require_distinct_steps": True,
                "steps": [{"step": 1, "action_filters": []}],
            }
        )
        result = await evaluate_cross_namespace_sequence(None, rule, ["my-org"])  # type: ignore[arg-type]
        assert result == []

    @_pytest.mark.anyio
    async def test_invalid_agg_key_raises(self) -> None:
        import pytest

        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "data.evil; DROP TABLE events;",
                "time_window_minutes": 120,
                "steps": [{"step": 1, "action_filters": ["repo.create"]}],
            }
        )
        with pytest.raises(ValueError, match="not a permitted column"):
            await evaluate_cross_namespace_sequence(None, rule, ["my-org"])  # type: ignore[arg-type]

    @_pytest.mark.anyio
    async def test_no_events_returns_empty(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "actor",
                "time_window_minutes": 120,
                "require_distinct_steps": True,
                "steps": [
                    {"step": 1, "action_filters": ["repo.create"]},
                    {"step": 2, "action_filters": ["repo.create_actions_secret"]},
                ],
            }
        )
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await evaluate_cross_namespace_sequence(mock_session, rule, ["my-org"])
        assert result == []

    @_pytest.mark.anyio
    async def test_complete_sequence_returns_hit(self) -> None:
        from datetime import datetime
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "actor",
                "time_window_minutes": 120,
                "require_distinct_steps": True,
                "steps": [
                    {"step": 1, "action_filters": ["repo.create"]},
                    {"step": 2, "action_filters": ["repo.create_actions_secret"]},
                ],
                "confidence": 0.75,
            }
        )

        t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC)

        class FakeRow:
            def __init__(self, mapping: dict) -> None:
                self._mapping = mapping

        rows = [
            FakeRow(
                {
                    "id": 1,
                    "action": "repo.create",
                    "actor": "alice",
                    "org": "my-org",
                    "repo": "my-org/repo1",
                    "source_ip": "1.2.3.4",
                    "created_at": t1,
                    "data": {},
                    "geo_country_code": "US",
                    "user_agent": "ua",
                }
            ),
            FakeRow(
                {
                    "id": 2,
                    "action": "repo.create_actions_secret",
                    "actor": "alice",
                    "org": "my-org",
                    "repo": "my-org/repo1",
                    "source_ip": "1.2.3.4",
                    "created_at": t2,
                    "data": {},
                    "geo_country_code": "US",
                    "user_agent": "ua",
                }
            ),
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await evaluate_cross_namespace_sequence(mock_session, rule, ["my-org"])
        assert len(result) == 1
        hit = result[0]
        assert hit["aggregation_key_value"] == "alice"
        assert hit["matched_steps"] == 2
        assert hit["actor"] == "alice"
        assert hit["org"] == "my-org"
        assert len(hit["event_ids"]) == 2
        assert hit["time_span_minutes"] == 30.0

    @_pytest.mark.anyio
    async def test_groups_by_actor(self) -> None:
        from datetime import datetime
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "actor",
                "time_window_minutes": 120,
                "require_distinct_steps": True,
                "steps": [
                    {"step": 1, "action_filters": ["repo.create"]},
                    {"step": 2, "action_filters": ["repo.create_actions_secret"]},
                ],
            }
        )

        t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC)

        class FakeRow:
            def __init__(self, mapping: dict) -> None:
                self._mapping = mapping

        rows = [
            # alice: complete sequence
            FakeRow(
                {
                    "id": 1,
                    "action": "repo.create",
                    "actor": "alice",
                    "org": "o",
                    "repo": "r",
                    "source_ip": None,
                    "created_at": t1,
                    "data": {},
                    "geo_country_code": None,
                    "user_agent": None,
                }
            ),
            FakeRow(
                {
                    "id": 2,
                    "action": "repo.create_actions_secret",
                    "actor": "alice",
                    "org": "o",
                    "repo": "r",
                    "source_ip": None,
                    "created_at": t2,
                    "data": {},
                    "geo_country_code": None,
                    "user_agent": None,
                }
            ),
            # bob: only step 1
            FakeRow(
                {
                    "id": 3,
                    "action": "repo.create",
                    "actor": "bob",
                    "org": "o",
                    "repo": "r",
                    "source_ip": None,
                    "created_at": t1,
                    "data": {},
                    "geo_country_code": None,
                    "user_agent": None,
                }
            ),
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await evaluate_cross_namespace_sequence(mock_session, rule, ["o"])
        assert len(result) == 1
        assert result[0]["aggregation_key_value"] == "alice"

    @_pytest.mark.anyio
    async def test_null_agg_key_value_skipped(self) -> None:
        from datetime import datetime
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "actor",
                "time_window_minutes": 120,
                "require_distinct_steps": True,
                "steps": [
                    {"step": 1, "action_filters": ["repo.create"]},
                    {"step": 2, "action_filters": ["repo.create_actions_secret"]},
                ],
            }
        )

        t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC)

        class FakeRow:
            def __init__(self, mapping: dict) -> None:
                self._mapping = mapping

        rows = [
            FakeRow(
                {
                    "id": 1,
                    "action": "repo.create",
                    "actor": None,
                    "org": "o",
                    "repo": "r",
                    "source_ip": None,
                    "created_at": t1,
                    "data": {},
                    "geo_country_code": None,
                    "user_agent": None,
                }
            ),
            FakeRow(
                {
                    "id": 2,
                    "action": "repo.create_actions_secret",
                    "actor": None,
                    "org": "o",
                    "repo": "r",
                    "source_ip": None,
                    "created_at": t2,
                    "data": {},
                    "geo_country_code": None,
                    "user_agent": None,
                }
            ),
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await evaluate_cross_namespace_sequence(mock_session, rule, ["o"])
        assert result == []

    @_pytest.mark.anyio
    async def test_sql_uses_bind_params(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "actor",
                "time_window_minutes": 60,
                "require_distinct_steps": True,
                "steps": [
                    {"step": 1, "action_filters": ["repo.create"]},
                    {"step": 2, "action_filters": ["repo.create_actions_secret"]},
                ],
            }
        )

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await evaluate_cross_namespace_sequence(mock_session, rule, ["my-org"])

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        params = call_args[0][1]

        assert "action = ANY(:actions)" in sql_text
        assert "org = ANY(:scoped_orgs)" in sql_text
        assert "created_at >= :cutoff" in sql_text
        assert params["actions"] == ["repo.create", "repo.create_actions_secret"]
        assert params["scoped_orgs"] == ["my-org"]
        assert "cutoff" in params

    @_pytest.mark.anyio
    async def test_non_actor_agg_key(self) -> None:
        from datetime import datetime
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import evaluate_cross_namespace_sequence

        rule = FakeRule(
            {
                "aggregation_key": "source_ip",
                "time_window_minutes": 120,
                "require_distinct_steps": True,
                "steps": [
                    {"step": 1, "action_filters": ["repo.create"]},
                    {"step": 2, "action_filters": ["repo.create_actions_secret"]},
                ],
            }
        )

        t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC)

        class FakeRow:
            def __init__(self, mapping: dict) -> None:
                self._mapping = mapping

        rows = [
            FakeRow(
                {
                    "id": 1,
                    "action": "repo.create",
                    "actor": "alice",
                    "org": "o",
                    "repo": "r",
                    "source_ip": "10.0.0.1",
                    "created_at": t1,
                    "data": {},
                    "geo_country_code": None,
                    "user_agent": None,
                }
            ),
            FakeRow(
                {
                    "id": 2,
                    "action": "repo.create_actions_secret",
                    "actor": "alice",
                    "org": "o",
                    "repo": "r",
                    "source_ip": "10.0.0.1",
                    "created_at": t2,
                    "data": {},
                    "geo_country_code": None,
                    "user_agent": None,
                }
            ),
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await evaluate_cross_namespace_sequence(mock_session, rule, ["o"])
        assert len(result) == 1
        hit = result[0]
        assert hit["aggregation_key"] == "source_ip"
        assert hit["aggregation_key_value"] == "10.0.0.1"
        # actor should come from the first matched event
        assert hit["actor"] == "alice"


# ─── _evaluate_sequence_rule with data.* aggregation keys ─────────────────────


class _FakeSeqEvent:
    """Minimal event stub for _evaluate_sequence_rule candidates."""

    def __init__(self, action: str, data: dict[str, Any] | None = None) -> None:
        self.action = action
        self.data = data or {}


class _FakeSeqRow:
    """Minimal DB row stub matching the SELECT id, action, created_at query."""

    def __init__(self, id: int, action: str, created_at: datetime) -> None:
        self.id = id
        self.action = action
        self.created_at = created_at


class _FakeSeqRule:
    """Rule stub with all attributes needed by _evaluate_sequence_rule."""

    def __init__(self, logic_config: dict[str, Any]) -> None:
        self.logic_config = logic_config
        self.id = 1
        self.version = 1
        self.name = "Test Sequence Rule"
        self.description = "Test description"
        self.default_severity = "medium"


class TestEvaluateSequenceRuleDataKeys:
    """Tests for _evaluate_sequence_rule with data.* aggregation keys."""

    import pytest as _pytest

    @_pytest.mark.anyio
    async def test_data_repo_agg_key_builds_jsonb_sql(self) -> None:
        """Sequence rule with data.repo builds SQL using data->>'repo'."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                    {"action": "repo.create_actions_secret"},
                ],
                "aggregation_key": "data.repo",
                "time_window_minutes": 60,
            }
        )
        events = [
            _FakeSeqEvent("repo.create", data={"repo": "acme/web-app"}),
            _FakeSeqEvent("repo.create_actions_secret", data={"repo": "acme/web-app"}),
        ]

        # Return empty results so sequence is incomplete — we just check SQL
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await _evaluate_sequence_rule(mock_session, rule, events, ["acme"])  # type: ignore[arg-type]

        # Verify SQL uses JSONB extraction
        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "data->>'repo'" in sql_text
        assert "action = ANY(:actions)" in sql_text
        assert "created_at >= :window_start" in sql_text

        # Verify bind parameters
        params = call_args[0][1]
        assert params["agg_value"] == "acme/web-app"
        assert params["actions"] == ["repo.create", "repo.create_actions_secret"]

    @_pytest.mark.anyio
    async def test_data_org_agg_key_builds_jsonb_sql(self) -> None:
        """Sequence rule with data.org builds SQL using data->>'org'."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "org.add_member"},
                    {"action": "org.update_member"},
                ],
                "aggregation_key": "data.org",
                "time_window_minutes": 120,
            }
        )
        events = [
            _FakeSeqEvent("org.add_member", data={"org": "my-org"}),
            _FakeSeqEvent("org.update_member", data={"org": "my-org"}),
        ]

        # Return empty results so sequence is incomplete — we just check SQL
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await _evaluate_sequence_rule(mock_session, rule, events, ["my-org"])  # type: ignore[arg-type]

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "data->>'org'" in sql_text
        params = call_args[0][1]
        assert params["agg_value"] == "my-org"

    @_pytest.mark.anyio
    async def test_missing_jsonb_field_excluded_from_agg_values(self) -> None:
        """Events where the JSONB field is missing are excluded from aggregation."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                    {"action": "repo.delete"},
                ],
                "aggregation_key": "data.team",
                "time_window_minutes": 60,
            }
        )
        # First event has team, second doesn't — only "platform" should be queried
        events = [
            _FakeSeqEvent("repo.create", data={"team": "platform"}),
            _FakeSeqEvent("repo.delete", data={}),  # no team key
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await _evaluate_sequence_rule(mock_session, rule, events, ["org"])  # type: ignore[arg-type]

        # Should execute exactly once — only for "platform"
        assert mock_session.execute.call_count == 1
        params = mock_session.execute.call_args[0][1]
        assert params["agg_value"] == "platform"

    @_pytest.mark.anyio
    async def test_all_events_missing_jsonb_field_skips_query(self) -> None:
        """When no events have the aggregation field, no DB query is issued."""
        from unittest.mock import AsyncMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                    {"action": "repo.delete"},
                ],
                "aggregation_key": "data.nonexistent",
                "time_window_minutes": 60,
            }
        )
        events = [
            _FakeSeqEvent("repo.create", data={"repo": "acme/web"}),
            _FakeSeqEvent("repo.delete", data={"repo": "acme/web"}),
        ]

        mock_session = AsyncMock()

        await _evaluate_sequence_rule(mock_session, rule, events, ["org"])  # type: ignore[arg-type]

        # No agg_values means the loop body never runs
        mock_session.execute.assert_not_called()

    @_pytest.mark.anyio
    async def test_data_key_sequence_ordering(self) -> None:
        """Sequence steps must match in chronological order for data.* keys."""
        from datetime import datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                    {"action": "repo.create_actions_secret"},
                ],
                "aggregation_key": "data.repo",
                "time_window_minutes": 60,
                "confidence": 0.7,
            }
        )
        events = [
            _FakeSeqEvent("repo.create", data={"repo": "acme/web"}),
            _FakeSeqEvent("repo.create_actions_secret", data={"repo": "acme/web"}),
        ]

        # DB returns events in CORRECT chronological order
        t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, 12, 10, 0, tzinfo=UTC)
        db_rows = [
            _FakeSeqRow(10, "repo.create", t1),
            _FakeSeqRow(11, "repo.create_actions_secret", t2),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = db_rows
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.services.detection_service.check_suppression",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.detection_service.find_existing_detection",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.detection_service.resolve_severity",
                new_callable=AsyncMock,
                return_value="high",
            ),
        ):
            await _evaluate_sequence_rule(mock_session, rule, events, ["acme"])  # type: ignore[arg-type]

        # Detection was created — session.add was called
        mock_session.add.assert_called_once()
        detection = mock_session.add.call_args[0][0]
        assert detection.event_ids == [10, 11]
        assert detection.actor is None  # data.* key, not actor
        assert detection.context_data["aggregation_key_value"] == "acme/web"

    @_pytest.mark.anyio
    async def test_data_key_sequence_wrong_order_no_detection(self) -> None:
        """Events in wrong order should not trigger a detection for data.* keys."""
        from datetime import datetime
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                    {"action": "repo.create_actions_secret"},
                ],
                "aggregation_key": "data.repo",
                "time_window_minutes": 60,
            }
        )
        events = [
            _FakeSeqEvent("repo.create", data={"repo": "acme/web"}),
            _FakeSeqEvent("repo.create_actions_secret", data={"repo": "acme/web"}),
        ]

        # DB returns events in WRONG order (step 2 before step 1)
        t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, 12, 10, 0, tzinfo=UTC)
        db_rows = [
            _FakeSeqRow(11, "repo.create_actions_secret", t1),
            _FakeSeqRow(10, "repo.create", t2),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = db_rows
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await _evaluate_sequence_rule(mock_session, rule, events, ["acme"])  # type: ignore[arg-type]

        # No detection created since sequence is not in correct order
        mock_session.add.assert_not_called()

    @_pytest.mark.anyio
    async def test_invalid_data_key_returns_early(self) -> None:
        """data.* key with special chars returns early without querying the DB."""
        from unittest.mock import AsyncMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                ],
                "aggregation_key": "data.evil;DROP TABLE events;",
                "time_window_minutes": 60,
            }
        )
        events = [
            _FakeSeqEvent("repo.create", data={"evil;DROP TABLE events;": "val"}),
        ]

        mock_session = AsyncMock()

        await _evaluate_sequence_rule(mock_session, rule, events, ["org"])  # type: ignore[arg-type]

        # Should return early without any DB query
        mock_session.execute.assert_not_called()

    @_pytest.mark.anyio
    async def test_unsupported_agg_key_returns_early(self) -> None:
        """An aggregation key that is not in whitelist and not data.* returns early."""
        from unittest.mock import AsyncMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                ],
                "aggregation_key": "unknown_column",
                "time_window_minutes": 60,
            }
        )
        # events need to pass event_matches_rule and have the agg_key attribute
        event = _FakeSeqEvent("repo.create")
        event.unknown_column = "val"  # type: ignore[attr-defined]

        mock_session = AsyncMock()

        await _evaluate_sequence_rule(mock_session, rule, [event], ["org"])  # type: ignore[arg-type]

        mock_session.execute.assert_not_called()

    @_pytest.mark.anyio
    async def test_safe_column_agg_key_works(self) -> None:
        """Non-actor keys in _SAFE_DISTINCT_COLUMNS (e.g. 'repo') work correctly."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                    {"action": "repo.delete"},
                ],
                "aggregation_key": "repo",
                "time_window_minutes": 60,
            }
        )
        event = _FakeSeqEvent("repo.create")
        event.repo = "acme/web"  # type: ignore[attr-defined]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await _evaluate_sequence_rule(mock_session, rule, [event], ["acme"])  # type: ignore[arg-type]

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        # Should use the column name directly, not JSONB extraction
        assert "repo = :agg_value" in sql_text
        assert "data->>" not in sql_text

    @_pytest.mark.anyio
    async def test_data_key_multiple_agg_values(self) -> None:
        """Multiple distinct data.* values each get their own DB query."""
        from unittest.mock import AsyncMock, MagicMock

        from app.services.detection_service import _evaluate_sequence_rule

        rule = _FakeSeqRule(
            {
                "sequence_steps": [
                    {"action": "repo.create"},
                    {"action": "repo.delete"},
                ],
                "aggregation_key": "data.team",
                "time_window_minutes": 60,
            }
        )
        events = [
            _FakeSeqEvent("repo.create", data={"team": "alpha"}),
            _FakeSeqEvent("repo.create", data={"team": "beta"}),
            _FakeSeqEvent("repo.delete", data={"team": "alpha"}),
        ]

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await _evaluate_sequence_rule(mock_session, rule, events, ["org"])  # type: ignore[arg-type]

        # Two distinct teams => two queries
        assert mock_session.execute.call_count == 2
        queried_values = {call[0][1]["agg_value"] for call in mock_session.execute.call_args_list}
        assert queried_values == {"alpha", "beta"}
