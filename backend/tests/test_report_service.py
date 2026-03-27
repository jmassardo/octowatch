"""Unit tests for report service: verify correct SQL construction patterns."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.report_service import (
    _bucket_interval,
    _window_start,
    get_copilot_seats_report,
    get_mau_report,
    get_repo_creation_rate_report,
    get_seat_utilization_report,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(**kwargs: object) -> MagicMock:
    """Create a MagicMock that behaves like a SQLAlchemy Row with named attrs."""
    row = MagicMock()
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def _mock_session_with_results(
    *result_sets: list,
) -> AsyncMock:
    """Return an ``AsyncSession`` mock whose ``.execute()`` yields one result
    set per call.  Each result set is a list of mock rows returned by
    ``fetchall()`` (or ``fetchone()`` for single-row results).
    """
    session = AsyncMock()
    mocks = []
    for rows in result_sets:
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_result.fetchone.return_value = rows[0] if rows else None
        mocks.append(mock_result)
    session.execute = AsyncMock(side_effect=mocks)
    return session


# ---------------------------------------------------------------------------
# _bucket_interval
# ---------------------------------------------------------------------------


class TestBucketInterval:
    def test_daily(self) -> None:
        assert _bucket_interval("daily") == timedelta(days=1)

    def test_weekly(self) -> None:
        assert _bucket_interval("weekly") == timedelta(days=7)

    def test_monthly(self) -> None:
        assert _bucket_interval("monthly") == timedelta(days=30)

    def test_unknown_defaults_to_daily(self) -> None:
        assert _bucket_interval("unknown") == timedelta(days=1)


# ---------------------------------------------------------------------------
# _window_start
# ---------------------------------------------------------------------------


class TestWindowStart:
    def test_30_day_window(self) -> None:
        start = _window_start(30)
        now = datetime.now(UTC)
        diff = (now - start).total_seconds()
        # Should be approximately 30 days
        assert 29 * 86400 < diff < 31 * 86400

    def test_90_day_window(self) -> None:
        start = _window_start(90)
        now = datetime.now(UTC)
        diff = (now - start).total_seconds()
        assert 89 * 86400 < diff < 91 * 86400


# ---------------------------------------------------------------------------
# Smoke tests – verify functions call session.execute
# ---------------------------------------------------------------------------


class TestReportServiceMocked:
    """Smoke tests that verify report functions call the session correctly."""

    @pytest.mark.asyncio
    async def test_get_mau_report_executes_query(self) -> None:
        session = _mock_session_with_results([])

        result = await get_mau_report(session, window_days=30, granularity="daily")

        assert isinstance(result, list)
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_seat_utilization_report_executes_two_queries(self) -> None:
        """seat_utilization now issues two queries (max + per-bucket)."""
        max_row = _make_row(max_active=0)
        session = _mock_session_with_results([max_row], [])

        result = await get_seat_utilization_report(session)

        assert isinstance(result, list)
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_get_repo_creation_rate_report(self) -> None:
        session = _mock_session_with_results([])

        result = await get_repo_creation_rate_report(session)
        assert result == []

    @pytest.mark.asyncio
    async def test_org_filter_passed_to_query(self) -> None:
        session = _mock_session_with_results([])

        await get_mau_report(session, window_days=30, granularity="daily", org="my-org")

        call_args = session.execute.call_args
        params = call_args[0][1] if call_args[0] else call_args[1]
        # The org should appear in the params dict
        assert "org" in str(params) or "my-org" in str(params)


# ---------------------------------------------------------------------------
# get_seat_utilization_report – output shape
# ---------------------------------------------------------------------------


class TestSeatUtilizationReportShape:
    """Verify that the returned dicts match the frontend SeatUtilizationBucket."""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self) -> None:
        bucket_ts = datetime(2024, 6, 1, tzinfo=UTC)
        max_row = _make_row(max_active=10)
        data_row = _make_row(bucket=bucket_ts, org="acme", active_seats=8)
        session = _mock_session_with_results([max_row], [data_row])

        result = await get_seat_utilization_report(session)

        assert len(result) == 1
        item = result[0]
        assert set(item.keys()) == {
            "bucket",
            "active_seat_count",
            "provisioned_seat_count",
            "utilization_pct",
        }

    @pytest.mark.asyncio
    async def test_utilization_calculation(self) -> None:
        bucket_ts = datetime(2024, 6, 1, tzinfo=UTC)
        max_row = _make_row(max_active=20)
        data_row = _make_row(bucket=bucket_ts, org="acme", active_seats=15)
        session = _mock_session_with_results([max_row], [data_row])

        result = await get_seat_utilization_report(session)

        item = result[0]
        assert item["active_seat_count"] == 15
        assert item["provisioned_seat_count"] == 20
        assert item["utilization_pct"] == 75.0

    @pytest.mark.asyncio
    async def test_utilization_zero_when_no_provisioned(self) -> None:
        """When there are no events at all, provisioned is 0 and pct is 0.0."""
        max_row = _make_row(max_active=0)
        session = _mock_session_with_results([max_row], [])

        result = await get_seat_utilization_report(session)

        assert result == []

    @pytest.mark.asyncio
    async def test_bucket_is_iso_string(self) -> None:
        bucket_ts = datetime(2024, 7, 15, 12, 0, tzinfo=UTC)
        max_row = _make_row(max_active=5)
        data_row = _make_row(bucket=bucket_ts, org="corp", active_seats=5)
        session = _mock_session_with_results([max_row], [data_row])

        result = await get_seat_utilization_report(session)

        assert result[0]["bucket"] == bucket_ts.isoformat()

    @pytest.mark.asyncio
    async def test_multiple_buckets(self) -> None:
        ts1 = datetime(2024, 6, 1, tzinfo=UTC)
        ts2 = datetime(2024, 6, 2, tzinfo=UTC)
        max_row = _make_row(max_active=10)
        row1 = _make_row(bucket=ts1, org="acme", active_seats=5)
        row2 = _make_row(bucket=ts2, org="acme", active_seats=10)
        session = _mock_session_with_results([max_row], [row1, row2])

        result = await get_seat_utilization_report(session)

        assert len(result) == 2
        assert result[0]["utilization_pct"] == 50.0
        assert result[1]["utilization_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_utilization_rounds_to_one_decimal(self) -> None:
        bucket_ts = datetime(2024, 6, 1, tzinfo=UTC)
        max_row = _make_row(max_active=3)
        data_row = _make_row(bucket=bucket_ts, org="acme", active_seats=1)
        session = _mock_session_with_results([max_row], [data_row])

        result = await get_seat_utilization_report(session)

        # 1/3*100 = 33.333... → 33.3
        assert result[0]["utilization_pct"] == 33.3


# ---------------------------------------------------------------------------
# get_copilot_seats_report – output shape
# ---------------------------------------------------------------------------


class TestCopilotSeatsReportShape:
    """Verify that the returned dicts match the frontend CopilotSeatsBucket."""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self) -> None:
        bucket_ts = datetime(2024, 6, 1, tzinfo=UTC)
        row = _make_row(
            bucket=bucket_ts,
            org="acme",
            action="copilot.add_seats",
            seat_events=3,
        )
        session = _mock_session_with_results([row])

        result = await get_copilot_seats_report(session)

        assert len(result) == 1
        assert set(result[0].keys()) == {
            "bucket",
            "seats_assigned",
            "seats_revoked",
            "seats_net",
            "policy_change_count",
        }

    @pytest.mark.asyncio
    async def test_assign_actions_sum(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=UTC)
        rows = [
            _make_row(bucket=ts, org="o", action="copilot.add_seats", seat_events=5),
            _make_row(bucket=ts, org="o", action="copilot.seat_allotment_added", seat_events=2),
        ]
        session = _mock_session_with_results(rows)

        result = await get_copilot_seats_report(session)

        assert result[0]["seats_assigned"] == 7
        assert result[0]["seats_revoked"] == 0
        assert result[0]["seats_net"] == 7

    @pytest.mark.asyncio
    async def test_revoke_actions_sum(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=UTC)
        rows = [
            _make_row(bucket=ts, org="o", action="copilot.remove_seats", seat_events=3),
            _make_row(bucket=ts, org="o", action="copilot.seat_allotment_removed", seat_events=1),
        ]
        session = _mock_session_with_results(rows)

        result = await get_copilot_seats_report(session)

        assert result[0]["seats_revoked"] == 4
        assert result[0]["seats_assigned"] == 0
        assert result[0]["seats_net"] == -4

    @pytest.mark.asyncio
    async def test_policy_change_count(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=UTC)
        rows = [
            _make_row(bucket=ts, org="o", action="copilot.enable_organization", seat_events=2),
            _make_row(bucket=ts, org="o", action="copilot.disable_organization", seat_events=1),
        ]
        session = _mock_session_with_results(rows)

        result = await get_copilot_seats_report(session)

        assert result[0]["policy_change_count"] == 3
        # enable counts as both assign AND policy
        assert result[0]["seats_assigned"] == 2
        # disable counts as both revoke AND policy
        assert result[0]["seats_revoked"] == 1
        assert result[0]["seats_net"] == 1

    @pytest.mark.asyncio
    async def test_net_calculation_mixed(self) -> None:
        ts = datetime(2024, 6, 1, tzinfo=UTC)
        rows = [
            _make_row(bucket=ts, org="o", action="copilot.add_seats", seat_events=10),
            _make_row(bucket=ts, org="o", action="copilot.remove_seats", seat_events=4),
        ]
        session = _mock_session_with_results(rows)

        result = await get_copilot_seats_report(session)

        assert result[0]["seats_assigned"] == 10
        assert result[0]["seats_revoked"] == 4
        assert result[0]["seats_net"] == 6

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_results([])

        result = await get_copilot_seats_report(session)

        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_buckets(self) -> None:
        ts1 = datetime(2024, 6, 1, tzinfo=UTC)
        ts2 = datetime(2024, 6, 2, tzinfo=UTC)
        rows = [
            _make_row(bucket=ts1, org="o", action="copilot.add_seats", seat_events=5),
            _make_row(bucket=ts2, org="o", action="copilot.remove_seats", seat_events=2),
        ]
        session = _mock_session_with_results(rows)

        result = await get_copilot_seats_report(session)

        assert len(result) == 2
        bucket_map = {b["bucket"]: b for b in result}
        assert bucket_map[ts1.isoformat()]["seats_assigned"] == 5
        assert bucket_map[ts1.isoformat()]["seats_net"] == 5
        assert bucket_map[ts2.isoformat()]["seats_revoked"] == 2
        assert bucket_map[ts2.isoformat()]["seats_net"] == -2
