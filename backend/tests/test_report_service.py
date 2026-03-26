"""Unit tests for report service: verify correct SQL construction patterns."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.report_service import _bucket_interval, _window_start


class TestBucketInterval:
    def test_daily(self):
        assert _bucket_interval("daily") == "1 day"

    def test_weekly(self):
        assert _bucket_interval("weekly") == "7 days"

    def test_monthly(self):
        assert _bucket_interval("monthly") == "1 month"

    def test_unknown_defaults_to_daily(self):
        assert _bucket_interval("unknown") == "1 day"


class TestWindowStart:
    def test_30_day_window(self):
        from datetime import datetime

        start = _window_start(30)
        now = datetime.now(UTC)
        diff = (now - start).total_seconds()
        # Should be approximately 30 days
        assert 29 * 86400 < diff < 31 * 86400

    def test_90_day_window(self):
        from datetime import datetime

        start = _window_start(90)
        now = datetime.now(UTC)
        diff = (now - start).total_seconds()
        assert 89 * 86400 < diff < 91 * 86400


class TestReportServiceMocked:
    """Smoke tests that verify report functions call the session correctly."""

    @pytest.mark.asyncio
    async def test_get_mau_report_executes_query(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.services.report_service import get_mau_report

        result = await get_mau_report(mock_session, window_days=30, granularity="daily")

        assert isinstance(result, list)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_seat_utilization_report_executes_query(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.services.report_service import get_seat_utilization_report

        result = await get_seat_utilization_report(mock_session)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_repo_creation_rate_report(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.services.report_service import get_repo_creation_rate_report

        result = await get_repo_creation_rate_report(mock_session)
        assert result == []

    @pytest.mark.asyncio
    async def test_org_filter_passed_to_query(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        from app.services.report_service import get_mau_report

        await get_mau_report(mock_session, window_days=30, granularity="daily", org="my-org")

        call_args = mock_session.execute.call_args
        params = call_args[0][1] if call_args[0] else call_args[1]
        # The org should appear in the params dict
        assert "org" in str(params) or "my-org" in str(params)
