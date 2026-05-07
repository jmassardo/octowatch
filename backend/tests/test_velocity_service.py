"""Tests for the velocity service module.

Tests cover:
- DORA benchmark classification functions
- Trend calculation helper
- LeadershipSummary dataclass construction
- TeamMetrics dataclass construction
- CadenceDay dataclass construction
"""

from __future__ import annotations

import pytest

from app.services.velocity_service import (
    CadenceDay,
    DoraTier,
    LeadershipSummary,
    MetricWithTrend,
    TeamMetrics,
    _compute_trend,
    classify_change_failure_rate,
    classify_deploy_frequency,
    classify_lead_time,
    classify_mttr,
)

# ── DORA Classification Tests ─────────────────────────────────────────────────


class TestClassifyDeployFrequency:
    def test_elite_multiple_per_day(self) -> None:
        assert classify_deploy_frequency(2.0) == DoraTier.ELITE

    def test_elite_boundary(self) -> None:
        assert classify_deploy_frequency(1.5) == DoraTier.ELITE

    def test_high_daily(self) -> None:
        assert classify_deploy_frequency(0.5) == DoraTier.HIGH

    def test_high_boundary(self) -> None:
        result = classify_deploy_frequency(1 / 7)
        assert result == DoraTier.HIGH

    def test_medium_weekly(self) -> None:
        assert classify_deploy_frequency(0.1) == DoraTier.MEDIUM

    def test_medium_boundary(self) -> None:
        result = classify_deploy_frequency(1 / 30)
        assert result == DoraTier.MEDIUM

    def test_low_monthly_plus(self) -> None:
        assert classify_deploy_frequency(0.01) == DoraTier.LOW

    def test_low_zero(self) -> None:
        assert classify_deploy_frequency(0) == DoraTier.LOW


class TestClassifyLeadTime:
    def test_elite_under_1h(self) -> None:
        assert classify_lead_time(0.5) == DoraTier.ELITE

    def test_high_under_1d(self) -> None:
        assert classify_lead_time(12) == DoraTier.HIGH

    def test_high_boundary(self) -> None:
        assert classify_lead_time(1) == DoraTier.HIGH

    def test_medium_under_1w(self) -> None:
        assert classify_lead_time(48) == DoraTier.MEDIUM

    def test_medium_boundary(self) -> None:
        assert classify_lead_time(24) == DoraTier.MEDIUM

    def test_low_over_1w(self) -> None:
        assert classify_lead_time(200) == DoraTier.LOW

    def test_low_boundary(self) -> None:
        assert classify_lead_time(168) == DoraTier.LOW


class TestClassifyChangeFailureRate:
    def test_elite_under_5(self) -> None:
        assert classify_change_failure_rate(3.0) == DoraTier.ELITE

    def test_high_under_10(self) -> None:
        assert classify_change_failure_rate(7.0) == DoraTier.HIGH

    def test_medium_under_15(self) -> None:
        assert classify_change_failure_rate(12.0) == DoraTier.MEDIUM

    def test_low_over_15(self) -> None:
        assert classify_change_failure_rate(20.0) == DoraTier.LOW

    def test_elite_zero(self) -> None:
        assert classify_change_failure_rate(0) == DoraTier.ELITE

    def test_boundary_5(self) -> None:
        assert classify_change_failure_rate(5.0) == DoraTier.HIGH

    def test_boundary_10(self) -> None:
        assert classify_change_failure_rate(10.0) == DoraTier.MEDIUM

    def test_boundary_15(self) -> None:
        assert classify_change_failure_rate(15.0) == DoraTier.LOW


class TestClassifyMttr:
    def test_elite_under_1h(self) -> None:
        assert classify_mttr(0.5) == DoraTier.ELITE

    def test_high_under_1d(self) -> None:
        assert classify_mttr(6.0) == DoraTier.HIGH

    def test_medium_under_1w(self) -> None:
        assert classify_mttr(72.0) == DoraTier.MEDIUM

    def test_low_over_1w(self) -> None:
        assert classify_mttr(200.0) == DoraTier.LOW


# ── Trend Calculation Tests ───────────────────────────────────────────────────


class TestComputeTrend:
    def test_positive_trend(self) -> None:
        assert _compute_trend(15.0, 10.0) == 50.0

    def test_negative_trend(self) -> None:
        assert _compute_trend(8.0, 10.0) == -20.0

    def test_zero_previous_returns_zero(self) -> None:
        assert _compute_trend(10.0, 0.0) == 0.0

    def test_no_change(self) -> None:
        assert _compute_trend(10.0, 10.0) == 0.0

    def test_large_increase(self) -> None:
        assert _compute_trend(100.0, 10.0) == 900.0

    def test_decrease_to_zero(self) -> None:
        assert _compute_trend(0.0, 10.0) == -100.0


# ── Dataclass Construction Tests ──────────────────────────────────────────────


class TestMetricWithTrend:
    def test_construction(self) -> None:
        m = MetricWithTrend(
            value=2.5,
            previous_value=2.0,
            trend_pct=25.0,
            classification="elite",
        )
        assert m.value == 2.5
        assert m.previous_value == 2.0
        assert m.trend_pct == 25.0
        assert m.classification == "elite"

    def test_frozen(self) -> None:
        m = MetricWithTrend(
            value=1.0,
            previous_value=0.5,
            trend_pct=100.0,
            classification="high",
        )
        with pytest.raises(AttributeError):
            m.value = 99  # type: ignore[misc]


class TestLeadershipSummary:
    def test_construction(self) -> None:
        metric = MetricWithTrend(
            value=1.0,
            previous_value=0.5,
            trend_pct=100.0,
            classification="high",
        )
        summary = LeadershipSummary(
            deployment_frequency=metric,
            lead_time=metric,
            change_failure_rate=metric,
            mttr=metric,
            pr_throughput=metric,
            active_contributors=metric,
            period_days=30,
        )
        assert summary.period_days == 30
        assert summary.deployment_frequency.value == 1.0


class TestTeamMetrics:
    def test_construction(self) -> None:
        t = TeamMetrics(team="my-org", value=2.5, classification="elite")
        assert t.team == "my-org"
        assert t.value == 2.5
        assert t.classification == "elite"


class TestCadenceDay:
    def test_construction(self) -> None:
        c = CadenceDay(date="2024-01-15", deployments=5, merges=3, reviews=10)
        assert c.date == "2024-01-15"
        assert c.deployments == 5
        assert c.merges == 3
        assert c.reviews == 10


# ── DoraTier Enum Tests ───────────────────────────────────────────────────────


class TestDoraTier:
    def test_values(self) -> None:
        assert DoraTier.ELITE.value == "elite"
        assert DoraTier.HIGH.value == "high"
        assert DoraTier.MEDIUM.value == "medium"
        assert DoraTier.LOW.value == "low"

    def test_is_enum(self) -> None:
        assert isinstance(DoraTier.ELITE, DoraTier)
        assert DoraTier.ELITE.value == "elite"
