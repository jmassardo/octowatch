"""Tests for REST API activity data sync (repo_commits, pull_requests).

Covers _fetch_page handlers, pagination, delta sync, deduplication, error
handling, and the _upsert_activity_events function.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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
    json_data: list | dict | None = None,
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


def _patch_repo_query(repo_names: list[str]):
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


# ── repo_commits fetch tests ─────────────────────────────────────────────────


class TestFetchPageRepoCommits:
    """Tests for _fetch_page with entity_type='repo_commits'."""

    @pytest.mark.asyncio
    async def test_basic_commit_fetch(self) -> None:
        """Commits from a single repo are normalized correctly."""
        from app.workers.github_sync_worker import _fetch_page

        commits_data = [
            {
                "sha": "abc123",
                "author": {"login": "alice", "id": 1},
                "committer": {"login": "alice", "id": 1},
                "commit": {
                    "author": {"name": "Alice", "date": "2024-06-01T10:00:00Z"},
                    "message": "initial commit",
                },
                "html_url": "https://github.com/test-org/repo1/commit/abc123",
            },
            {
                "sha": "def456",
                "author": {"login": "bob", "id": 2},
                "committer": {"login": "bob", "id": 2},
                "commit": {
                    "author": {"name": "Bob", "date": "2024-06-02T11:00:00Z"},
                    "message": "fix bug",
                },
                "html_url": "https://github.com/test-org/repo1/commit/def456",
            },
        ]

        mock_resp = _make_response(200, commits_data, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=mock_resp),
            ),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="repo_commits",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 2
        assert items[0]["action"] == "git.push"
        assert items[0]["actor"] == "alice"
        assert items[0]["actor_id"] == 1
        assert items[0]["document_id"] == "commit-abc123"
        assert items[0]["repo"] == "test-org/repo1"
        assert items[0]["ingestion_source"] == "github_api_sync"
        assert items[0]["source_file_path"] == "api/test-org/repo1/commits"
        assert items[0]["actor_is_bot"] is False

        data = json.loads(items[0]["data"])
        assert data["sha"] == "abc123"
        assert data["message"] == "initial commit"

        assert items[1]["actor"] == "bob"
        assert items[1]["document_id"] == "commit-def456"
        # No more repos, no more pages
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_pagination_across_repos(self) -> None:
        """Pagination works across multiple repos using JSON cursor."""
        from app.workers.github_sync_worker import _fetch_page

        commit1 = {
            "sha": "aaa",
            "author": {"login": "alice", "id": 1},
            "commit": {"author": {"name": "Alice", "date": "2024-06-01T10:00:00Z"}, "message": "a"},
            "html_url": "https://github.com/org/repo1/commit/aaa",
        }
        commit2 = {
            "sha": "bbb",
            "author": {"login": "bob", "id": 2},
            "commit": {"author": {"name": "Bob", "date": "2024-06-02T10:00:00Z"}, "message": "b"},
            "html_url": "https://github.com/org/repo2/commit/bbb",
        }

        # First call: repo1 has commits, has next page link (to simulate pagination)
        resp_repo1 = _make_response(200, [commit1], {"link": '<next>; rel="next"'})
        # Second call: repo1 page 2, no more pages
        resp_repo1_p2 = _make_response(200, [], {})

        with (
            _patch_repo_query(["repo1", "repo2"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_repo1]),
            ),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="repo_commits",
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
        with (
            _patch_repo_query(["repo1", "repo2"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_repo1_p2, _make_response(200, [commit2], {})]),
            ),
        ):
            items2, next_cursor2 = await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=next_cursor,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items2) == 1
        assert items2[0]["document_id"] == "commit-bbb"
        assert next_cursor2 is None  # all repos done

    @pytest.mark.asyncio
    async def test_bot_actor_detection(self) -> None:
        """Actors ending in [bot] are flagged."""
        from app.workers.github_sync_worker import _fetch_page

        bot_commit = {
            "sha": "bot1",
            "author": {"login": "dependabot[bot]", "id": 99},
            "commit": {
                "author": {"name": "dependabot[bot]", "date": "2024-06-01T10:00:00Z"},
                "message": "bump deps",
            },
            "html_url": "https://github.com/org/repo/commit/bot1",
        }

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=_make_response(200, [bot_commit], {})),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items[0]["actor_is_bot"] is True

    @pytest.mark.asyncio
    async def test_fallback_to_commit_author_name(self) -> None:
        """When author.login is missing, falls back to commit.author.name."""
        from app.workers.github_sync_worker import _fetch_page

        commit = {
            "sha": "noauth",
            "author": None,
            "committer": None,
            "commit": {
                "author": {"name": "External Dev", "date": "2024-06-01T10:00:00Z"},
                "message": "external contribution",
            },
            "html_url": "",
        }

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=_make_response(200, [commit], {})),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items[0]["actor"] == "External Dev"
        assert items[0]["actor_id"] is None

    @pytest.mark.asyncio
    async def test_repo_404_skipped(self) -> None:
        """A 404 on a repo is silently skipped, other repos are still processed."""
        from app.workers.github_sync_worker import _fetch_page

        commit = {
            "sha": "ok1",
            "author": {"login": "alice", "id": 1},
            "commit": {
                "author": {"name": "Alice", "date": "2024-06-01T10:00:00Z"},
                "message": "ok",
            },
            "html_url": "",
        }

        resp_404 = _make_response(404, text="Not Found")
        # Override raise_for_status so 404 doesn't raise — our code checks status_code
        resp_404.raise_for_status = MagicMock()
        resp_ok = _make_response(200, [commit], {})

        with (
            _patch_repo_query(["deleted-repo", "good-repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_404, resp_ok]),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        assert items[0]["document_id"] == "commit-ok1"

    @pytest.mark.asyncio
    async def test_repo_409_empty_repo_skipped(self) -> None:
        """A 409 (empty repo) is silently skipped."""
        from app.workers.github_sync_worker import _fetch_page

        resp_409 = _make_response(409, text="Git Repository is empty")
        resp_409.raise_for_status = MagicMock()

        with (
            _patch_repo_query(["empty-repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=resp_409),
            ),
        ):
            items, cursor = await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items == []
        assert cursor is None

    @pytest.mark.asyncio
    async def test_repo_403_skipped(self) -> None:
        """A 403 on a repo is skipped gracefully."""
        from app.workers.github_sync_worker import _fetch_page

        resp_403 = _make_response(403, text="Forbidden")
        resp_403.raise_for_status = MagicMock()

        with (
            _patch_repo_query(["private-repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=resp_403),
            ),
        ):
            items, cursor = await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items == []
        assert cursor is None

    @pytest.mark.asyncio
    async def test_no_repos_returns_empty(self) -> None:
        """When there are no repos for the org, return empty immediately."""
        from app.workers.github_sync_worker import _fetch_page

        with _patch_repo_query([]):
            items, cursor = await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items == []
        assert cursor is None

    @pytest.mark.asyncio
    async def test_delta_since_passed_to_api(self) -> None:
        """delta_since is forwarded as the `since` query parameter."""
        from app.workers.github_sync_worker import _fetch_page

        since = datetime(2024, 5, 1, tzinfo=UTC)

        captured_params: list[dict] = []

        async def mock_get(
            url: str,
            headers: dict,
            params: dict,
            rate_limiter: object,
            **kw: object,
        ) -> MagicMock:
            captured_params.append(dict(params))
            return _make_response(200, [], {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=mock_get),
            ),
        ):
            await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
                delta_since=since,
            )

        assert len(captured_params) == 1
        assert captured_params[0]["since"] == since.isoformat()

    @pytest.mark.asyncio
    async def test_long_message_truncated(self) -> None:
        """Commit messages over 500 chars are truncated."""
        from app.workers.github_sync_worker import _fetch_page

        long_msg = "x" * 1000
        commit = {
            "sha": "trunc1",
            "author": {"login": "dev", "id": 1},
            "commit": {
                "author": {"name": "Dev", "date": "2024-06-01T10:00:00Z"},
                "message": long_msg,
            },
            "html_url": "",
        }

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=_make_response(200, [commit], {})),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="repo_commits",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        data = json.loads(items[0]["data"])
        assert len(data["message"]) == 500


# ── pull_requests fetch tests ─────────────────────────────────────────────────


class TestFetchPagePullRequests:
    """Tests for _fetch_page with entity_type='pull_requests'."""

    @pytest.mark.asyncio
    async def test_basic_pr_fetch_open(self) -> None:
        """Open PRs are normalized with action pull_request.opened."""
        from app.workers.github_sync_worker import _fetch_page

        now = datetime.now(UTC)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_update = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        pr_data = [
            {
                "number": 42,
                "state": "open",
                "title": "Add feature X",
                "user": {"login": "alice", "id": 1},
                "created_at": recent,
                "updated_at": recent_update,
                "merged_at": None,
                "closed_at": None,
                "merged": False,
                "html_url": "https://github.com/org/repo/pull/42",
                "additions": 10,
                "deletions": 5,
                "changed_files": 3,
            },
        ]

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=_make_response(200, pr_data, {})),
            ),
        ):
            items, cursor = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        item = items[0]
        assert item["action"] == "pull_request.opened"
        assert item["actor"] == "alice"
        assert item["actor_id"] == 1
        assert item["document_id"] == "pr-org/repo#42-opened"
        assert item["repo"] == "org/repo"
        assert item["ingestion_source"] == "github_api_sync"
        assert item["source_file_path"] == "api/org/repo/pulls"

        data = json.loads(item["data"])
        assert data["number"] == 42
        assert data["title"] == "Add feature X"
        assert data["merged"] is False
        assert data["additions"] == 10
        assert cursor is None

    @pytest.mark.asyncio
    async def test_merged_pr(self) -> None:
        """Merged PRs produce pull_request.merged action."""
        from app.workers.github_sync_worker import _fetch_page

        now = datetime.now(UTC)
        created = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        merged = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        merged_dt = now - timedelta(days=1)

        pr_data = [
            {
                "number": 10,
                "state": "closed",
                "title": "Merged PR",
                "user": {"login": "bob", "id": 2},
                "created_at": created,
                "updated_at": merged,
                "merged_at": merged,
                "closed_at": merged,
                "merged": True,
                "html_url": "https://github.com/org/repo/pull/10",
                "additions": 1,
                "deletions": 0,
                "changed_files": 1,
            },
        ]

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=_make_response(200, pr_data, {})),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items[0]["action"] == "pull_request.merged"
        assert items[0]["document_id"] == "pr-org/repo#10-merged"
        # merged_at should be used as created_at — verify it's close to merged_dt
        assert abs((items[0]["created_at"] - merged_dt).total_seconds()) < 2

    @pytest.mark.asyncio
    async def test_closed_not_merged_pr(self) -> None:
        """Closed (not merged) PRs produce pull_request.closed action."""
        from app.workers.github_sync_worker import _fetch_page

        now = datetime.now(UTC)
        created = (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        closed = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        pr_data = [
            {
                "number": 11,
                "state": "closed",
                "title": "Rejected PR",
                "user": {"login": "carol", "id": 3},
                "created_at": created,
                "updated_at": closed,
                "merged_at": None,
                "closed_at": closed,
                "merged": False,
                "html_url": "https://github.com/org/repo/pull/11",
                "additions": 0,
                "deletions": 0,
                "changed_files": 0,
            },
        ]

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=_make_response(200, pr_data, {})),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items[0]["action"] == "pull_request.closed"
        assert items[0]["document_id"] == "pr-org/repo#11-closed"

    @pytest.mark.asyncio
    async def test_delta_sync_stops_on_old_prs(self) -> None:
        """Delta sync stops fetching when PRs are older than delta_since."""
        from app.workers.github_sync_worker import _fetch_page

        now = datetime.now(UTC)
        recent_pr = {
            "number": 100,
            "state": "open",
            "title": "Recent",
            "user": {"login": "dev", "id": 1},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "merged_at": None,
            "closed_at": None,
            "merged": False,
            "html_url": "",
            "additions": 0,
            "deletions": 0,
            "changed_files": 0,
        }
        old_pr = {
            "number": 50,
            "state": "open",
            "title": "Old",
            "user": {"login": "dev", "id": 1},
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
            "merged_at": None,
            "closed_at": None,
            "merged": False,
            "html_url": "",
            "additions": 0,
            "deletions": 0,
            "changed_files": 0,
        }

        resp = _make_response(200, [recent_pr, old_pr], {"link": '<next>; rel="next"'})

        delta = now - timedelta(days=7)

        with (
            _patch_repo_query(["repo1", "repo2"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=resp),
            ),
        ):
            items, cursor = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
                delta_since=delta,
            )

        # Only the recent PR should be included, and early stop means no more pages
        assert len(items) == 1
        assert items[0]["document_id"] == "pr-org/repo1#100-opened"
        assert cursor is None  # stopped early

    @pytest.mark.asyncio
    async def test_pr_bot_detection(self) -> None:
        """PR authors ending in [bot] are flagged."""
        from app.workers.github_sync_worker import _fetch_page

        now = datetime.now(UTC)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        bot_pr = {
            "number": 99,
            "state": "open",
            "title": "Bump deps",
            "user": {"login": "renovate[bot]", "id": 999},
            "created_at": recent,
            "updated_at": recent,
            "merged_at": None,
            "closed_at": None,
            "merged": False,
            "html_url": "",
            "additions": 0,
            "deletions": 0,
            "changed_files": 0,
        }

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=_make_response(200, [bot_pr], {})),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items[0]["actor_is_bot"] is True

    @pytest.mark.asyncio
    async def test_pr_pagination_across_repos(self) -> None:
        """PR fetching paginates across repos with JSON cursor."""
        from app.workers.github_sync_worker import _fetch_page

        now = datetime.now(UTC)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        pr1 = {
            "number": 1,
            "state": "open",
            "title": "PR1",
            "user": {"login": "dev", "id": 1},
            "created_at": recent,
            "updated_at": recent,
            "merged_at": None,
            "closed_at": None,
            "merged": False,
            "html_url": "",
            "additions": 0,
            "deletions": 0,
            "changed_files": 0,
        }

        # repo1 returns PRs with a next page
        resp_page1 = _make_response(200, [pr1], {"link": '<url>; rel="next"'})

        with (
            _patch_repo_query(["repo1", "repo2"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=resp_page1),
            ),
        ):
            items, cursor = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        assert cursor is not None
        cursor_data = json.loads(cursor)
        assert cursor_data["repo_idx"] == 0
        assert cursor_data["page"] == 2

    @pytest.mark.asyncio
    async def test_pr_repo_404_skipped(self) -> None:
        """A 404 on repo is skipped, other repos still processed."""
        from app.workers.github_sync_worker import _fetch_page

        now = datetime.now(UTC)
        recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        pr = {
            "number": 1,
            "state": "open",
            "title": "PR",
            "user": {"login": "dev", "id": 1},
            "created_at": recent,
            "updated_at": recent,
            "merged_at": None,
            "closed_at": None,
            "merged": False,
            "html_url": "",
            "additions": 0,
            "deletions": 0,
            "changed_files": 0,
        }

        resp_404 = _make_response(404, text="Not Found")
        resp_404.raise_for_status = MagicMock()
        resp_ok = _make_response(200, [pr], {})

        with (
            _patch_repo_query(["gone-repo", "good-repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=[resp_404, resp_ok]),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_pr_no_repos(self) -> None:
        """No repos for org returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        with _patch_repo_query([]):
            items, cursor = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items == []
        assert cursor is None

    @pytest.mark.asyncio
    async def test_merged_at_detection_over_merged_flag(self) -> None:
        """A PR with merged_at set (but merged=False) is treated as merged."""
        from app.workers.github_sync_worker import _fetch_page

        now = datetime.now(UTC)
        created = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        merged_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        pr_data = [
            {
                "number": 15,
                "state": "closed",
                "title": "Tricky merge",
                "user": {"login": "dev", "id": 1},
                "created_at": created,
                "updated_at": merged_ts,
                "merged_at": merged_ts,
                "closed_at": merged_ts,
                "merged": False,  # GitHub sometimes has this inconsistency
                "html_url": "",
                "additions": 0,
                "deletions": 0,
                "changed_files": 0,
            },
        ]

        with (
            _patch_repo_query(["repo"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(return_value=_make_response(200, pr_data, {})),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert items[0]["action"] == "pull_request.merged"


# ── _upsert_activity_events tests ────────────────────────────────────────────


class TestUpsertActivityEvents:
    """Tests for the _upsert_activity_events function."""

    @pytest.mark.asyncio
    async def test_insert_events(self) -> None:
        """Events are inserted into events table and event_dedup."""
        from app.workers.github_sync_worker import _upsert_activity_events

        mock_session = AsyncMock()

        # First execute: dedup check → no existing row
        dedup_result = MagicMock()
        dedup_result.fetchone.return_value = None

        # Second execute: INSERT INTO events → return id
        insert_result = MagicMock()
        insert_result.fetchone.return_value = (42,)

        # Third execute: INSERT INTO event_dedup
        dedup_insert_result = MagicMock()

        mock_session.execute = AsyncMock(
            side_effect=[dedup_result, insert_result, dedup_insert_result]
        )
        mock_session.commit = AsyncMock()

        items = [
            {
                "document_id": "commit-abc123",
                "action": "git.push",
                "actor": "alice",
                "actor_id": 1,
                "actor_is_bot": False,
                "org": "test-org",
                "repo": "test-org/repo1",
                "created_at": datetime(2024, 6, 1, 10, 0, tzinfo=UTC),
                "data": json.dumps({"sha": "abc123", "message": "hello", "url": ""}),
                "ingestion_source": "github_api_sync",
                "source_file_path": "api/test-org/repo1/commits",
            },
        ]

        await _upsert_activity_events(mock_session, "test-org", items)

        # Should have called execute 3 times: dedup check, insert event, insert dedup
        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deduplication_skips_existing(self) -> None:
        """Events already in event_dedup are skipped."""
        from app.workers.github_sync_worker import _upsert_activity_events

        mock_session = AsyncMock()

        # Dedup check returns existing row
        dedup_result = MagicMock()
        dedup_result.fetchone.return_value = (1,)

        mock_session.execute = AsyncMock(return_value=dedup_result)
        mock_session.commit = AsyncMock()

        items = [
            {
                "document_id": "commit-existing",
                "action": "git.push",
                "actor": "alice",
                "actor_id": 1,
                "actor_is_bot": False,
                "org": "org",
                "repo": "org/repo",
                "created_at": datetime(2024, 6, 1, tzinfo=UTC),
                "data": "{}",
                "ingestion_source": "github_api_sync",
                "source_file_path": "api/org/repo/commits",
            },
        ]

        await _upsert_activity_events(mock_session, "org", items)

        # Only the dedup check should have been called (1 time),
        # then commit
        assert mock_session.execute.call_count == 1
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_items(self) -> None:
        """Empty items list returns immediately without DB calls."""
        from app.workers.github_sync_worker import _upsert_activity_events

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        await _upsert_activity_events(mock_session, "org", [])

        mock_session.execute.assert_not_called()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_document_id_skipped(self) -> None:
        """Items without document_id are silently skipped."""
        from app.workers.github_sync_worker import _upsert_activity_events

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.execute = AsyncMock()

        items = [
            {
                "action": "git.push",
                "actor": "alice",
                "org": "org",
                "created_at": datetime(2024, 6, 1, tzinfo=UTC),
                "data": "{}",
                "ingestion_source": "github_api_sync",
                "source_file_path": "api/org/repo/commits",
            },
        ]

        await _upsert_activity_events(mock_session, "org", items)

        # No DB calls for items without document_id, only commit
        mock_session.execute.assert_not_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_action_skipped(self) -> None:
        """Items without action are silently skipped."""
        from app.workers.github_sync_worker import _upsert_activity_events

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.execute = AsyncMock()

        items = [
            {
                "document_id": "commit-test",
                "actor": "alice",
                "org": "org",
                "created_at": datetime(2024, 6, 1, tzinfo=UTC),
                "data": "{}",
                "ingestion_source": "github_api_sync",
                "source_file_path": "api/org/repo/commits",
            },
        ]

        await _upsert_activity_events(mock_session, "org", items)

        mock_session.execute.assert_not_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_data_dict_converted_to_json(self) -> None:
        """If data is a dict instead of a string, it gets JSON-serialized."""
        from app.workers.github_sync_worker import _upsert_activity_events

        mock_session = AsyncMock()

        dedup_result = MagicMock()
        dedup_result.fetchone.return_value = None

        insert_result = MagicMock()
        insert_result.fetchone.return_value = (1,)

        dedup_insert_result = MagicMock()

        mock_session.execute = AsyncMock(
            side_effect=[dedup_result, insert_result, dedup_insert_result]
        )
        mock_session.commit = AsyncMock()

        items = [
            {
                "document_id": "commit-dict-data",
                "action": "git.push",
                "actor": "alice",
                "actor_id": 1,
                "actor_is_bot": False,
                "org": "org",
                "repo": "org/repo",
                "created_at": datetime(2024, 6, 1, tzinfo=UTC),
                "data": {"sha": "abc", "message": "test", "url": ""},
                "ingestion_source": "github_api_sync",
                "source_file_path": "api/org/repo/commits",
            },
        ]

        await _upsert_activity_events(mock_session, "org", items)

        # Verify the INSERT call used a JSON string for data
        insert_call = mock_session.execute.call_args_list[1]
        params = insert_call[0][1]
        assert isinstance(params["data"], str)
        parsed = json.loads(params["data"])
        assert parsed["sha"] == "abc"

    @pytest.mark.asyncio
    async def test_on_conflict_do_nothing_returns_no_row(self) -> None:
        """When ON CONFLICT DO NOTHING produces no RETURNING, skip dedup insert."""
        from app.workers.github_sync_worker import _upsert_activity_events

        mock_session = AsyncMock()

        dedup_result = MagicMock()
        dedup_result.fetchone.return_value = None

        # INSERT returns no row (conflict)
        insert_result = MagicMock()
        insert_result.fetchone.return_value = None

        mock_session.execute = AsyncMock(side_effect=[dedup_result, insert_result])
        mock_session.commit = AsyncMock()

        items = [
            {
                "document_id": "commit-conflict",
                "action": "git.push",
                "actor": "alice",
                "actor_id": 1,
                "actor_is_bot": False,
                "org": "org",
                "repo": "org/repo",
                "created_at": datetime(2024, 6, 1, tzinfo=UTC),
                "data": "{}",
                "ingestion_source": "github_api_sync",
                "source_file_path": "api/org/repo/commits",
            },
        ]

        await _upsert_activity_events(mock_session, "org", items)

        # Only 2 calls: dedup check + insert (no dedup insert since no row returned)
        assert mock_session.execute.call_count == 2
        mock_session.commit.assert_called_once()


# ── _upsert_items dispatcher tests ───────────────────────────────────────────


class TestUpsertItemsDispatcher:
    """Tests that _upsert_items correctly dispatches to _upsert_activity_events."""

    @pytest.mark.asyncio
    async def test_dispatches_repo_commits(self) -> None:
        """repo_commits entity type routes to _upsert_activity_events."""
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()

        with patch(
            "app.workers.github_sync_worker._upsert_activity_events",
            new=AsyncMock(),
        ) as mock_upsert:
            await _upsert_items(mock_session, "repo_commits", "test-org", [{"item": 1}])
            mock_upsert.assert_called_once_with(mock_session, "test-org", [{"item": 1}])

    @pytest.mark.asyncio
    async def test_dispatches_pull_requests(self) -> None:
        """pull_requests entity type routes to _upsert_activity_events."""
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()

        with patch(
            "app.workers.github_sync_worker._upsert_activity_events",
            new=AsyncMock(),
        ) as mock_upsert:
            await _upsert_items(mock_session, "pull_requests", "test-org", [{"item": 1}])
            mock_upsert.assert_called_once_with(mock_session, "test-org", [{"item": 1}])


# ── Entity registration tests ────────────────────────────────────────────────


class TestEntityRegistration:
    """Verify new entity types are registered in the right places."""

    def test_repo_commits_in_scope_type(self) -> None:
        """repo_commits is a valid ScopeType literal."""
        from app.schemas.github_sync import SyncTriggerRequest

        req = SyncTriggerRequest(scope="repo_commits")
        assert req.scope == "repo_commits"

    def test_pull_requests_in_scope_type(self) -> None:
        """pull_requests is a valid ScopeType literal."""
        from app.schemas.github_sync import SyncTriggerRequest

        req = SyncTriggerRequest(scope="pull_requests")
        assert req.scope == "pull_requests"

    def test_schedule_scope_validates_repo_commits(self) -> None:
        """repo_commits is accepted by SyncScheduleUpdateRequest.scope validator."""
        from app.schemas.github_sync import SyncScheduleUpdateRequest

        req = SyncScheduleUpdateRequest(scope="repo_commits")
        assert req.scope == "repo_commits"

    def test_schedule_scope_validates_pull_requests(self) -> None:
        """pull_requests is accepted by SyncScheduleUpdateRequest.scope validator."""
        from app.schemas.github_sync import SyncScheduleUpdateRequest

        req = SyncScheduleUpdateRequest(scope="pull_requests")
        assert req.scope == "pull_requests"


# ── Migration test ────────────────────────────────────────────────────────────


class TestMigration0026:
    """Tests for the ingestion_source CHECK constraint migration."""

    def test_migration_revision_chain(self) -> None:
        """Migration 0026 follows 0025 in the revision chain."""
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parent.parent / (
            "alembic/versions/0026_widen_ingestion_source_check.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0026", path)
        assert spec is not None
        assert spec.loader is not None
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)

        assert m.revision == "0026"
        assert m.down_revision == "0025"

    def test_upgrade_function_exists(self) -> None:
        """Migration has an upgrade function."""
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parent.parent / (
            "alembic/versions/0026_widen_ingestion_source_check.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0026_up", path)
        assert spec is not None
        assert spec.loader is not None
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)

        assert callable(m.upgrade)

    def test_downgrade_function_exists(self) -> None:
        """Migration has a downgrade function."""
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parent.parent / (
            "alembic/versions/0026_widen_ingestion_source_check.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0026_down", path)
        assert spec is not None
        assert spec.loader is not None
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)

        assert callable(m.downgrade)
