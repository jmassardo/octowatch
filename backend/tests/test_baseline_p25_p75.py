"""Tests for P25/P75 percentile computation in the baseline worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workers.baseline_worker import (
    _compute_utilization_baselines,
    _percentile,
    _upsert_baseline,
)


class TestPercentileFunction:
    """Tests for the _percentile helper."""

    def test_p25_simple(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        result = _percentile(values, 25)
        # 25th percentile of [1..8]: index = 0.25 * 7 = 1.75 -> lerp(2, 3, 0.75) = 2.75
        assert result == pytest.approx(2.75, abs=0.01)

    def test_p75_simple(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        result = _percentile(values, 75)
        # 75th percentile: index = 0.75 * 7 = 5.25 -> lerp(6, 7, 0.25) = 6.25
        assert result == pytest.approx(6.25, abs=0.01)

    def test_p25_single_value(self) -> None:
        values = [42.0]
        assert _percentile(values, 25) == 42.0

    def test_p75_single_value(self) -> None:
        values = [42.0]
        assert _percentile(values, 75) == 42.0

    def test_empty_list_returns_zero(self) -> None:
        assert _percentile([], 25) == 0.0
        assert _percentile([], 75) == 0.0

    def test_unsorted_input_still_works(self) -> None:
        values = [5.0, 1.0, 3.0, 2.0, 4.0]
        # Should sort internally: [1, 2, 3, 4, 5]
        p25 = _percentile(values, 25)
        p75 = _percentile(values, 75)
        assert p25 == pytest.approx(2.0, abs=0.01)
        assert p75 == pytest.approx(4.0, abs=0.01)

    def test_p25_less_than_p75(self) -> None:
        values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
        assert _percentile(values, 25) < _percentile(values, 75)


class TestUpsertBaselineP25P75:
    """Tests for _upsert_baseline with p25/p75 parameters."""

    @pytest.mark.asyncio
    async def test_upsert_baseline_with_p25_p75(self) -> None:
        """Verify _upsert_baseline passes p25/p75 to SQL execution."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=30)

        await _upsert_baseline(
            mock_session,
            baseline_type="actor",
            scope_key="actor:alice:org:acme",
            metric_name="daily_events",
            window_start=cutoff,
            window_end=now,
            mean=10.5,
            stddev=2.3,
            p25=5.0,
            p75=15.0,
            p95=20.0,
            p99=25.0,
            sample_count=30,
        )

        mock_session.execute.assert_called_once()
        call_args = mock_session.execute.call_args
        params = call_args[0][1]

        assert params["p25"] == 5.0
        assert params["p75"] == 15.0
        assert params["mean"] == 10.5
        assert params["stddev"] == 2.3
        assert params["p95"] == 20.0
        assert params["p99"] == 25.0
        assert params["sample_count"] == 30
        assert params["baseline_type"] == "actor"
        assert params["scope_key"] == "actor:alice:org:acme"
        assert params["metric_name"] == "daily_events"

    @pytest.mark.asyncio
    async def test_upsert_baseline_p25_p75_default_none(self) -> None:
        """Verify p25/p75 default to None when not provided."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=30)

        await _upsert_baseline(
            mock_session,
            baseline_type="org",
            scope_key="org:acme",
            metric_name="daily_ips",
            window_start=cutoff,
            window_end=now,
            mean=5.0,
            stddev=1.0,
            p95=10.0,
            p99=12.0,
            sample_count=20,
        )

        call_args = mock_session.execute.call_args
        params = call_args[0][1]

        assert params["p25"] is None
        assert params["p75"] is None

    @pytest.mark.asyncio
    async def test_upsert_baseline_sql_includes_p25_p75_columns(self) -> None:
        """Verify the SQL statement references p25 and p75 columns."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=30)

        await _upsert_baseline(
            mock_session,
            baseline_type="utilization",
            scope_key="acme/alice",
            metric_name="copilot.copilot_suggestions",
            window_start=cutoff,
            window_end=now,
            mean=100.0,
            stddev=20.0,
            p25=80.0,
            p75=120.0,
            p95=150.0,
            p99=180.0,
            sample_count=14,
        )

        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0].text)

        assert "p25" in sql_text
        assert "p75" in sql_text
        assert ":p25" in sql_text
        assert ":p75" in sql_text


class TestComputeUtilizationBaselines:
    """Tests for _compute_utilization_baselines."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_combos(self) -> None:
        """Returns 0 when no actor/org/feature combos have enough data."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await _compute_utilization_baselines(mock_session)

        assert result == 0

    @pytest.mark.asyncio
    async def test_processes_qualifying_combos(self) -> None:
        """Computes baselines for combos with >= 14 days of data."""
        mock_session = AsyncMock()

        # First call returns combos, subsequent calls return metric stats
        combo_row = MagicMock()
        combo_row.org_slug = "acme-corp"
        combo_row.actor_login = "alice"
        combo_row.feature_area = "copilot"
        combo_row.day_count = 20

        combo_result = MagicMock()
        combo_result.fetchall.return_value = [combo_row]

        metric_row = MagicMock()
        metric_row.mean_val = 50.0
        metric_row.stddev_val = 10.0
        metric_row.p25 = 40.0
        metric_row.p75 = 60.0
        metric_row.p95 = 75.0
        metric_row.p99 = 90.0
        metric_row.sample_count = 20

        metric_result = MagicMock()
        metric_result.fetchone.return_value = metric_row

        # Upsert call returns a generic result
        upsert_result = MagicMock()

        # combo_query + (metric_query + upsert) * 9 = 1 + 18 = 19 calls
        side_effects: list[MagicMock] = [combo_result]
        for _ in range(9):
            side_effects.append(metric_result)
            side_effects.append(upsert_result)
        mock_session.execute = AsyncMock(side_effect=side_effects)

        result = await _compute_utilization_baselines(mock_session)

        # 9 metrics for 1 combo = 9 baselines written
        assert result == 9

    @pytest.mark.asyncio
    async def test_skips_metrics_with_no_data(self) -> None:
        """Skips metrics where sample_count is 0 or mean is None."""
        mock_session = AsyncMock()

        combo_row = MagicMock()
        combo_row.org_slug = "acme-corp"
        combo_row.actor_login = "bob"
        combo_row.feature_area = "actions"
        combo_row.day_count = 15

        combo_result = MagicMock()
        combo_result.fetchall.return_value = [combo_row]

        # Metric with no data
        empty_metric_row = MagicMock()
        empty_metric_row.mean_val = None
        empty_metric_row.stddev_val = None
        empty_metric_row.p25 = None
        empty_metric_row.p75 = None
        empty_metric_row.p95 = None
        empty_metric_row.p99 = None
        empty_metric_row.sample_count = 0

        empty_result = MagicMock()
        empty_result.fetchone.return_value = empty_metric_row

        # Metric with data
        valid_metric_row = MagicMock()
        valid_metric_row.mean_val = 100.0
        valid_metric_row.stddev_val = 15.0
        valid_metric_row.p25 = 85.0
        valid_metric_row.p75 = 115.0
        valid_metric_row.p95 = 140.0
        valid_metric_row.p99 = 160.0
        valid_metric_row.sample_count = 15

        valid_result = MagicMock()
        valid_result.fetchone.return_value = valid_metric_row

        upsert_result = MagicMock()

        # combo_query + empty_metric + (valid_metric + upsert) * 8 = 1 + 1 + 16 = 18
        side_effects: list[MagicMock] = [combo_result, empty_result]
        for _ in range(8):
            side_effects.append(valid_result)
            side_effects.append(upsert_result)
        mock_session.execute = AsyncMock(side_effect=side_effects)

        result = await _compute_utilization_baselines(mock_session)

        # 8 metrics written (1 skipped due to no data)
        assert result == 8

    @pytest.mark.asyncio
    async def test_scope_key_format(self) -> None:
        """Verify scope_key is formatted as '{org_slug}/{actor_login}'."""
        mock_session = AsyncMock()

        combo_row = MagicMock()
        combo_row.org_slug = "my-org"
        combo_row.actor_login = "developer1"
        combo_row.feature_area = "git"
        combo_row.day_count = 14

        combo_result = MagicMock()
        combo_result.fetchall.return_value = [combo_row]

        metric_row = MagicMock()
        metric_row.mean_val = 5.0
        metric_row.stddev_val = 2.0
        metric_row.p25 = 3.0
        metric_row.p75 = 7.0
        metric_row.p95 = 10.0
        metric_row.p99 = 12.0
        metric_row.sample_count = 14

        metric_result = MagicMock()
        metric_result.fetchone.return_value = metric_row

        upsert_result = MagicMock()

        side_effects: list[MagicMock] = [combo_result]
        for _ in range(9):
            side_effects.append(metric_result)
            side_effects.append(upsert_result)
        mock_session.execute = AsyncMock(side_effect=side_effects)

        await _compute_utilization_baselines(mock_session)

        # Find upsert calls (those with scope_key in params dict)
        all_calls = mock_session.execute.call_args_list
        upsert_calls = [
            c
            for c in all_calls
            if len(c[0]) > 1 and isinstance(c[0][1], dict) and "scope_key" in c[0][1]
        ]
        assert len(upsert_calls) > 0
        assert upsert_calls[0][0][1]["scope_key"] == "my-org/developer1"

    @pytest.mark.asyncio
    async def test_metric_name_format(self) -> None:
        """Verify metric_name is formatted as '{feature_area}.{metric}'."""
        mock_session = AsyncMock()

        combo_row = MagicMock()
        combo_row.org_slug = "org1"
        combo_row.actor_login = "user1"
        combo_row.feature_area = "actions"
        combo_row.day_count = 14

        combo_result = MagicMock()
        combo_result.fetchall.return_value = [combo_row]

        metric_row = MagicMock()
        metric_row.mean_val = 10.0
        metric_row.stddev_val = 3.0
        metric_row.p25 = 7.0
        metric_row.p75 = 13.0
        metric_row.p95 = 18.0
        metric_row.p99 = 22.0
        metric_row.sample_count = 20

        metric_result = MagicMock()
        metric_result.fetchone.return_value = metric_row

        upsert_result = MagicMock()

        side_effects: list[MagicMock] = [combo_result]
        for _ in range(9):
            side_effects.append(metric_result)
            side_effects.append(upsert_result)
        mock_session.execute = AsyncMock(side_effect=side_effects)

        await _compute_utilization_baselines(mock_session)

        # Find upsert calls
        all_calls = mock_session.execute.call_args_list
        upsert_calls = [
            c
            for c in all_calls
            if len(c[0]) > 1 and isinstance(c[0][1], dict) and "metric_name" in c[0][1]
        ]
        # First metric in the list is actions_minutes
        assert upsert_calls[0][0][1]["metric_name"] == "actions.actions_minutes"
        assert upsert_calls[0][0][1]["baseline_type"] == "utilization"

    @pytest.mark.asyncio
    async def test_stddev_none_defaults_to_zero(self) -> None:
        """When stddev_val is None (single sample), default to 0.0."""
        mock_session = AsyncMock()

        combo_row = MagicMock()
        combo_row.org_slug = "org1"
        combo_row.actor_login = "user1"
        combo_row.feature_area = "copilot"
        combo_row.day_count = 14

        combo_result = MagicMock()
        combo_result.fetchall.return_value = [combo_row]

        metric_row = MagicMock()
        metric_row.mean_val = 10.0
        metric_row.stddev_val = None  # Can happen with single non-null value
        metric_row.p25 = 10.0
        metric_row.p75 = 10.0
        metric_row.p95 = 10.0
        metric_row.p99 = 10.0
        metric_row.sample_count = 1

        metric_result = MagicMock()
        metric_result.fetchone.return_value = metric_row

        # Only first metric has data, rest return None mean
        empty_row = MagicMock()
        empty_row.mean_val = None
        empty_row.sample_count = 0
        empty_result = MagicMock()
        empty_result.fetchone.return_value = empty_row

        upsert_result = MagicMock()

        # combo_query + metric_query (valid) + upsert + 8 * empty_metric = 11
        side_effects: list[MagicMock] = [
            combo_result,
            metric_result,
            upsert_result,
        ]
        for _ in range(8):
            side_effects.append(empty_result)
        mock_session.execute = AsyncMock(side_effect=side_effects)

        result = await _compute_utilization_baselines(mock_session)
        assert result == 1

        # Find the upsert call
        all_calls = mock_session.execute.call_args_list
        upsert_calls = [
            c
            for c in all_calls
            if len(c[0]) > 1 and isinstance(c[0][1], dict) and "stddev" in c[0][1]
        ]
        assert upsert_calls[0][0][1]["stddev"] == 0.0
