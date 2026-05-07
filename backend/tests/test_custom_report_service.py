"""Unit tests for custom report service: validate query construction and results."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.custom_report_service import (
    _get_timestamp_column,
    _serialize_value,
    _validate_field,
    run_custom_report,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session_with_results(
    col_names: list[str],
    rows: list[tuple[object, ...]],
) -> AsyncMock:
    """Return an AsyncSession mock whose execute() returns rows with named columns."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [tuple(r) for r in rows]
    mock_result.keys.return_value = col_names
    session.execute = AsyncMock(return_value=mock_result)
    return session


def _mock_session_empty() -> AsyncMock:
    """Return an AsyncSession mock that returns no rows."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.keys.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ---------------------------------------------------------------------------
# _validate_field
# ---------------------------------------------------------------------------


class TestValidateField:
    def test_valid_events_field(self) -> None:
        assert _validate_field("action", "events") is True

    def test_invalid_events_field(self) -> None:
        assert _validate_field("password", "events") is False

    def test_valid_detections_field(self) -> None:
        assert _validate_field("severity", "detections") is True

    def test_valid_workflows_field(self) -> None:
        assert _validate_field("org", "workflows") is True

    def test_unknown_source(self) -> None:
        assert _validate_field("action", "nonexistent") is False

    def test_empty_field(self) -> None:
        assert _validate_field("", "events") is False


# ---------------------------------------------------------------------------
# _get_timestamp_column
# ---------------------------------------------------------------------------


class TestGetTimestampColumn:
    def test_events_timestamp(self) -> None:
        assert _get_timestamp_column("events") == "created_at"

    def test_workflows_timestamp(self) -> None:
        assert _get_timestamp_column("workflows") == "started_at"

    def test_detections_timestamp(self) -> None:
        assert _get_timestamp_column("detections") == "created_at"


# ---------------------------------------------------------------------------
# _serialize_value
# ---------------------------------------------------------------------------


class TestSerializeValue:
    def test_datetime_value(self) -> None:
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        assert _serialize_value(dt) == "2024-01-15T12:00:00+00:00"

    def test_string_value(self) -> None:
        assert _serialize_value("hello") == "hello"

    def test_int_value(self) -> None:
        assert _serialize_value(42) == 42

    def test_none_value(self) -> None:
        assert _serialize_value(None) is None


# ---------------------------------------------------------------------------
# run_custom_report
# ---------------------------------------------------------------------------


class TestRunCustomReport:
    @pytest.mark.anyio
    async def test_empty_data_sources_returns_empty(self) -> None:
        session = _mock_session_empty()
        result = await run_custom_report(
            session,
            data_sources=[],
            columns=[],
            filters=[],
            grouping={},
        )
        assert result == []

    @pytest.mark.anyio
    async def test_unknown_data_source_returns_empty(self) -> None:
        session = _mock_session_empty()
        result = await run_custom_report(
            session,
            data_sources=["unknown_source"],
            columns=[],
            filters=[],
            grouping={},
        )
        assert result == []

    @pytest.mark.anyio
    async def test_basic_events_query(self) -> None:
        now = datetime.now(UTC)
        session = _mock_session_with_results(
            col_names=["action", "actor", "created_at"],
            rows=[
                ("repos.create", "octocat", now),
                ("repos.delete", "monalisa", now - timedelta(hours=1)),
            ],
        )

        result = await run_custom_report(
            session,
            data_sources=["events"],
            columns=[
                {"field": "action", "label": "Action", "visible": True},
                {"field": "actor", "label": "Actor", "visible": True},
            ],
            filters=[],
            grouping={},
            window_days=30,
        )

        assert len(result) == 2
        assert result[0]["action"] == "repos.create"
        assert result[0]["actor"] == "octocat"
        assert result[1]["action"] == "repos.delete"

        # Verify session.execute was called
        session.execute.assert_called_once()

    @pytest.mark.anyio
    async def test_query_with_filters(self) -> None:
        session = _mock_session_with_results(
            col_names=["action", "actor"],
            rows=[("repos.create", "octocat")],
        )

        result = await run_custom_report(
            session,
            data_sources=["events"],
            columns=[{"field": "action", "label": "Action", "visible": True}],
            filters=[
                {"field": "action", "operator": "eq", "value": "repos.create"},
                {"field": "actor", "operator": "contains", "value": "octo"},
            ],
            grouping={},
            window_days=30,
        )

        assert len(result) == 1
        # Verify the SQL included filter parameters
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["filt_0"] == "repos.create"
        assert params["filt_1"] == "%octo%"

    @pytest.mark.anyio
    async def test_query_with_invalid_filter_field_is_ignored(self) -> None:
        session = _mock_session_with_results(
            col_names=["action"],
            rows=[("repos.create",)],
        )

        result = await run_custom_report(
            session,
            data_sources=["events"],
            columns=[],
            filters=[
                {"field": "password", "operator": "eq", "value": "secret"},
            ],
            grouping={},
        )

        # The invalid filter field should be silently ignored
        assert len(result) == 1
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert "filt_0" not in params

    @pytest.mark.anyio
    async def test_query_with_grouping(self) -> None:
        now = datetime.now(UTC)
        session = _mock_session_with_results(
            col_names=["bucket", "org", "count"],
            rows=[
                (now, "my-org", 42),
                (now - timedelta(days=1), "my-org", 38),
            ],
        )

        result = await run_custom_report(
            session,
            data_sources=["events"],
            columns=[],
            filters=[],
            grouping={"group_by": "org", "time_bucket": "daily"},
            window_days=30,
        )

        assert len(result) == 2
        assert result[0]["org"] == "my-org"
        assert result[0]["count"] == 42

        # Verify bucket_interval was passed
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["bucket_interval"] == timedelta(days=1)

    @pytest.mark.anyio
    async def test_query_with_time_bucket_only(self) -> None:
        now = datetime.now(UTC)
        session = _mock_session_with_results(
            col_names=["bucket", "count"],
            rows=[(now, 100)],
        )

        result = await run_custom_report(
            session,
            data_sources=["events"],
            columns=[],
            filters=[],
            grouping={"time_bucket": "weekly"},
            window_days=30,
        )

        assert len(result) == 1
        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["bucket_interval"] == timedelta(days=7)

    @pytest.mark.anyio
    async def test_query_with_org_filter(self) -> None:
        session = _mock_session_with_results(
            col_names=["action"],
            rows=[("repos.create",)],
        )

        await run_custom_report(
            session,
            data_sources=["events"],
            columns=[],
            filters=[],
            grouping={},
            org="my-org",
        )

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["org"] == "my-org"

    @pytest.mark.anyio
    async def test_query_with_custom_date_range(self) -> None:
        session = _mock_session_with_results(
            col_names=["action"],
            rows=[("repos.create",)],
        )

        await run_custom_report(
            session,
            data_sources=["events"],
            columns=[],
            filters=[],
            grouping={},
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["start_dt"].year == 2024
        assert params["start_dt"].month == 1
        assert params["start_dt"].day == 1

    @pytest.mark.anyio
    async def test_workflows_data_source_uses_started_at(self) -> None:
        session = _mock_session_with_results(
            col_names=["org", "status"],
            rows=[("my-org", "completed")],
        )

        await run_custom_report(
            session,
            data_sources=["workflows"],
            columns=[
                {"field": "org", "label": "Org", "visible": True},
                {"field": "status", "label": "Status", "visible": True},
            ],
            filters=[],
            grouping={},
        )

        # Verify that the query uses started_at for ordering
        call_args = session.execute.call_args
        query_text = str(call_args[0][0])
        assert "started_at" in query_text

    @pytest.mark.anyio
    async def test_empty_result_returns_empty_list(self) -> None:
        session = _mock_session_empty()

        result = await run_custom_report(
            session,
            data_sources=["events"],
            columns=[],
            filters=[],
            grouping={},
        )

        assert result == []

    @pytest.mark.anyio
    async def test_in_operator_filter(self) -> None:
        session = _mock_session_with_results(
            col_names=["action"],
            rows=[("repos.create",)],
        )

        await run_custom_report(
            session,
            data_sources=["events"],
            columns=[],
            filters=[
                {"field": "action", "operator": "in", "value": ["repos.create", "repos.delete"]},
            ],
            grouping={},
        )

        call_args = session.execute.call_args
        params = call_args[0][1]
        assert params["filt_0"] == ["repos.create", "repos.delete"]

    @pytest.mark.anyio
    async def test_copilot_source_adds_scope(self) -> None:
        session = _mock_session_with_results(
            col_names=["action", "actor"],
            rows=[("copilot.seat_assigned", "admin")],
        )

        await run_custom_report(
            session,
            data_sources=["copilot"],
            columns=[],
            filters=[],
            grouping={},
        )

        call_args = session.execute.call_args
        query_text = str(call_args[0][0])
        assert "copilot" in query_text.lower()

    @pytest.mark.anyio
    async def test_invalid_column_fields_use_defaults(self) -> None:
        session = _mock_session_with_results(
            col_names=["action", "actor"],
            rows=[("repos.create", "octocat")],
        )

        await run_custom_report(
            session,
            data_sources=["events"],
            columns=[
                {"field": "invalid_field", "label": "Bad", "visible": True},
            ],
            filters=[],
            grouping={},
        )

        # Should have used default fields since invalid_field was rejected
        session.execute.assert_called_once()
