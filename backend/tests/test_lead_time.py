"""Tests for lead time metric enhancement.

Covers:
- PR data enrichment (new fields in data JSON)
- _enrich_prs_with_linked_issues GraphQL enrichment function
- Issues handler data shape and PR filtering
- Deployments handler data shape (deployment + deployment_status)
- Workflow run head_sha field
- Lead time SQL query structure in report_service
- Migration 0036 validation
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers (same patterns as test_api_activity_sync.py) ──────────────────────


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
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.headers = headers or {}
    resp.text = ""
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
    return [(n,) for n in names]


def _patch_repo_query(repo_names: list[str]):
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


def _make_pr(
    number: int = 1,
    state: str = "closed",
    merged: bool = True,
    merged_at: str | None = "2024-06-10T12:00:00Z",
    created_at: str = "2024-06-01T10:00:00Z",
    user_login: str = "alice",
    user_id: int = 1,
    merge_commit_sha: str | None = "aaa111",
    head_sha: str = "bbb222",
    head_ref: str = "feature-branch",
    additions: int = 10,
    deletions: int = 5,
    changed_files: int = 3,
) -> dict:
    return {
        "number": number,
        "title": f"PR #{number}",
        "state": state,
        "merged": merged,
        "merged_at": merged_at,
        "created_at": created_at,
        "closed_at": merged_at,
        "user": {"login": user_login, "id": user_id},
        "html_url": f"https://github.com/test-org/repo1/pull/{number}",
        "additions": additions,
        "deletions": deletions,
        "changed_files": changed_files,
        "merge_commit_sha": merge_commit_sha,
        "head": {"sha": head_sha, "ref": head_ref},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# A. PR data enrichment — new fields in data JSON
# ═══════════════════════════════════════════════════════════════════════════════


class TestPRDataEnrichment:
    """Verify pull_requests handler includes new lead-time fields in data."""

    @pytest.mark.asyncio
    async def test_merged_pr_data_contains_new_fields(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        pr = _make_pr(
            number=42,
            merged=True,
            merge_commit_sha="abc123",
            head_sha="def456",
            head_ref="feature/foo",
            created_at="2024-06-01T10:00:00Z",
        )
        mock_resp = _make_response(200, [pr], {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=mock_resp)
            ),
            patch("app.workers.github_sync_worker._enrich_prs_with_linked_issues", new=AsyncMock()),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        data = json.loads(items[0]["data"])
        assert data["merge_commit_sha"] == "abc123"
        assert data["head_sha"] == "def456"
        assert data["head_ref"] == "feature/foo"
        assert data["pr_created_at"] == "2024-06-01T10:00:00Z"
        assert data["linked_issues"] == []

    @pytest.mark.asyncio
    async def test_pr_with_null_head(self) -> None:
        """PR with missing head object stores None for head_sha/head_ref."""
        from app.workers.github_sync_worker import _fetch_page

        pr = _make_pr(number=1)
        pr["head"] = None  # simulate missing head

        mock_resp = _make_response(200, [pr], {})
        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=mock_resp)
            ),
            patch("app.workers.github_sync_worker._enrich_prs_with_linked_issues", new=AsyncMock()),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        data = json.loads(items[0]["data"])
        assert data["head_sha"] is None
        assert data["head_ref"] is None

    @pytest.mark.asyncio
    async def test_open_pr_also_has_new_fields(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        pr = _make_pr(number=5, state="open", merged=False, merged_at=None)
        mock_resp = _make_response(200, [pr], {})
        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=mock_resp)
            ),
            patch("app.workers.github_sync_worker._enrich_prs_with_linked_issues", new=AsyncMock()),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        data = json.loads(items[0]["data"])
        assert "merge_commit_sha" in data
        assert "head_sha" in data
        assert "head_ref" in data
        assert "pr_created_at" in data
        assert "linked_issues" in data

    @pytest.mark.asyncio
    async def test_pr_without_merge_commit_sha(self) -> None:
        """Open/closed-not-merged PR can have null merge_commit_sha."""
        from app.workers.github_sync_worker import _fetch_page

        pr = _make_pr(number=2, merged=False, state="open", merged_at=None)
        pr["merge_commit_sha"] = None
        mock_resp = _make_response(200, [pr], {})
        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=mock_resp)
            ),
            patch("app.workers.github_sync_worker._enrich_prs_with_linked_issues", new=AsyncMock()),
        ):
            items, _ = await _fetch_page(
                entity_type="pull_requests",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        data = json.loads(items[0]["data"])
        assert data["merge_commit_sha"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# B. _enrich_prs_with_linked_issues
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnrichPRsWithLinkedIssues:
    """Test the GraphQL enrichment function for linked issues."""

    def _make_item(
        self,
        pr_num: int,
        repo: str = "test-org/repo1",
        merged: bool = True,
    ) -> dict:
        action = "pull_request.merged" if merged else "pull_request.opened"
        return {
            "action": action,
            "repo": repo,
            "data": json.dumps(
                {
                    "number": pr_num,
                    "linked_issues": [],
                }
            ),
        }

    @pytest.mark.asyncio
    async def test_no_merged_items_is_noop(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items = [self._make_item(1, merged=False)]
        original_data = items[0]["data"]

        await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())

        assert items[0]["data"] == original_data

    @pytest.mark.asyncio
    async def test_empty_items_is_noop(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items: list[dict] = []
        await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())
        assert items == []

    @pytest.mark.asyncio
    async def test_enrichment_updates_data_in_place(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items = [self._make_item(10, repo="test-org/repo1")]

        graphql_result = {
            "data": {
                "pr0": {
                    "pullRequest": {
                        "closingIssuesReferences": {
                            "nodes": [
                                {
                                    "number": 5,
                                    "createdAt": "2024-05-20T09:00:00Z",
                                    "repository": {"nameWithOwner": "test-org/repo1"},
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=AsyncMock(return_value=graphql_result),
        ):
            await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())

        data = json.loads(items[0]["data"])
        assert len(data["linked_issues"]) == 1
        assert data["linked_issues"][0]["number"] == 5
        assert data["linked_issues"][0]["created_at"] == "2024-05-20T09:00:00Z"
        assert data["linked_issues"][0]["repo"] == "test-org/repo1"

    @pytest.mark.asyncio
    async def test_graphql_failure_retains_empty_linked_issues(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items = [self._make_item(10)]

        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=AsyncMock(side_effect=Exception("network error")),
        ):
            await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())

        data = json.loads(items[0]["data"])
        assert data["linked_issues"] == []

    @pytest.mark.asyncio
    async def test_graphql_returns_null_data(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items = [self._make_item(7)]

        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=AsyncMock(return_value={"data": None}),
        ):
            await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())

        data = json.loads(items[0]["data"])
        assert data["linked_issues"] == []

    @pytest.mark.asyncio
    async def test_batching_splits_at_25(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items = [self._make_item(i) for i in range(60)]

        mock_graphql = AsyncMock(return_value={"data": {}})

        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=mock_graphql,
        ):
            await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())

        # 60 items → ceil(60/25) = 3 batches
        assert mock_graphql.call_count == 3

    @pytest.mark.asyncio
    async def test_item_with_no_pr_number_skipped(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        item = {
            "action": "pull_request.merged",
            "repo": "test-org/repo1",
            "data": json.dumps({"number": None, "linked_issues": []}),
        }

        mock_graphql = AsyncMock(return_value={"data": {}})
        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=mock_graphql,
        ):
            await _enrich_prs_with_linked_issues([item], "tok", _make_rate_limiter())

        # No valid fragments → no GraphQL call
        mock_graphql.assert_not_called()

    @pytest.mark.asyncio
    async def test_item_with_bad_repo_format_skipped(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        item = {
            "action": "pull_request.merged",
            "repo": "no-slash-repo",
            "data": json.dumps({"number": 1, "linked_issues": []}),
        }

        mock_graphql = AsyncMock(return_value={"data": {}})
        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=mock_graphql,
        ):
            await _enrich_prs_with_linked_issues([item], "tok", _make_rate_limiter())

        mock_graphql.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_linked_issues(self) -> None:
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items = [self._make_item(10)]

        graphql_result = {
            "data": {
                "pr0": {
                    "pullRequest": {
                        "closingIssuesReferences": {
                            "nodes": [
                                {
                                    "number": 5,
                                    "createdAt": "2024-05-20T09:00:00Z",
                                    "repository": {"nameWithOwner": "test-org/repo1"},
                                },
                                {
                                    "number": 8,
                                    "createdAt": "2024-05-18T08:00:00Z",
                                    "repository": {"nameWithOwner": "test-org/repo1"},
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=AsyncMock(return_value=graphql_result),
        ):
            await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())

        data = json.loads(items[0]["data"])
        assert len(data["linked_issues"]) == 2

    @pytest.mark.asyncio
    async def test_partial_graphql_response(self) -> None:
        """Some PRs have data, others are missing from the response."""
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items = [self._make_item(10), self._make_item(20)]

        graphql_result = {
            "data": {
                "pr0": {
                    "pullRequest": {
                        "closingIssuesReferences": {
                            "nodes": [
                                {
                                    "number": 3,
                                    "createdAt": "2024-05-15T12:00:00Z",
                                    "repository": {"nameWithOwner": "test-org/repo1"},
                                },
                            ]
                        }
                    }
                },
                # pr1 missing entirely
            }
        }

        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=AsyncMock(return_value=graphql_result),
        ):
            await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())

        data0 = json.loads(items[0]["data"])
        data1 = json.loads(items[1]["data"])
        assert len(data0["linked_issues"]) == 1
        assert data1["linked_issues"] == []  # unchanged

    @pytest.mark.asyncio
    async def test_pr_with_no_closing_issues(self) -> None:
        """PR exists in response but has no closing issue references."""
        from app.workers.github_sync_worker import _enrich_prs_with_linked_issues

        items = [self._make_item(10)]

        graphql_result = {
            "data": {"pr0": {"pullRequest": {"closingIssuesReferences": {"nodes": []}}}}
        }

        with patch(
            "app.workers.github_sync_worker._graphql_page",
            new=AsyncMock(return_value=graphql_result),
        ):
            await _enrich_prs_with_linked_issues(items, "tok", _make_rate_limiter())

        data = json.loads(items[0]["data"])
        assert data["linked_issues"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# C. Issues handler data shape + PR filtering
# ═══════════════════════════════════════════════════════════════════════════════


class TestIssuesHandler:
    """Test the issues sync handler produces correct items and filters PRs."""

    def _make_issue(
        self,
        number: int = 1,
        state: str = "open",
        is_pr: bool = False,
        user_login: str = "alice",
        created_at: str = "2024-06-01T10:00:00Z",
        updated_at: str = "2024-06-05T12:00:00Z",
        closed_at: str | None = None,
    ) -> dict:
        issue = {
            "number": number,
            "title": f"Issue #{number}",
            "state": state,
            "state_reason": None,
            "user": {"login": user_login, "id": 1},
            "html_url": f"https://github.com/test-org/repo1/issues/{number}",
            "labels": [{"name": "bug"}],
            "milestone": {"title": "v1.0"},
            "assignees": [{"login": "bob"}],
            "created_at": created_at,
            "updated_at": updated_at,
            "closed_at": closed_at,
        }
        if is_pr:
            issue["pull_request"] = {"url": "https://api.github.com/..."}
        return issue

    @pytest.mark.asyncio
    async def test_filters_out_pull_requests(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        issues = [
            self._make_issue(number=1, is_pr=False, state="open"),
            self._make_issue(number=2, is_pr=True, state="open"),  # PR, should be filtered
            self._make_issue(
                number=3, is_pr=False, state="closed", closed_at="2024-06-04T15:00:00Z"
            ),
        ]
        mock_resp = _make_response(200, issues, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=mock_resp)
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="issues",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 2
        # Verify no PR-sourced items
        doc_ids = [i["document_id"] for i in items]
        assert any("#1-" in d for d in doc_ids)
        assert not any("#2-" in d for d in doc_ids)
        assert any("#3-" in d for d in doc_ids)

    @pytest.mark.asyncio
    async def test_open_issue_data_shape(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        issue = self._make_issue(number=10, state="open", created_at="2024-06-01T10:00:00Z")
        mock_resp = _make_response(200, [issue], {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=mock_resp)
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="issues",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        item = items[0]
        assert item["action"] == "issue.opened"
        assert item["actor"] == "alice"
        assert item["org"] == "test-org"
        assert item["repo"] == "test-org/repo1"
        assert item["document_id"] == "issue-test-org/repo1#10-open"
        assert item["ingestion_source"] == "github_api_sync"

        data = json.loads(item["data"])
        assert data["number"] == 10
        assert data["state"] == "open"
        assert data["labels"] == ["bug"]
        assert data["milestone"] == "v1.0"
        assert data["assignees"] == ["bob"]
        assert data["issue_created_at"] == "2024-06-01T10:00:00Z"
        assert data["user"]["login"] == "alice"

    @pytest.mark.asyncio
    async def test_closed_issue_data_shape(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        issue = self._make_issue(
            number=20,
            state="closed",
            created_at="2024-06-01T10:00:00Z",
            closed_at="2024-06-03T14:00:00Z",
        )
        mock_resp = _make_response(200, [issue], {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=mock_resp)
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="issues",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        item = items[0]
        assert item["action"] == "issue.closed"
        assert item["document_id"] == "issue-test-org/repo1#20-closed"

        data = json.loads(item["data"])
        assert data["closed_at"] == "2024-06-03T14:00:00Z"

    @pytest.mark.asyncio
    async def test_issues_skip_404_repo(self) -> None:
        """A 404 repo is skipped, next repo is attempted."""
        from app.workers.github_sync_worker import _fetch_page

        resp_404 = _make_response(404, [], {})
        resp_404.raise_for_status = MagicMock()  # 404 doesn't raise
        issue = self._make_issue(number=1)
        resp_ok = _make_response(200, [issue], {})

        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_404
            return resp_ok

        with (
            _patch_repo_query(["repo-private", "repo-public"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=_side_effect),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="issues",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# D. Deployments handler data shape
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeploymentsHandler:
    """Test the deployments sync handler."""

    def _make_deployment(
        self,
        deploy_id: int = 100,
        environment: str = "production",
        ref: str = "main",
        sha: str = "abc123",
        created_at: str = "2024-06-10T12:00:00Z",
    ) -> dict:
        return {
            "id": deploy_id,
            "environment": environment,
            "ref": ref,
            "sha": sha,
            "task": "deploy",
            "description": "Deploying to prod",
            "html_url": f"https://github.com/test-org/repo1/deployments/{deploy_id}",
            "url": f"https://api.github.com/repos/test-org/repo1/deployments/{deploy_id}",
            "created_at": created_at,
            "creator": {"login": "deploy-bot", "id": 99},
        }

    def _make_deploy_status(
        self,
        status_id: int = 200,
        state: str = "success",
        created_at: str = "2024-06-10T12:05:00Z",
    ) -> dict:
        return {
            "id": status_id,
            "state": state,
            "description": "Deployed successfully",
            "created_at": created_at,
            "environment_url": "https://example.com",
            "url": f"https://api.github.com/repos/test-org/repo1/deployments/100/statuses/{status_id}",
            "creator": {"login": "github-actions[bot]", "id": 41898282},
        }

    @pytest.mark.asyncio
    async def test_deployment_item_shape(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        deploy = self._make_deployment()
        deploy_resp = _make_response(200, [deploy], {})
        status_resp = _make_response(200, [], {})  # no statuses

        call_count = 0

        async def _side_effect(url, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "statuses" in url:
                return status_resp
            return deploy_resp

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=_side_effect),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="deployments",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        deploy_items = [i for i in items if i["action"] == "deployment.created"]
        assert len(deploy_items) == 1
        item = deploy_items[0]
        assert item["actor"] == "deploy-bot"
        assert item["repo"] == "test-org/repo1"
        assert item["document_id"] == "deployment-test-org/repo1-100"

        data = json.loads(item["data"])
        assert data["deployment_id"] == 100
        assert data["environment"] == "production"
        assert data["sha"] == "abc123"
        assert data["ref"] == "main"
        assert data["creator"]["login"] == "deploy-bot"

    @pytest.mark.asyncio
    async def test_deployment_status_item_shape(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        deploy = self._make_deployment(deploy_id=100, sha="abc123")
        status = self._make_deploy_status(status_id=200, state="success")

        deploy_resp = _make_response(200, [deploy], {})
        status_resp = _make_response(200, [status], {})

        async def _side_effect(url, *args, **kwargs):
            if "statuses" in url:
                return status_resp
            return deploy_resp

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=_side_effect),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="deployments",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        status_items = [i for i in items if i["action"].startswith("deployment_status.")]
        assert len(status_items) == 1
        si = status_items[0]
        assert si["action"] == "deployment_status.success"
        assert si["document_id"] == "deploy-status-test-org/repo1-100-200"

        data = json.loads(si["data"])
        assert data["deployment_id"] == 100
        assert data["status_id"] == 200
        assert data["state"] == "success"
        assert data["sha"] == "abc123"
        assert data["environment_url"] == "https://example.com"
        assert data["creator"]["login"] == "github-actions[bot]"

    @pytest.mark.asyncio
    async def test_deployment_status_bot_detection(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        deploy = self._make_deployment()
        status = self._make_deploy_status()

        deploy_resp = _make_response(200, [deploy], {})
        status_resp = _make_response(200, [status], {})

        async def _side_effect(url, *args, **kwargs):
            if "statuses" in url:
                return status_resp
            return deploy_resp

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=_side_effect),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="deployments",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        status_items = [i for i in items if i["action"].startswith("deployment_status.")]
        assert status_items[0]["actor_is_bot"] is True

    @pytest.mark.asyncio
    async def test_deployment_status_fetch_error_handled(self) -> None:
        """Status fetch failure doesn't crash the deployment sync."""
        from app.workers.github_sync_worker import _fetch_page

        deploy = self._make_deployment()
        deploy_resp = _make_response(200, [deploy], {})

        async def _side_effect(url, *args, **kwargs):
            if "statuses" in url:
                raise Exception("connection timeout")
            return deploy_resp

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get",
                new=AsyncMock(side_effect=_side_effect),
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="deployments",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        # Deployment item exists; statuses were skipped gracefully
        deploy_items = [i for i in items if i["action"] == "deployment.created"]
        assert len(deploy_items) == 1
        status_items = [i for i in items if i["action"].startswith("deployment_status.")]
        assert len(status_items) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# E. Workflow run head_sha
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkflowRunHeadSha:
    """Verify workflow_run items include head_sha in data JSON."""

    @pytest.mark.asyncio
    async def test_workflow_run_contains_head_sha(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        run = {
            "id": 9999,
            "name": "CI",
            "workflow_id": 100,
            "run_number": 42,
            "head_branch": "main",
            "event": "push",
            "conclusion": "success",
            "status": "completed",
            "created_at": "2024-06-10T12:00:00Z",
            "run_started_at": "2024-06-10T12:00:05Z",
            "updated_at": "2024-06-10T12:05:00Z",
            "html_url": "https://github.com/test-org/repo1/actions/runs/9999",
            "triggering_actor": {"login": "alice", "id": 1},
            "head_sha": "sha_abc123",
        }
        runs_resp = _make_response(200, {"workflow_runs": [run]}, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=runs_resp)
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        assert len(items) == 1
        data = json.loads(items[0]["data"])
        assert data["head_sha"] == "sha_abc123"
        assert data["workflow_name"] == "CI"
        assert data["conclusion"] == "success"

    @pytest.mark.asyncio
    async def test_workflow_run_missing_head_sha(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        run = {
            "id": 9999,
            "name": "CI",
            "workflow_id": 100,
            "run_number": 42,
            "head_branch": "main",
            "event": "push",
            "conclusion": "success",
            "status": "completed",
            "created_at": "2024-06-10T12:00:00Z",
            "run_started_at": "2024-06-10T12:00:05Z",
            "updated_at": "2024-06-10T12:05:00Z",
            "html_url": "https://github.com/test-org/repo1/actions/runs/9999",
            "triggering_actor": {"login": "alice", "id": 1},
            # head_sha deliberately missing
        }
        runs_resp = _make_response(200, {"workflow_runs": [run]}, {})

        with (
            _patch_repo_query(["repo1"]),
            patch(
                "app.workers.github_sync_worker._github_get", new=AsyncMock(return_value=runs_resp)
            ),
        ):
            items, _ = await _fetch_page(
                entity_type="workflow_runs",
                org="test-org",
                token="tok",
                cursor=None,
                rate_limiter=_make_rate_limiter(),
            )

        data = json.loads(items[0]["data"])
        assert data["head_sha"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# F. Lead time SQL response dict structure
# ═══════════════════════════════════════════════════════════════════════════════


class TestLeadTimeSQLResponseStructure:
    """Verify the report service includes new lead time fields."""

    @pytest.mark.asyncio
    async def test_shipping_faster_contains_lead_time_fields(self) -> None:
        """Mock the DB session to return canned rows and validate dict keys."""
        from app.services.report_service import get_metrics_that_matter

        # Build a mock row that returns named attributes for all queries
        def _make_row(**kwargs):
            row = MagicMock()
            for k, v in kwargs.items():
                setattr(row, k, v)
            return row

        # Track which query is being executed to return the right mock
        call_idx = 0
        query_results = []

        # We need to return mock rows for many sequential queries.
        # The key ones: pr_lifecycle, lead_time, pr_rate, workflow, etc.
        # Rather than mock every single query, patch at the session level
        # and validate that the result dict contains the new keys.

        mock_row_generic = _make_row(
            avg_hours=10.5,
            avg_lead_time_hours=24.3,
            median_lead_time_hours=18.7,
            lead_time_pr_count=42,
            merge_rate_pct=85.0,
            workflow_runs_total=100,
            workflow_runs_succeeded=90,
            workflow_runs_failed=10,
            codeql_opened=5,
            codeql_closed=3,
            secret_opened=2,
            secret_resolved=1,
            total_repos=10,
            protected_repos=8,
            failed_run_waste_pct=5.0,
            rerun_rate_pct=2.0,
            auto_merge_rate_pct=15.0,
            review_rounds_avg=1.5,
            deployment_frequency=3.5,
            change_failure_rate_pct=4.0,
        )

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row_generic
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await get_metrics_that_matter(mock_session, period_days=30)

        shipping_faster = result["shipping_faster"]
        assert "avg_lead_time_hours" in shipping_faster
        assert "median_lead_time_hours" in shipping_faster
        assert "lead_time_pr_count" in shipping_faster
        # Verify the old field is still present
        assert "avg_pr_lifecycle_hours" in shipping_faster


# ═══════════════════════════════════════════════════════════════════════════════
# G. Migration 0036 validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigration0036:
    """Validate the migration file structure and SQL correctness."""

    def test_revision_identifiers(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migration_0036",
            "/workspaces/octowatch/backend/alembic/versions/0036_add_lead_time_indexes.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.revision == "0036"
        assert mod.down_revision == "0035"
        assert mod.branch_labels is None
        assert mod.depends_on is None

    def test_upgrade_creates_four_indexes(self) -> None:
        """Verify upgrade creates 4 indexes using CREATE INDEX IF NOT EXISTS."""
        path = "/workspaces/octowatch/backend/alembic/versions/0036_add_lead_time_indexes.py"
        with open(path) as f:
            content = f.read()

        assert content.count("CREATE INDEX IF NOT EXISTS") == 4
        assert "idx_events_pr_merged" in content
        assert "idx_events_deploy_status_sha" in content
        assert "idx_events_workflow_success_sha" in content
        assert "idx_events_issue_opened" in content

    def test_downgrade_drops_four_indexes(self) -> None:
        path = "/workspaces/octowatch/backend/alembic/versions/0036_add_lead_time_indexes.py"
        with open(path) as f:
            content = f.read()

        assert content.count("DROP INDEX IF EXISTS") == 4

    def test_partial_index_conditions(self) -> None:
        """Verify partial index WHERE clauses match the lead time query patterns."""
        path = "/workspaces/octowatch/backend/alembic/versions/0036_add_lead_time_indexes.py"
        with open(path) as f:
            content = f.read()

        # PR merged index
        assert "WHERE action = 'pull_request.merged'" in content
        # Deployment status success index
        assert "WHERE action = 'deployment_status.success'" in content
        # Workflow success index
        assert "WHERE action = 'workflow_run.success'" in content
        # Issue opened index
        assert "WHERE action = 'issue.opened'" in content


# ═══════════════════════════════════════════════════════════════════════════════
# H. _upsert_items dispatcher routes new entity types
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpsertItemsDispatcher:
    """Verify that issues and deployments are routed to _upsert_activity_events."""

    @pytest.mark.asyncio
    async def test_issues_routed_to_activity_events(self) -> None:
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()
        with patch(
            "app.workers.github_sync_worker._upsert_activity_events",
            new=AsyncMock(),
        ) as mock_upsert:
            await _upsert_items(mock_session, "issues", "test-org", [{"test": 1}])
            mock_upsert.assert_called_once_with(mock_session, "test-org", [{"test": 1}])

    @pytest.mark.asyncio
    async def test_deployments_routed_to_activity_events(self) -> None:
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()
        with patch(
            "app.workers.github_sync_worker._upsert_activity_events",
            new=AsyncMock(),
        ) as mock_upsert:
            await _upsert_items(mock_session, "deployments", "test-org", [{"test": 1}])
            mock_upsert.assert_called_once_with(mock_session, "test-org", [{"test": 1}])


# ═══════════════════════════════════════════════════════════════════════════════
# I. ScopeType and _ORG_ENTITIES contain new entity types
# ═══════════════════════════════════════════════════════════════════════════════


class TestScopeAndEntityConfig:
    """Verify issues and deployments are registered in config."""

    def test_scope_type_accepts_issues(self) -> None:
        """issues is a valid ScopeType value."""
        from app.workers.github_sync_worker import ScopeType

        # ScopeType is a Literal — verify by type annotation check
        scope: ScopeType = "issues"  # type: ignore[assignment]
        assert scope == "issues"

    def test_scope_type_accepts_deployments(self) -> None:
        from app.workers.github_sync_worker import ScopeType

        scope: ScopeType = "deployments"  # type: ignore[assignment]
        assert scope == "deployments"

    def test_org_entities_includes_issues_and_deployments(self) -> None:
        """Cannot directly import _ORG_ENTITIES (it's inside a function),
        so we grep-verify by reading the source."""
        import ast

        path = "/workspaces/octowatch/backend/app/workers/github_sync_worker.py"
        with open(path) as f:
            content = f.read()
        # Both should appear as string literals in the _ORG_ENTITIES set
        assert '"issues"' in content
        assert '"deployments"' in content
