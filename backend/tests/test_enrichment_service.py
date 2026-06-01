"""Tests for the enrichment service and delivery timeline functionality."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.enrichment_service import (
    compute_hours_between,
    parse_linked_issues,
)


class TestParseLinkedIssues:
    """Tests for parse_linked_issues function."""

    def test_empty_string(self) -> None:
        assert parse_linked_issues("") == []

    def test_none_input(self) -> None:
        assert parse_linked_issues("") == []

    def test_fixes_keyword(self) -> None:
        assert parse_linked_issues("fixes #123") == [123]

    def test_closes_keyword(self) -> None:
        assert parse_linked_issues("closes #456") == [456]

    def test_resolves_keyword(self) -> None:
        assert parse_linked_issues("resolves #789") == [789]

    def test_multiple_issues(self) -> None:
        text = "This PR fixes #10, closes #20 and resolves #30"
        result = parse_linked_issues(text)
        assert result == [10, 20, 30]

    def test_case_insensitive(self) -> None:
        assert parse_linked_issues("Fixes #42") == [42]
        assert parse_linked_issues("CLOSES #99") == [99]

    def test_past_tense(self) -> None:
        assert parse_linked_issues("fixed #11") == [11]
        assert parse_linked_issues("closed #22") == [22]
        assert parse_linked_issues("resolved #33") == [33]

    def test_org_repo_reference(self) -> None:
        assert parse_linked_issues("fixes org/repo#55") == [55]

    def test_deduplication(self) -> None:
        text = "fixes #1, also fixes #1"
        assert parse_linked_issues(text) == [1]

    def test_no_closing_keywords(self) -> None:
        text = "This is a regular PR description mentioning issue #123"
        assert parse_linked_issues(text) == []

    def test_multiline_body(self) -> None:
        text = """## Summary
        This PR implements the feature.

        Fixes #100
        Also closes #200

        ## Testing
        - Unit tests added
        """
        result = parse_linked_issues(text)
        assert result == [100, 200]


class TestComputeHoursBetween:
    """Tests for compute_hours_between function."""

    def test_valid_timestamps(self) -> None:
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2024, 1, 1, 2, 30, 0, tzinfo=UTC)
        assert compute_hours_between(start, end) == 2.5

    def test_none_start(self) -> None:
        end = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert compute_hours_between(None, end) is None

    def test_none_end(self) -> None:
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        assert compute_hours_between(start, None) is None

    def test_both_none(self) -> None:
        assert compute_hours_between(None, None) is None

    def test_same_timestamp(self) -> None:
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert compute_hours_between(ts, ts) == 0.0

    def test_large_duration(self) -> None:
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2024, 1, 8, 0, 0, 0, tzinfo=UTC)
        # 7 days = 168 hours
        assert compute_hours_between(start, end) == 168.0


class TestEnrichPrMergeEvent:
    """Tests for enrich_pr_merge_event function."""

    @pytest.mark.asyncio
    async def test_enrichment_with_linked_issues(self) -> None:
        """Test that enrichment correctly parses issues and computes phases."""
        from app.services.enrichment_service import enrich_pr_merge_event

        # Create a mock session
        session = AsyncMock()

        # Mock the flush (no-op)
        session.flush = AsyncMock()

        # Set up mock responses for event queries
        # _find_earliest_issue_event for issues.opened
        issue_created = datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        # _find_earliest_issue_event for issues.assigned
        issue_assigned = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        # _find_pr_opened_at
        pr_opened = datetime(2024, 1, 3, 10, 0, 0, tzinfo=UTC)
        # pr_merged_at
        pr_merged = datetime(2024, 1, 5, 10, 0, 0, tzinfo=UTC)
        # _find_ci_completion
        ci_done = datetime(2024, 1, 5, 10, 30, 0, tzinfo=UTC)

        # Mock execute to return appropriate results based on the query
        mock_mapping_issue_created = MagicMock()
        mock_mapping_issue_created.__getitem__ = lambda self, k: (
            issue_created if k == "earliest" else None
        )
        mock_mapping_issue_created.get = lambda k, d=None: issue_created if k == "earliest" else d

        mock_mapping_issue_assigned = MagicMock()
        mock_mapping_issue_assigned.__getitem__ = lambda self, k: (
            issue_assigned if k == "earliest" else None
        )
        mock_mapping_issue_assigned.get = lambda k, d=None: issue_assigned if k == "earliest" else d

        mock_mapping_pr_opened = MagicMock()
        mock_mapping_pr_opened.__getitem__ = lambda self, k: pr_opened if k == "opened_at" else None
        mock_mapping_pr_opened.get = lambda k, d=None: pr_opened if k == "opened_at" else d

        mock_mapping_ci = MagicMock()
        mock_mapping_ci.__getitem__ = lambda self, k: ci_done if k == "completed_at" else None
        mock_mapping_ci.get = lambda k, d=None: ci_done if k == "completed_at" else d

        # Mock the timeline record returned by select after upsert
        mock_timeline = MagicMock()
        mock_timeline.id = "test-uuid-123"
        mock_timeline.total_hours = 96.5
        mock_timeline.issue_numbers = [42]
        mock_timeline.org = "test-org"
        mock_timeline.repo = "test-repo"
        mock_timeline.pr_number = 99

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()

            # First call: issue created (issues.opened)
            if call_count == 1:
                mappings_mock = MagicMock()
                mappings_mock.first.return_value = mock_mapping_issue_created
                result.mappings.return_value = mappings_mock
            # Second call: issue assigned
            elif call_count == 2:
                mappings_mock = MagicMock()
                mappings_mock.first.return_value = mock_mapping_issue_assigned
                result.mappings.return_value = mappings_mock
            # Third call: PR opened
            elif call_count == 3:
                mappings_mock = MagicMock()
                mappings_mock.first.return_value = mock_mapping_pr_opened
                result.mappings.return_value = mappings_mock
            # Fourth call: CI completion
            elif call_count == 4:
                mappings_mock = MagicMock()
                mappings_mock.first.return_value = mock_mapping_ci
                result.mappings.return_value = mappings_mock
            # Fifth call: upsert (pg_insert)
            elif call_count == 5:
                pass
            # Sixth call: select the timeline record
            elif call_count == 6:
                result.scalar_one.return_value = mock_timeline
            return result

        session.execute = mock_execute

        timeline = await enrich_pr_merge_event(
            session,
            org="test-org",
            repo="test-repo",
            pr_number=99,
            pr_body="This PR fixes #42",
            pr_title="Feature implementation",
            pr_merged_at=pr_merged,
            merge_commit_sha="abc123def",
        )

        assert timeline.id == "test-uuid-123"
        assert timeline.issue_numbers == [42]

    @pytest.mark.asyncio
    async def test_enrichment_no_issues(self) -> None:
        """Test enrichment when PR has no linked issues."""
        from app.services.enrichment_service import enrich_pr_merge_event

        session = AsyncMock()
        session.flush = AsyncMock()

        pr_merged = datetime(2024, 1, 5, 10, 0, 0, tzinfo=UTC)

        mock_timeline = MagicMock()
        mock_timeline.id = "no-issues-uuid"
        mock_timeline.total_hours = None
        mock_timeline.issue_numbers = []

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()

            # First call: PR opened (no issues to look up)
            if call_count == 1:
                mappings_mock = MagicMock()
                mappings_mock.first.return_value = {"opened_at": None}
                result.mappings.return_value = mappings_mock
            # Second call: upsert (no CI lookup since merge_commit_sha=None)
            elif call_count == 2:
                pass
            # Third call: select
            elif call_count == 3:
                result.scalar_one.return_value = mock_timeline
            return result

        session.execute = mock_execute

        timeline = await enrich_pr_merge_event(
            session,
            org="test-org",
            repo="test-repo",
            pr_number=50,
            pr_body="Regular PR with no issue refs",
            pr_title="Minor fix",
            pr_merged_at=pr_merged,
            merge_commit_sha=None,
        )

        assert timeline.id == "no-issues-uuid"
        assert timeline.issue_numbers == []


class TestGetDeliveryTimelineStats:
    """Tests for get_delivery_timeline_stats function."""

    @pytest.mark.asyncio
    async def test_empty_orgs_returns_empty(self) -> None:
        """Test that empty org list returns zeroed stats."""
        from app.services.enrichment_service import get_delivery_timeline_stats

        session = AsyncMock()
        result = await get_delivery_timeline_stats(session, orgs=[], days=30)

        assert result["total_prs"] == 0
        assert result["avg_total_hours"] is None
        assert result["timelines"] == []

    @pytest.mark.asyncio
    async def test_stats_with_data(self) -> None:
        """Test that stats are returned correctly when data exists."""
        from app.services.enrichment_service import get_delivery_timeline_stats

        session = AsyncMock()

        # Mock the aggregated stats query
        mock_stats_row = {
            "total_prs": 5,
            "avg_backlog_hours": 4.5,
            "avg_dev_hours": 12.0,
            "avg_review_hours": 6.0,
            "avg_deploy_hours": 0.5,
            "avg_total_hours": 23.0,
            "median_total_hours": 20.0,
            "p95_total_hours": 48.0,
        }

        mock_timeline_rows = [
            {
                "id": "uuid-1",
                "pr_number": 10,
                "repo": "my-repo",
                "org": "my-org",
                "issue_numbers": [1, 2],
                "backlog_hours": 5.0,
                "dev_hours": 10.0,
                "review_hours": 4.0,
                "deploy_hours": 0.3,
                "total_hours": 19.3,
                "pr_merged_at": datetime(2024, 1, 5, tzinfo=UTC),
                "created_at": datetime(2024, 1, 5, tzinfo=UTC),
            }
        ]

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            mappings_mock = MagicMock()

            if call_count == 1:
                # Stats query
                mappings_mock.first.return_value = mock_stats_row
            elif call_count == 2:
                # Timelines query
                mappings_mock.all.return_value = mock_timeline_rows

            result.mappings.return_value = mappings_mock
            return result

        session.execute = mock_execute

        result = await get_delivery_timeline_stats(session, orgs=["my-org"], days=30)

        assert result["total_prs"] == 5
        assert result["avg_backlog_hours"] == 4.5
        assert result["avg_total_hours"] == 23.0
        assert result["median_total_hours"] == 20.0
        assert result["p95_total_hours"] == 48.0
        assert len(result["timelines"]) == 1


class TestEnrichmentWorkerTask:
    """Tests for the Celery worker task."""

    @pytest.mark.asyncio
    async def test_enrich_pr_async_wrapper(self) -> None:
        """Test the async wrapper function processes correctly."""
        from app.workers.enrichment_worker import _enrich_pr

        mock_timeline = MagicMock()
        mock_timeline.id = "worker-uuid"
        mock_timeline.total_hours = 10.0
        mock_timeline.issue_numbers = [5]

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.workers.enrichment_worker.AsyncSessionLocal") as mock_session_local,
            patch(
                "app.services.enrichment_service.enrich_pr_merge_event",
                new_callable=AsyncMock,
                return_value=mock_timeline,
            ),
        ):
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _enrich_pr(
                org="test-org",
                repo="test-repo",
                pr_number=77,
                pr_body="fixes #5",
                pr_title="test",
                pr_merged_at_iso="2024-01-05T10:00:00+00:00",
                merge_commit_sha="sha123",
            )

            assert result["timeline_id"] == "worker-uuid"
            assert result["total_hours"] == 10.0
            assert result["linked_issues"] == [5]
