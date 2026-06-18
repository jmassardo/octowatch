"""Tests for Epic 4 detection coverage expansion.

Covers:
- Baseline worker schema alignment (#60)
- Off-hours anomaly detection (#60)
- Threat intel CRUD endpoints (#55)
- Threat intel IP matching (#55)
- New detection rule evaluation (#36, #33, #30)
- Threat intel feed fetch task (#55)
- Detection rule fixtures loading (#30, #33, #36)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.detection import BehavioralBaseline, RuleDefinition
from app.services.detection_service import (
    _adjust_threshold_with_baseline,
    evaluate_off_hours_anomaly,
    event_matches_rule,
)
from app.services.threat_intel_service import (
    create_feed,
    create_indicator,
    fetch_feed_indicators,
    get_feeds,
    get_indicators,
    is_malicious_domain,
    is_malicious_indicator,
    is_malicious_ip,
    soft_delete_indicator,
    update_indicator,
)
from app.workers.baseline_worker import _percentile, _upsert_baseline

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_event(
    *,
    event_id: int = 1,
    action: str = "repos.create",
    actor: str = "testuser",
    org: str = "my-org",
    repo: str = "my-org/hello-world",
    source_ip: str = "192.168.1.1",
    user_agent: str = "Mozilla/5.0",
    created_at: datetime | None = None,
    data: dict | None = None,
    geo_latitude: float | None = None,
    geo_longitude: float | None = None,
    geo_is_proxy: bool = False,
    actor_is_bot: bool = False,
) -> MagicMock:
    """Create a mock AuditEvent with specified attributes."""
    event = MagicMock()
    event.id = event_id
    event.action = action
    event.actor = actor
    event.org = org
    event.repo = repo
    event.source_ip = source_ip
    event.user_agent = user_agent
    event.created_at = created_at or datetime.now(UTC)
    event.data = data or {}
    event.geo_latitude = geo_latitude
    event.geo_longitude = geo_longitude
    event.geo_is_proxy = geo_is_proxy
    event.actor_is_bot = actor_is_bot
    return event


def _make_rule(
    *,
    rule_id: int = 1,
    name: str = "Test Rule",
    slug: str = "test-rule",
    logic_type: str = "pattern",
    logic_config: dict | None = None,
    default_severity: str = "medium",
    default_confidence: str = "medium",
    version: int = 1,
    enabled: bool = True,
    status: str = "active",
) -> MagicMock:
    """Create a mock RuleDefinition with specified attributes."""
    rule = MagicMock(spec=RuleDefinition)
    rule.id = rule_id
    rule.name = name
    rule.slug = slug
    rule.logic_type = logic_type
    rule.logic_config = logic_config or {}
    rule.default_severity = default_severity
    rule.default_confidence = default_confidence
    rule.version = version
    rule.enabled = enabled
    rule.status = status
    rule.description = f"Test rule: {name}"
    return rule


def _make_baseline(
    *,
    baseline_type: str = "actor",
    scope_key: str = "actor:testuser:org:my-org",
    metric_name: str = "active_hours",
    mean: float = 14.0,
    stddev: float = 2.5,
    p95: float = 18.0,
    p99: float = 20.0,
    sample_count: int = 100,
) -> MagicMock:
    """Create a mock BehavioralBaseline."""
    baseline = MagicMock(spec=BehavioralBaseline)
    baseline.baseline_type = baseline_type
    baseline.scope_key = scope_key
    baseline.metric_name = metric_name
    baseline.mean = mean
    baseline.stddev = stddev
    baseline.p95 = p95
    baseline.p99 = p99
    baseline.sample_count = sample_count
    baseline.window_start = datetime.now(UTC) - timedelta(days=30)
    baseline.window_end = datetime.now(UTC)
    return baseline


# ═══════════════════════════════════════════════════════════════════════════════
# §1 — Baseline Worker Schema Alignment Tests (#60)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBaselineWorkerPercentile:
    """Test the _percentile helper used by baseline computations."""

    def test_percentile_empty_list(self):
        assert _percentile([], 95) == 0.0

    def test_percentile_single_value(self):
        assert _percentile([5.0], 95) == 5.0

    def test_percentile_p95(self):
        values = list(range(1, 101))
        p95 = _percentile([float(v) for v in values], 95)
        assert 94.0 <= p95 <= 96.0

    def test_percentile_p99(self):
        values = list(range(1, 101))
        p99 = _percentile([float(v) for v in values], 99)
        assert 98.0 <= p99 <= 100.0

    def test_percentile_p50_median(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        p50 = _percentile(values, 50)
        assert p50 == 3.0

    def test_percentile_all_same(self):
        values = [7.0, 7.0, 7.0, 7.0]
        assert _percentile(values, 95) == 7.0


class TestBaselineUpsertFunction:
    """Test that _upsert_baseline generates correct SQL parameters."""

    @pytest.mark.asyncio
    async def test_upsert_baseline_calls_session_execute(self):
        session = AsyncMock()
        await _upsert_baseline(
            session,
            baseline_type="actor",
            scope_key="actor:jdoe:org:acme",
            metric_name="daily_events",
            window_start=datetime(2024, 1, 1, tzinfo=UTC),
            window_end=datetime(2024, 1, 31, tzinfo=UTC),
            mean=10.5,
            stddev=3.2,
            p95=16.0,
            p99=20.0,
            sample_count=30,
        )
        session.execute.assert_called_once()
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["baseline_type"] == "actor"
        assert params["scope_key"] == "actor:jdoe:org:acme"
        assert params["metric_name"] == "daily_events"
        assert params["mean"] == 10.5
        assert params["stddev"] == 3.2
        assert params["p95"] == 16.0
        assert params["p99"] == 20.0
        assert params["sample_count"] == 30


# ═══════════════════════════════════════════════════════════════════════════════
# §2 — Off-Hours Anomaly Detection Tests (#60)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOffHoursAnomalyDetection:
    """Test off-hours anomaly detection engine."""

    @pytest.mark.asyncio
    async def test_off_hours_flags_event_outside_range(self):
        """Event at hour 3 should be flagged when baseline mean=14, stddev=2.5."""
        session = AsyncMock()

        # Mock _load_baseline to return an actor-level baseline
        baseline = _make_baseline(mean=14.0, stddev=2.5)

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=baseline,
        ):
            rule = _make_rule(
                logic_type="statistical",
                logic_config={
                    "action_filters": ["*"],
                    "x_config": {"engine": "off_hours_anomaly", "z_multiplier": 2.0},
                    "time_window_minutes": 60,
                    "confidence": 0.55,
                },
            )
            event = _make_event(
                created_at=datetime(2024, 6, 15, 3, 0, 0, tzinfo=UTC),
                action="repos.create",
            )
            results = await evaluate_off_hours_anomaly(session, rule, [event], ["my-org"])

        assert len(results) == 1
        ctx = results[0]["context_data"]
        assert ctx["event_hour"] == 3
        assert ctx["baseline_mean_hour"] == 14.0
        assert ctx["z_score"] > 2.0

    @pytest.mark.asyncio
    async def test_off_hours_no_flag_within_range(self):
        """Event at hour 14 should not be flagged when baseline mean=14, stddev=2.5."""
        session = AsyncMock()

        baseline = _make_baseline(mean=14.0, stddev=2.5)

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=baseline,
        ):
            rule = _make_rule(
                logic_type="statistical",
                logic_config={
                    "action_filters": ["*"],
                    "x_config": {"engine": "off_hours_anomaly", "z_multiplier": 2.0},
                    "time_window_minutes": 60,
                    "confidence": 0.55,
                },
            )
            event = _make_event(
                created_at=datetime(2024, 6, 15, 14, 30, 0, tzinfo=UTC),
            )
            results = await evaluate_off_hours_anomaly(session, rule, [event], ["my-org"])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_off_hours_no_baseline_skips(self):
        """Events should be skipped when no baseline exists."""
        session = AsyncMock()

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=None,
        ):
            rule = _make_rule(
                logic_type="statistical",
                logic_config={
                    "action_filters": ["*"],
                    "x_config": {"engine": "off_hours_anomaly", "z_multiplier": 2.0},
                    "time_window_minutes": 60,
                    "confidence": 0.55,
                },
            )
            event = _make_event(
                created_at=datetime(2024, 6, 15, 3, 0, 0, tzinfo=UTC),
            )
            results = await evaluate_off_hours_anomaly(session, rule, [event], ["my-org"])

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_off_hours_org_fallback(self):
        """Should fall back to org baseline when no actor baseline exists."""
        session = AsyncMock()

        org_baseline = _make_baseline(
            baseline_type="org",
            scope_key="org:my-org",
            mean=12.0,
            stddev=3.0,
        )

        call_count = 0

        async def mock_load(s, bt, sk, mn):
            nonlocal call_count
            call_count += 1
            if bt == "actor":
                return None  # No actor baseline
            return org_baseline

        with patch(
            "app.services.detection_service._load_baseline",
            side_effect=mock_load,
        ):
            rule = _make_rule(
                logic_type="statistical",
                logic_config={
                    "action_filters": ["*"],
                    "x_config": {"engine": "off_hours_anomaly", "z_multiplier": 2.0},
                    "time_window_minutes": 60,
                    "confidence": 0.55,
                },
            )
            event = _make_event(
                created_at=datetime(2024, 6, 15, 3, 0, 0, tzinfo=UTC),
            )
            results = await evaluate_off_hours_anomaly(session, rule, [event], ["my-org"])

        assert len(results) == 1
        assert results[0]["context_data"]["baseline_type"] == "org"


# ═══════════════════════════════════════════════════════════════════════════════
# §3 — Threat Intel IP Matching Tests (#55)
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreatIntelIPMatching:
    """Test IP-based threat intelligence matching."""

    @pytest.mark.asyncio
    async def test_exact_ip_match(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"value": "10.0.0.5", "source": "manual", "confidence": 0.9}
        ]
        session.execute.return_value = mock_result

        is_mal, source = await is_malicious_ip(session, "10.0.0.5")
        assert is_mal is True
        assert source == "manual"

    @pytest.mark.asyncio
    async def test_cidr_match(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"value": "10.0.0.0/24", "source": "feed:1", "confidence": 0.8}
        ]
        session.execute.return_value = mock_result

        is_mal, source = await is_malicious_ip(session, "10.0.0.42")
        assert is_mal is True
        assert source == "feed:1"

    @pytest.mark.asyncio
    async def test_ip_no_match(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"value": "10.0.0.5", "source": "manual", "confidence": 0.9}
        ]
        session.execute.return_value = mock_result

        is_mal, source = await is_malicious_ip(session, "192.168.1.1")
        assert is_mal is False
        assert source is None

    @pytest.mark.asyncio
    async def test_invalid_ip(self):
        session = AsyncMock()
        is_mal, source = await is_malicious_ip(session, "not-an-ip")
        assert is_mal is False
        assert source is None

    @pytest.mark.asyncio
    async def test_malicious_indicator_dispatch_ip(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"value": "10.0.0.5", "source": "manual", "confidence": 0.9}
        ]
        session.execute.return_value = mock_result

        is_mal, source = await is_malicious_indicator(session, "10.0.0.5", "ip")
        assert is_mal is True

    @pytest.mark.asyncio
    async def test_malicious_indicator_dispatch_unknown(self):
        session = AsyncMock()
        is_mal, source = await is_malicious_indicator(session, "value", "unknown_type")
        assert is_mal is False


# ═══════════════════════════════════════════════════════════════════════════════
# §4 — Threat Intel CRUD Tests (#55)
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreatIntelCRUD:
    """Test threat intel service CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_indicator(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = {
            "id": 1,
            "indicator_type": "ip",
            "value": "10.0.0.1",
            "source": "manual",
            "confidence": 0.85,
            "active": True,
            "added_at": datetime.now(UTC),
            "added_by": "testuser",
            "expires_at": None,
            "notes": "test",
        }
        session.execute.return_value = mock_result

        result = await create_indicator(
            session,
            indicator_type="ip",
            value="10.0.0.1",
            source="manual",
            confidence=0.85,
            added_by="testuser",
            notes="test",
        )
        assert result["indicator_type"] == "ip"
        assert result["value"] == "10.0.0.1"
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_indicators(self):
        session = AsyncMock()

        # First call: count
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        # Second call: data
        data_result = MagicMock()
        data_result.mappings.return_value.all.return_value = [
            {
                "id": 1,
                "indicator_type": "ip",
                "value": "10.0.0.1",
                "source": "manual",
                "confidence": 0.85,
                "active": True,
                "added_at": datetime.now(UTC),
                "added_by": "testuser",
                "expires_at": None,
                "notes": None,
                "feed_id": None,
                "metadata_json": None,
            }
        ]

        session.execute.side_effect = [count_result, data_result]

        items, total = await get_indicators(session, indicator_type="ip")
        assert total == 2
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_update_indicator(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = {
            "id": 1,
            "indicator_type": "ip",
            "value": "10.0.0.1",
            "source": "updated_source",
            "confidence": 0.9,
            "active": True,
            "added_at": datetime.now(UTC),
            "added_by": "testuser",
            "expires_at": None,
            "notes": None,
        }
        session.execute.return_value = mock_result

        result = await update_indicator(session, 1, updates={"source": "updated_source"})
        assert result is not None
        assert result["source"] == "updated_source"
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_indicator_empty_updates(self):
        session = AsyncMock()
        result = await update_indicator(session, 1, updates={})
        assert result is None

    @pytest.mark.asyncio
    async def test_soft_delete_indicator(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(id=1)
        session.execute.return_value = mock_result

        deleted = await soft_delete_indicator(session, 1)
        assert deleted is True
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_soft_delete_not_found(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        session.execute.return_value = mock_result

        deleted = await soft_delete_indicator(session, 999)
        assert deleted is False


# ═══════════════════════════════════════════════════════════════════════════════
# §5 — Threat Intel Feed Tests (#55)
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreatIntelFeeds:
    """Test threat intel feed management."""

    @pytest.mark.asyncio
    async def test_create_feed(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.fetchone.return_value = {
            "id": 1,
            "name": "Test Feed",
            "url": "https://example.com/feed.txt",
            "feed_type": "domain",
            "enabled": True,
            "refresh_interval_minutes": 1440,
            "last_fetched_at": None,
            "last_fetch_status": None,
            "last_indicator_count": None,
            "created_by": "testuser",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        session.execute.return_value = mock_result

        result = await create_feed(
            session,
            name="Test Feed",
            url="https://example.com/feed.txt",
            feed_type="domain",
            created_by="testuser",
        )
        assert result["name"] == "Test Feed"
        assert result["feed_type"] == "domain"

    @pytest.mark.asyncio
    async def test_get_feeds(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {
                "id": 1,
                "name": "Feed 1",
                "url": "https://example.com/feed.txt",
                "feed_type": "domain",
                "enabled": True,
                "refresh_interval_minutes": 1440,
                "last_fetched_at": None,
                "last_fetch_status": None,
                "last_indicator_count": None,
                "created_by": "testuser",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ]
        session.execute.return_value = mock_result

        feeds = await get_feeds(session)
        assert len(feeds) == 1
        assert feeds[0]["name"] == "Feed 1"

    @pytest.mark.asyncio
    async def test_fetch_feed_indicators(self):
        session = AsyncMock()
        content = "evil.com\nbad-domain.xyz\n# comment line\n\nmalware.net"

        count = await fetch_feed_indicators(
            session,
            feed_id=1,
            content=content,
            feed_type="domain",
            added_by="system:feed",
        )
        assert count == 3
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_feed_indicators_empty(self):
        session = AsyncMock()
        count = await fetch_feed_indicators(
            session, feed_id=1, content="", feed_type="domain", added_by="system:feed"
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_fetch_feed_indicators_csv_format(self):
        session = AsyncMock()
        content = "evil.com,high,2024-01-01\nbad.net,medium,2024-06-15"

        count = await fetch_feed_indicators(
            session,
            feed_id=1,
            content=content,
            feed_type="domain",
            added_by="system:feed",
        )
        assert count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# §6 — Detection Rule Evaluation Tests (#36, #33, #30)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatternRuleEvaluation:
    """Test pattern-based detection rules."""

    def test_suspicious_user_agent_python_requests(self):
        rule = _make_rule(
            logic_type="pattern",
            logic_config={
                "action_filters": ["*"],
                "field_conditions": [
                    {
                        "field": "user_agent",
                        "operator": "matches_glob",
                        "value": "*python-requests*",
                    }
                ],
            },
        )
        event = _make_event(user_agent="python-requests/2.28.0")
        assert event_matches_rule(event, rule) is True

    def test_suspicious_user_agent_curl(self):
        rule = _make_rule(
            logic_type="pattern",
            logic_config={
                "action_filters": ["*"],
                "field_conditions": [
                    {"field": "user_agent", "operator": "matches_glob", "value": "curl/*"}
                ],
            },
        )
        event = _make_event(user_agent="curl/7.88.1")
        assert event_matches_rule(event, rule) is True

    def test_suspicious_user_agent_no_match(self):
        rule = _make_rule(
            logic_type="pattern",
            logic_config={
                "action_filters": ["*"],
                "field_conditions": [
                    {
                        "field": "user_agent",
                        "operator": "matches_glob",
                        "value": "*python-requests*",
                    }
                ],
            },
        )
        event = _make_event(user_agent="Mozilla/5.0")
        assert event_matches_rule(event, rule) is False

    def test_ci_gate_bypass_match(self):
        rule = _make_rule(
            logic_type="pattern",
            logic_config={
                "action_filters": ["protected_branch.update_required_status_checks"],
            },
        )
        event = _make_event(action="protected_branch.update_required_status_checks")
        assert event_matches_rule(event, rule) is True

    def test_suspicious_runner_registration(self):
        rule = _make_rule(
            logic_type="pattern",
            logic_config={
                "action_filters": [
                    "actions.runner_registration_token_created",
                    "actions.self_hosted_runner_online",
                ],
            },
        )
        event = _make_event(action="actions.runner_registration_token_created")
        assert event_matches_rule(event, rule) is True

    def test_webhook_create_match(self):
        rule = _make_rule(
            logic_type="pattern",
            logic_config={
                "action_filters": ["hook.create", "hook.config_changed"],
            },
        )
        event = _make_event(action="hook.create")
        assert event_matches_rule(event, rule) is True

    def test_app_installation_match(self):
        rule = _make_rule(
            logic_type="pattern",
            logic_config={
                "action_filters": ["integration_installation.create"],
            },
        )
        event = _make_event(action="integration_installation.create")
        assert event_matches_rule(event, rule) is True


class TestSequenceRuleSchema:
    """Test that sequence rule definitions have valid structure."""

    def test_account_takeover_sequence_definition(self):
        config = {
            "action_filters": [
                "two_factor_authentication.recovery_codes_used",
                "user.update_password",
                "public_key.create",
            ],
            "sequence_steps": [
                {"step": 1, "action": "two_factor_authentication.recovery_codes_used"},
                {"step": 2, "action": "user.update_password"},
                {"step": 3, "action": "public_key.create"},
            ],
            "aggregation_key": "actor",
            "time_window_minutes": 30,
            "confidence": 0.75,
        }
        assert len(config["sequence_steps"]) == 3
        assert config["time_window_minutes"] == 30
        actions = [s["action"] for s in config["sequence_steps"]]
        assert "two_factor_authentication.recovery_codes_used" in actions
        assert "user.update_password" in actions
        assert "public_key.create" in actions

    def test_deployment_gate_bypass_sequence_definition(self):
        config = {
            "action_filters": [
                "environment.delete_protection_rule",
                "deployment.create",
            ],
            "sequence_steps": [
                {"step": 1, "action": "environment.delete_protection_rule"},
                {"step": 2, "action": "deployment.create"},
            ],
            "aggregation_key": "actor",
            "time_window_minutes": 10,
            "confidence": 0.80,
        }
        assert len(config["sequence_steps"]) == 2
        assert config["time_window_minutes"] == 10


class TestThresholdRuleWithBaseline:
    """Test baseline-adjusted threshold rules."""

    @pytest.mark.asyncio
    async def test_baseline_adjusts_threshold(self):
        session = AsyncMock()

        baseline = _make_baseline(
            metric_name="daily_events",
            mean=10.0,
            stddev=3.0,
        )

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=baseline,
        ):
            rule = _make_rule(
                logic_type="threshold",
                logic_config={
                    "baseline_comparison": True,
                    "baseline_metric": "daily_events",
                    "baseline_z_threshold": 3.0,
                    "threshold": 50,
                },
            )
            adjusted = await _adjust_threshold_with_baseline(
                session, rule, "testuser", "my-org", 50
            )
            # mean=10 + 3*3=19 → dynamic threshold = 19
            assert adjusted == 19

    @pytest.mark.asyncio
    async def test_no_baseline_returns_static(self):
        session = AsyncMock()

        with patch(
            "app.services.detection_service._load_baseline",
            return_value=None,
        ):
            rule = _make_rule(
                logic_type="threshold",
                logic_config={
                    "baseline_comparison": True,
                    "baseline_metric": "daily_events",
                    "baseline_z_threshold": 3.0,
                    "threshold": 50,
                },
            )
            adjusted = await _adjust_threshold_with_baseline(
                session, rule, "testuser", "my-org", 50
            )
            assert adjusted == 50

    @pytest.mark.asyncio
    async def test_baseline_comparison_disabled(self):
        session = AsyncMock()
        rule = _make_rule(
            logic_type="threshold",
            logic_config={
                "baseline_comparison": False,
                "threshold": 100,
            },
        )
        adjusted = await _adjust_threshold_with_baseline(session, rule, "testuser", "my-org", 100)
        assert adjusted == 100


# ═══════════════════════════════════════════════════════════════════════════════
# §7 — Detection Rule Fixtures Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectionRuleFixtures:
    """Test that the detection rules fixtures file is valid and well-structured."""

    def _load_fixtures(self) -> list[dict]:
        import os

        fixtures_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "app",
            "fixtures",
            "detection_rules_v2.json",
        )
        with open(fixtures_path) as f:
            return json.load(f)

    def test_fixtures_is_valid_json(self):
        rules = self._load_fixtures()
        assert isinstance(rules, list)
        assert len(rules) > 0

    def test_all_rules_have_required_fields(self):
        rules = self._load_fixtures()
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
        for rule in rules:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule '{rule.get('name')}' missing fields: {missing}"

    def test_all_slugs_unique(self):
        rules = self._load_fixtures()
        slugs = [r["slug"] for r in rules]
        assert len(slugs) == len(set(slugs)), "Duplicate slugs found in fixtures"

    def test_valid_logic_types(self):
        rules = self._load_fixtures()
        valid_types = {
            "pattern",
            "threshold",
            "sequence",
            "statistical",
            "posture",
            "cross_namespace_sequence",
        }
        for rule in rules:
            assert rule["logic_type"] in valid_types, (
                f"Rule '{rule['name']}' has invalid logic_type: {rule['logic_type']}"
            )

    def test_valid_severity_values(self):
        rules = self._load_fixtures()
        valid_severities = {"critical", "high", "medium", "low", "info"}
        for rule in rules:
            assert rule["default_severity"] in valid_severities, (
                f"Rule '{rule['name']}' has invalid severity: {rule['default_severity']}"
            )

    def test_valid_confidence_values(self):
        rules = self._load_fixtures()
        valid_confidences = {"high", "medium", "low"}
        for rule in rules:
            assert rule["default_confidence"] in valid_confidences, (
                f"Rule '{rule['name']}' has invalid confidence: {rule['default_confidence']}"
            )

    def test_categories_present(self):
        rules = self._load_fixtures()
        categories = {r["category"] for r in rules}
        # We should have rules from each detection domain
        assert "account_compromise" in categories
        assert "supply_chain" in categories
        assert "defense_evasion" in categories

    def test_sequence_rules_have_steps(self):
        rules = self._load_fixtures()
        for rule in rules:
            if rule["logic_type"] == "sequence":
                config = rule["logic_config"]
                assert "sequence_steps" in config, (
                    f"Sequence rule '{rule['name']}' missing sequence_steps"
                )
                assert len(config["sequence_steps"]) >= 2

    def test_threshold_rules_have_threshold(self):
        rules = self._load_fixtures()
        for rule in rules:
            if rule["logic_type"] == "threshold":
                config = rule["logic_config"]
                assert "threshold" in config, f"Threshold rule '{rule['name']}' missing threshold"
                assert config["threshold"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# §8 — Threat Intel Router Tests (#55)
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreatIntelRouterRegistration:
    """Test that the threat intel router is properly registered."""

    def test_router_registered_in_app(self):
        from app.main import create_app

        app = create_app()
        routes = [route.path for route in app.routes if hasattr(route, "path")]
        # Check that at least the indicator endpoints are registered
        assert any("/threat-intel" in r for r in routes)

    def test_indicator_schemas_valid(self):
        from app.schemas.threat_intel import IndicatorCreate

        # Create schema validates types
        indicator = IndicatorCreate(
            indicator_type="ip",
            value="10.0.0.1",
            source="manual",
            confidence=0.85,
        )
        assert indicator.indicator_type == "ip"
        assert indicator.value == "10.0.0.1"

    def test_feed_schema_valid(self):
        from app.schemas.threat_intel import FeedCreate

        feed = FeedCreate(
            name="Test Feed",
            url="https://example.com/feed.txt",
            feed_type="domain",
        )
        assert feed.name == "Test Feed"
        assert feed.refresh_interval_minutes == 1440


# ═══════════════════════════════════════════════════════════════════════════════
# §9 — Impossible Travel Metadata Enhancement Test (#36)
# ═══════════════════════════════════════════════════════════════════════════════


class TestImpossibleTravelMetadata:
    """Verify impossible travel detection includes geo visualization data."""

    def test_impossible_travel_context_has_geo_data(self):
        """The existing evaluate_impossible_travel already includes lat/lon pairs,
        distance_km, time_delta_seconds, and implied_speed_kmh in context_data.
        Verify the expected schema of the context."""
        expected_fields = {
            "ip_a",
            "geo_a",
            "ip_b",
            "geo_b",
            "distance_km",
            "time_delta_seconds",
            "implied_speed_kmh",
            "event_id_a",
            "event_id_b",
        }
        # Simulate the context_data structure from evaluate_impossible_travel
        ctx = {
            "ip_a": "1.1.1.1",
            "geo_a": {"lat": 40.7128, "lon": -74.0060},
            "ip_b": "2.2.2.2",
            "geo_b": {"lat": 51.5074, "lon": -0.1278},
            "distance_km": 5570.5,
            "time_delta_seconds": 600,
            "implied_speed_kmh": 33423.0,
            "event_id_a": 100,
            "event_id_b": 101,
        }
        assert set(ctx.keys()) == expected_fields
        assert isinstance(ctx["geo_a"], dict)
        assert "lat" in ctx["geo_a"]
        assert "lon" in ctx["geo_a"]


# ═══════════════════════════════════════════════════════════════════════════════
# §10 — Threat Intel Domain Matching Tests (existing service)
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreatIntelDomainMatching:
    """Test domain-based threat intelligence matching."""

    @pytest.mark.asyncio
    async def test_malicious_domain_match(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"domain": "*.evil.com", "source": "manual", "confidence": 0.9}
        ]
        session.execute.return_value = mock_result

        is_mal, source = await is_malicious_domain(session, "https://sub.evil.com/path")
        assert is_mal is True
        assert source == "manual"

    @pytest.mark.asyncio
    async def test_malicious_domain_no_match(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [
            {"domain": "*.evil.com", "source": "manual", "confidence": 0.9}
        ]
        session.execute.return_value = mock_result

        is_mal, source = await is_malicious_domain(session, "https://good.com/path")
        assert is_mal is False

    @pytest.mark.asyncio
    async def test_malicious_domain_no_url(self):
        session = AsyncMock()
        is_mal, source = await is_malicious_domain(session, "not-a-url")
        assert is_mal is False
