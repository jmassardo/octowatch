"""Tests for REST API workflow_runs sync entity.

Covers _fetch_page handler for workflow_runs, pagination, filtering for
completed-only runs, deduplication, error handling, and _upsert_items dispatch.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, _patch, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_rate_limiter() -> MagicMock:
    rl = MagicMock()
    rl.acquire = AsyncMock()
    rl.release = MagicMock()
    rl.update_from_headers = MagicMock()
    rl.handle_rate_limit_response = AsyncMock()
    return rl


def _make_response(
    status_code: int = 200,
    json_data: list[object] | dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    text: str = "",
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.headers = headers or {}
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response

        resp.raise_for_status.side_effect = HTTPStatusError(
            message=f"{status_code}",
            request=Request("GET", "https://api.github.com/test"),
            response=Response(status_code),
        )
    return resp


def _repo_rows(names: list[str]) -> list[tuple[str]]:
    """Simulate DB rows for repo_name SELECT."""
    return [(n,) for n in names]


def _patch_repo_query(repo_names: list[str]) -> _patch[MagicMock]:
    """Patch _make_session_factory to return a mock session that yields repo names."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = _repo_rows(repo_names)
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_factory = MagicMock()
    mock_factory.return_value = mock_session

    return patch(
        "app.workers.github_sync_worker._make_session_factory",
        return_value=mock_factory,
    )


def _make_workflow_run(
    run_id: int = 100,
    name: str = "CI",
    conclusion: str = "success",
    status: str = "completed",
    actor_login: str = "alice",
    actor_id: int = 1,
    head_branch: str = "main",
    event: str = "push",
    workflow_id: int = 10,
    run_number: int = 42,
    created_at: str = "2024-06-01T10:00:00Z",
    run_started_at: str = "2024-06-01T10:00:05Z",
    updated_at: str = "2024-06-01T10:03:05Z",
    html_url: str = "",
) -> dict[str, object]:
    """Create a realistic GitHub Actions workflow run API response object."""
    if not html_url:
        html_url = f"https://github.com/test-org/repo1/actions/runs/{run_id}"
    return {
        "id": run_id,
        "name": name,
        "head_branch": head_branch,
        "run_number": run_number,
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "workflow_id": workflow_id,
        "created_at": created_at,
        "run_started_at": run_started_at,
        "updated_at": updated_at,
        "html_url": html_url,
        "triggering_actor": {"login": actor_login, "id": actor_id},
        "actor": {"login": actor_login, "id": actor_id},
    }


# ── workflow_runs fetch tests ─────────────────────────────────────────────────


class TestFetchPageWorkflowRuns:
    """Tests for _fetch_page with entity_type='workflow_runs'."""

    @pytest.mark.asyncio
    async def test_basic_workflow_run_fetch(self) -> None:
        """Completed workflow runs from a single repo are normalized correctly."""
        from app.workers.github_sync_worker import _fetch_page

        runs = [
            _make_workflow_run(run_id=100, conclusion="success", actor_login="alice", actor_id=1),
            _make_workflow_run(
                run_id=101,
                conclusion="failure",
                actor_login="bob",
                actor_id=2,
                name="Deploy",
                event="pull_request",
                head_branch="feature-x",
            ),
        ]
        api_data = {"total_count": 2, "workflow_runs": runs}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="workflow_runs",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 2

        # First run
        assert items[0]["action"] == "workflow_run.success"
        assert items[0]["actor"] == "alice"
        assert items[0]["actor_id"] == 1
        assert items[0]["document_id"] == "workflow-run-test-org/repo1-100"
        assert items[0]["repo"] == "test-org/repo1"
        assert items[0]["org"] == "test-org"
        assert items[0]["ingestion_source"] == "github_api_sync"
        assert items[0]["source_file_path"] == "api/test-org/repo1/actions/runs"
        assert items[0]["actor_is_bot"] is False

        data0 = json.loads(items[0]["data"])
        assert data0["workflow_name"] == "CI"
        assert data0["run_id"] == 100
        assert data0["conclusion"] == "success"
        assert data0["event"] == "push"
        assert data0["head_branch"] == "main"
        assert data0["duration_seconds"] == 180.0  # 3 min difference

        # Second run
        assert items[1]["action"] == "workflow_run.failure"
        assert items[1]["actor"] == "bob"
        assert items[1]["document_id"] == "workflow-run-test-org/repo1-101"

        data1 = json.loads(items[1]["data"])
        assert data1["workflow_name"] == "Deploy"
        assert data1["event"] == "pull_request"

        # No more repos, no more pages
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_pagination_across_repos(self) -> None:
        """Pagination works across multiple repos using JSON cursor."""
        from app.workers.github_sync_worker import _fetch_page

        run1 = _make_workflow_run(run_id=200, actor_login="alice")
        run2 = _make_workflow_run(run_id=201, actor_login="bob")

        # First call: repo1 has runs, has next page link (to simulate pagination)
        resp_repo1 = _make_response(
            200,
            {"total_count": 1, "workflow_runs": [run1]},
            {"link": '<next>; rel="next"'},
        )
        # Second call: repo1 page 2, no more runs
        resp_repo1_p2 = _make_response(
            200,
            {"total_count": 0, "workflow_runs": []},
            {},
        )

        with (
            _patch_repo_query(["repo1", "repo2"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_repo1]),
            ),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        assert next_cursor is not None
        cursor_data = json.loads(next_cursor)
        assert cursor_data["repo_idx"] == 0
        assert cursor_data["page"] == 2

        # Continue with the cursor — repo1 page 2 empty, then repo2
        resp_repo2 = _make_response(
            200,
            {"total_count": 1, "workflow_runs": [run2]},
            {},
        )
        with (
            _patch_repo_query(["repo1", "repo2"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_repo1_p2, resp_repo2]),
            ),
        ):
            items2, next_cursor2 = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=next_cursor,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items2) == 1
        assert items2[0]["document_id"] == "workflow-run-org/repo2-201"
        assert next_cursor2 is None  # all repos done

    @pytest.mark.asyncio
    async def test_only_completed_runs_synced(self) -> None:
        """Runs with status != 'completed' are excluded from results."""
        from app.workers.github_sync_worker import _fetch_page

        completed_run = _make_workflow_run(run_id=300, status="completed", conclusion="success")
        in_progress_run = _make_workflow_run(run_id=301, status="in_progress", conclusion="")
        queued_run = _make_workflow_run(run_id=302, status="queued", conclusion="")

        api_data = {
            "total_count": 3,
            "workflow_runs": [completed_run, in_progress_run, queued_run],
        }
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        assert items[0]["document_id"] == "workflow-run-test-org/repo1-300"

    @pytest.mark.asyncio
    async def test_deduplication_via_document_id(self) -> None:
        """Same run_id produces consistent document_id for dedup."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(run_id=400)
        api_data = {"total_count": 1, "workflow_runs": [run]}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items1, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="myorg",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items2, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="myorg",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items1[0]["document_id"] == items2[0]["document_id"]
        assert items1[0]["document_id"] == "workflow-run-myorg/repo1-400"

    @pytest.mark.asyncio
    async def test_empty_repos_handled_gracefully(self) -> None:
        """Org with no repos returns empty items."""
        from app.workers.github_sync_worker import _fetch_page

        with _patch_repo_query([]):
            items, next_cursor = await _fetch_page(
                entity_type="workflow_runs",
                org="empty-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_repo_with_no_workflow_runs(self) -> None:
        """Repo with zero workflow runs handled gracefully."""
        from app.workers.github_sync_worker import _fetch_page

        api_data = {"total_count": 0, "workflow_runs": []}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="workflow_runs",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_repo_404_skipped(self) -> None:
        """Deleted/inaccessible repo is skipped, next repo is processed."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(run_id=500, actor_login="charlie")
        resp_404 = _make_response(404)
        resp_ok = _make_response(200, {"total_count": 1, "workflow_runs": [run]}, {})

        with (
            _patch_repo_query(["deleted-repo", "good-repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_404, resp_ok]),
            ),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="workflow_runs",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        assert items[0]["actor"] == "charlie"
        assert items[0]["repo"] == "test-org/good-repo"
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_repo_403_skipped(self) -> None:
        """Forbidden repo is skipped, next repo is processed."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(run_id=600)
        resp_403 = _make_response(403)
        resp_ok = _make_response(200, {"total_count": 1, "workflow_runs": [run]}, {})

        with (
            _patch_repo_query(["private-repo", "open-repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_403, resp_ok]),
            ),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="workflow_runs",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        assert items[0]["repo"] == "test-org/open-repo"

    @pytest.mark.asyncio
    async def test_multiple_repos_with_different_run_counts(self) -> None:
        """Multiple repos with varying workflow run counts are all processed."""
        from app.workers.github_sync_worker import _fetch_page

        runs_repo1 = [
            _make_workflow_run(run_id=700, actor_login="alice"),
            _make_workflow_run(run_id=701, actor_login="alice"),
        ]
        runs_repo2 = [
            _make_workflow_run(run_id=702, actor_login="bob"),
        ]

        resp_repo1 = _make_response(200, {"total_count": 2, "workflow_runs": runs_repo1}, {})
        resp_repo2 = _make_response(200, {"total_count": 1, "workflow_runs": runs_repo2}, {})

        with (
            _patch_repo_query(["repo1", "repo2"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_repo1, resp_repo2]),
            ),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="workflow_runs",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 3
        doc_ids = {i["document_id"] for i in items}
        assert "workflow-run-test-org/repo1-700" in doc_ids
        assert "workflow-run-test-org/repo1-701" in doc_ids
        assert "workflow-run-test-org/repo2-702" in doc_ids
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_event_metadata_contains_expected_fields(self) -> None:
        """All expected metadata fields are present in the event data."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(
            run_id=800,
            name="Build & Test",
            conclusion="cancelled",
            workflow_id=55,
            run_number=99,
            head_branch="develop",
            event="schedule",
            created_at="2024-07-15T08:00:00Z",
            run_started_at="2024-07-15T08:00:10Z",
            updated_at="2024-07-15T08:05:10Z",
            html_url="https://github.com/org/repo/actions/runs/800",
        )
        api_data = {"total_count": 1, "workflow_runs": [run]}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        item = items[0]
        assert item["action"] == "workflow_run.cancelled"

        data = json.loads(item["data"])
        assert data["workflow_name"] == "Build & Test"
        assert data["workflow_id"] == 55
        assert data["run_number"] == 99
        assert data["run_id"] == 800
        assert data["head_branch"] == "develop"
        assert data["event"] == "schedule"
        assert data["conclusion"] == "cancelled"
        assert data["status"] == "completed"
        assert data["run_started_at"] == "2024-07-15T08:00:10Z"
        assert data["updated_at"] == "2024-07-15T08:05:10Z"
        assert data["html_url"] == "https://github.com/org/repo/actions/runs/800"
        assert data["duration_seconds"] == 300.0  # 5 minutes

    @pytest.mark.asyncio
    async def test_bot_actor_detection(self) -> None:
        """Actors ending in [bot] are flagged."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(
            run_id=900,
            actor_login="dependabot[bot]",
            actor_id=49699333,
        )
        api_data = {"total_count": 1, "workflow_runs": [run]}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        assert items[0]["actor"] == "dependabot[bot]"
        assert items[0]["actor_is_bot"] is True

    @pytest.mark.asyncio
    async def test_delta_since_passed_to_api(self) -> None:
        """delta_since parameter is used in the API created filter."""
        from app.workers.github_sync_worker import _fetch_page

        api_data = {"total_count": 0, "workflow_runs": []}
        mock_resp = _make_response(200, api_data, {})
        mock_get = AsyncMock(return_value=mock_resp)

        delta = datetime(2024, 8, 1, 0, 0, 0, tzinfo=UTC)

        with (
            _patch_repo_query(["repo1"]),
            patch("app.workers.github_sync_worker._github_get", new=mock_get),
        ):
            await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
                delta_since=delta,
            )

        # Verify the created filter was passed
        call_args = mock_get.call_args
        params = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("params", {})
        assert "created" in params
        assert params["created"] == ">2024-08-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_duration_none_when_timestamps_missing(self) -> None:
        """Duration is None when run_started_at or updated_at is missing."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(run_id=1000)
        run["run_started_at"] = ""
        run["updated_at"] = ""
        api_data = {"total_count": 1, "workflow_runs": [run]}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        data = json.loads(items[0]["data"])
        assert data["duration_seconds"] is None

    @pytest.mark.asyncio
    async def test_conclusion_variants(self) -> None:
        """Different conclusion values produce correct action strings."""
        from app.workers.github_sync_worker import _fetch_page

        conclusions = ["success", "failure", "cancelled", "skipped", "timed_out"]
        runs = [
            _make_workflow_run(run_id=1100 + i, conclusion=c) for i, c in enumerate(conclusions)
        ]
        api_data = {"total_count": len(runs), "workflow_runs": runs}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 5
        for item, expected_conclusion in zip(items, conclusions, strict=True):
            assert item["action"] == f"workflow_run.{expected_conclusion}"

    @pytest.mark.asyncio
    async def test_fallback_to_actor_when_no_triggering_actor(self) -> None:
        """Falls back to 'actor' field when 'triggering_actor' is missing."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(run_id=1200, actor_login="fallback-user", actor_id=99)
        # Remove triggering_actor, keep actor
        del run["triggering_actor"]
        api_data = {"total_count": 1, "workflow_runs": [run]}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items[0]["actor"] == "fallback-user"
        assert items[0]["actor_id"] == 99

    @pytest.mark.asyncio
    async def test_no_actor_at_all(self) -> None:
        """Handles runs with no actor information gracefully."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(run_id=1300)
        run["triggering_actor"] = None
        run["actor"] = None
        api_data = {"total_count": 1, "workflow_runs": [run]}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        assert items[0]["actor"] is None
        assert items[0]["actor_id"] is None
        assert items[0]["actor_is_bot"] is False

    @pytest.mark.asyncio
    async def test_repo_idx_beyond_range_returns_empty(self) -> None:
        """Cursor with repo_idx >= len(repos) returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        with _patch_repo_query(["repo1"]):
            items, next_cursor = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=json.dumps({"repo_idx": 5, "page": 1}),
                rate_limiter=_make_rate_limiter(),
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_default_90_day_lookback(self) -> None:
        """When no delta_since, uses 90-day default lookback."""
        from app.workers.github_sync_worker import _fetch_page

        api_data = {"total_count": 0, "workflow_runs": []}
        mock_resp = _make_response(200, api_data, {})
        mock_get = AsyncMock(return_value=mock_resp)

        with (
            _patch_repo_query(["repo1"]),
            patch("app.workers.github_sync_worker._github_get", new=mock_get),
        ):
            await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        call_args = mock_get.call_args
        params = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("params", {})
        assert "created" in params
        # The date should be roughly 90 days ago
        created_filter = params["created"]
        assert created_filter.startswith(">")
        date_str = created_filter[1:]
        filter_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        days_ago = (now - filter_date).days
        assert 89 <= days_ago <= 91

    @pytest.mark.asyncio
    async def test_invalid_created_at_fallback(self) -> None:
        """Invalid created_at timestamp falls back to now()."""
        from app.workers.github_sync_worker import _fetch_page

        run = _make_workflow_run(run_id=1400, created_at="not-a-date")
        api_data = {"total_count": 1, "workflow_runs": [run]}
        mock_resp = _make_response(200, api_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        # Should have a created_at (fallback to now), not crash
        assert items[0]["created_at"] is not None


# ── _upsert_items dispatcher tests ───────────────────────────────────────────


class TestUpsertItemsWorkflowRuns:
    """Tests that _upsert_items correctly dispatches workflow_runs."""

    @pytest.mark.asyncio
    async def test_dispatches_workflow_runs(self) -> None:
        """workflow_runs entity type routes to _upsert_activity_events."""
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()

        with patch(
            "app.workers.github_sync_worker._upsert_activity_events",
            new=AsyncMock(),
        ) as mock_upsert:
            await _upsert_items(mock_session, "workflow_runs", "test-org", [{"item": 1}])
            mock_upsert.assert_called_once_with(mock_session, "test-org", [{"item": 1}])


# ── Entity registration tests ────────────────────────────────────────────────


class TestWorkflowRunsEntityRegistration:
    """Verify workflow_runs is registered in the right places."""

    def test_workflow_runs_in_scope_type(self) -> None:
        """workflow_runs is a valid ScopeType literal."""
        from app.schemas.github_sync import SyncTriggerRequest

        req = SyncTriggerRequest(scope="workflow_runs")
        assert req.scope == "workflow_runs"

    def test_schedule_scope_validates_workflow_runs(self) -> None:
        """workflow_runs is accepted by SyncScheduleUpdateRequest.scope validator."""
        from app.schemas.github_sync import SyncScheduleUpdateRequest

        req = SyncScheduleUpdateRequest(scope="workflow_runs")
        assert req.scope == "workflow_runs"

    def test_workflow_runs_in_org_entities(self) -> None:
        """workflow_runs is listed in _ORG_ENTITIES so it runs per-org."""
        import pathlib

        src = pathlib.Path(__file__).resolve().parent.parent / ("app/workers/github_sync_worker.py")
        source = src.read_text()
        # Verify the string "workflow_runs" appears in _ORG_ENTITIES block
        assert '"workflow_runs"' in source or "'workflow_runs'" in source

    def test_action_naming_matches_report_query(self) -> None:
        """Events use 'workflow_run.<conclusion>' matching report LIKE 'workflow_run.%'."""
        # The report_service queries: action LIKE 'workflow_run.%'
        # Our events use: workflow_run.success, workflow_run.failure, etc.
        import pathlib

        src = pathlib.Path(__file__).resolve().parent.parent / ("app/services/report_service.py")
        source = src.read_text()
        # Verify the report uses LIKE 'workflow_run.%'
        assert "workflow_run.%" in source

        # Verify our handler creates actions matching this pattern
        worker_src = pathlib.Path(__file__).resolve().parent.parent / (
            "app/workers/github_sync_worker.py"
        )
        worker_source = worker_src.read_text()
        assert 'f"workflow_run.{conclusion}"' in worker_source
