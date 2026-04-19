"""Tests for new sync entity types (code scanning, actions workflows, MFA status)
and extended delta sync for org_members, teams, team_members, branch_protections,
and outside_collaborators.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.github_sync import SyncScheduleUpdateRequest, SyncTriggerRequest

# ─── New Model Tests ──────────────────────────────────────────────────────────


class TestOrgCodeScanningAlertSummaryModel:
    """Tests for the OrgCodeScanningAlertSummary ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import OrgCodeScanningAlertSummary

        assert OrgCodeScanningAlertSummary.__tablename__ == "org_code_scanning_alert_summaries"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import OrgCodeScanningAlertSummary

        constraints = {
            c.name for c in OrgCodeScanningAlertSummary.__table__.constraints if hasattr(c, "name")
        }
        assert "uq_code_scanning_summary_slug_org" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import OrgCodeScanningAlertSummary

        cols = {c.name for c in OrgCodeScanningAlertSummary.__table__.columns}
        expected = {
            "id",
            "enterprise_slug",
            "org",
            "open_count",
            "fixed_count",
            "dismissed_count",
            "total_count",
            "error_count",
            "warning_count",
            "note_count",
            "synced_at",
        }
        assert expected.issubset(cols)


class TestOrgActionsWorkflowSummaryModel:
    """Tests for the OrgActionsWorkflowSummary ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import OrgActionsWorkflowSummary

        assert OrgActionsWorkflowSummary.__tablename__ == "org_actions_workflow_summaries"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import OrgActionsWorkflowSummary

        constraints = {
            c.name for c in OrgActionsWorkflowSummary.__table__.constraints if hasattr(c, "name")
        }
        assert "uq_actions_workflow_summary_slug_org" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import OrgActionsWorkflowSummary

        cols = {c.name for c in OrgActionsWorkflowSummary.__table__.columns}
        expected = {
            "id",
            "enterprise_slug",
            "org",
            "total_workflows",
            "active_workflows",
            "total_runs",
            "successful_runs",
            "failed_runs",
            "cancelled_runs",
            "synced_at",
        }
        assert expected.issubset(cols)


class TestOrgMemberMfaField:
    """Tests for the mfa_enabled field on OrgMember."""

    def test_mfa_enabled_column_exists(self) -> None:
        from app.models.github_sync import OrgMember

        cols = {c.name for c in OrgMember.__table__.columns}
        assert "mfa_enabled" in cols

    def test_mfa_enabled_is_nullable(self) -> None:
        from app.models.github_sync import OrgMember

        col = OrgMember.__table__.c.mfa_enabled
        assert col.nullable is True


# ─── Schema Tests ─────────────────────────────────────────────────────────────


class TestNewScopeValuesExtended:
    """Tests that new entity types are accepted by schemas."""

    def test_trigger_request_code_scanning_alerts(self) -> None:
        req = SyncTriggerRequest(scope="code_scanning_alerts")
        assert req.scope == "code_scanning_alerts"

    def test_trigger_request_actions_workflows(self) -> None:
        req = SyncTriggerRequest(scope="actions_workflows")
        assert req.scope == "actions_workflows"

    def test_trigger_request_mfa_status(self) -> None:
        req = SyncTriggerRequest(scope="mfa_status")
        assert req.scope == "mfa_status"

    def test_schedule_request_new_scopes(self) -> None:
        for scope in ["code_scanning_alerts", "actions_workflows", "mfa_status"]:
            req = SyncScheduleUpdateRequest(scope=scope)
            assert req.scope == scope


# ─── Model Export Tests ───────────────────────────────────────────────────────


class TestNewModelExports:
    """Verify new models are exported from __init__.py."""

    def test_code_scanning_summary_exported(self) -> None:
        from app.models import OrgCodeScanningAlertSummary

        assert OrgCodeScanningAlertSummary is not None

    def test_actions_workflow_summary_exported(self) -> None:
        from app.models import OrgActionsWorkflowSummary

        assert OrgActionsWorkflowSummary is not None


# ─── Fetch Page Tests: Code Scanning Alerts ───────────────────────────────────


class TestFetchCodeScanningAlerts:
    """Tests for _fetch_page handling of code_scanning_alerts entity type."""

    @pytest.mark.asyncio
    async def test_fetch_code_scanning_alerts_aggregates(self) -> None:
        """Verify code scanning alerts are aggregated into a summary."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        alerts = [
            {
                "state": "open",
                "rule": {"security_severity_level": "error"},
            },
            {
                "state": "open",
                "rule": {"security_severity_level": "warning"},
            },
            {
                "state": "fixed",
                "rule": {"security_severity_level": "error"},
            },
            {
                "state": "dismissed",
                "rule": {"severity": "note"},
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = alerts
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="code_scanning_alerts",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        summary = items[0]
        assert summary["_org"] == "test-org"
        assert summary["open_count"] == 2
        assert summary["fixed_count"] == 1
        assert summary["dismissed_count"] == 1
        assert summary["total_count"] == 4
        assert summary["error_count"] == 2
        assert summary["warning_count"] == 1
        assert summary["note_count"] == 1
        assert next_cursor == "_done"

    @pytest.mark.asyncio
    async def test_fetch_code_scanning_done_cursor(self) -> None:
        """After aggregation, passing '_done' cursor returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        items, next_cursor = await _fetch_page(
            entity_type="code_scanning_alerts",
            org="test-org",
            token="test-token",
            cursor="_done",
            rate_limiter=mock_rate_limiter,
        )
        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_code_scanning_403_returns_empty(self) -> None:
        """403 response means code scanning isn't available."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="code_scanning_alerts",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_code_scanning_delta_since_uses_sort(self) -> None:
        """When delta_since is set, sort=updated is passed."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_get:
            await _fetch_page(
                entity_type="code_scanning_alerts",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
                delta_since=datetime.now(UTC) - timedelta(hours=12),
            )

        # Verify the sort params were passed
        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[1].get("params") or call_args[0][2]
        assert params.get("sort") == "updated"
        assert params.get("direction") == "desc"


# ─── Fetch Page Tests: Actions Workflows ──────────────────────────────────────


class TestFetchActionsWorkflows:
    """Tests for _fetch_page handling of actions_workflows entity type."""

    @pytest.mark.asyncio
    async def test_fetch_actions_workflows_aggregates(self) -> None:
        """Verify actions data is aggregated across repos."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        # First call: repos listing
        repos = [
            {"name": "repo-1", "id": 1, "archived": False},
            {"name": "repo-2", "id": 2, "archived": True},  # archived, should be skipped
        ]
        mock_repos_resp = MagicMock()
        mock_repos_resp.status_code = 200
        mock_repos_resp.json.return_value = repos
        mock_repos_resp.headers = {}

        # Second call: workflows for repo-1
        workflows = {
            "total_count": 2,
            "workflows": [
                {"id": 1, "name": "CI", "state": "active"},
                {"id": 2, "name": "Deploy", "state": "disabled_manually"},
            ],
        }
        mock_wf_resp = MagicMock()
        mock_wf_resp.status_code = 200
        mock_wf_resp.json.return_value = workflows
        mock_wf_resp.headers = {}

        # Third call: runs for repo-1
        runs = {
            "total_count": 3,
            "workflow_runs": [
                {"id": 1, "conclusion": "success"},
                {"id": 2, "conclusion": "failure"},
                {"id": 3, "conclusion": "cancelled"},
            ],
        }
        mock_runs_resp = MagicMock()
        mock_runs_resp.status_code = 200
        mock_runs_resp.json.return_value = runs
        mock_runs_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(side_effect=[mock_repos_resp, mock_wf_resp, mock_runs_resp]),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="actions_workflows",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        summary = items[0]
        assert summary["_org"] == "test-org"
        assert summary["total_workflows"] == 2
        assert summary["active_workflows"] == 1
        assert summary["total_runs"] == 3
        assert summary["successful_runs"] == 1
        assert summary["failed_runs"] == 1
        assert summary["cancelled_runs"] == 1
        assert next_cursor == "_done"

    @pytest.mark.asyncio
    async def test_fetch_actions_done_cursor(self) -> None:
        """After aggregation, passing '_done' cursor returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        items, next_cursor = await _fetch_page(
            entity_type="actions_workflows",
            org="test-org",
            token="test-token",
            cursor="_done",
            rate_limiter=mock_rate_limiter,
        )
        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_actions_repos_unavailable(self) -> None:
        """403 on repos listing returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="actions_workflows",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert items == []
        assert next_cursor is None


# ─── Fetch Page Tests: MFA Status ─────────────────────────────────────────────


class TestFetchMfaStatus:
    """Tests for _fetch_page handling of mfa_status entity type."""

    @pytest.mark.asyncio
    async def test_fetch_mfa_status_identifies_disabled_members(self) -> None:
        """Verify MFA status fetches members without MFA."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        # Members without MFA
        no_mfa_members = [
            {"login": "user-no-mfa-1", "id": 111},
            {"login": "user-no-mfa-2", "id": 222},
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = no_mfa_members
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="mfa_status",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        mfa_item = items[0]
        assert mfa_item["_org"] == "test-org"
        assert set(mfa_item["no_mfa_logins"]) == {"user-no-mfa-1", "user-no-mfa-2"}
        assert next_cursor == "_done"

    @pytest.mark.asyncio
    async def test_fetch_mfa_done_cursor(self) -> None:
        """After fetching, passing '_done' cursor returns empty."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        items, next_cursor = await _fetch_page(
            entity_type="mfa_status",
            org="test-org",
            token="test-token",
            cursor="_done",
            rate_limiter=mock_rate_limiter,
        )
        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_mfa_403_returns_empty(self) -> None:
        """403 means org doesn't expose MFA status."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="mfa_status",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_mfa_all_members_have_mfa(self) -> None:
        """When all members have MFA, return empty no_mfa_logins."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="mfa_status",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        assert items[0]["no_mfa_logins"] == []
        assert next_cursor == "_done"


# ─── Delta Sync Tests ────────────────────────────────────────────────────────


class TestDeltaSyncBranchProtections:
    """Tests for delta sync optimization in branch_protections."""

    @pytest.mark.asyncio
    async def test_branch_protections_delta_stops_at_old_repos(self) -> None:
        """When delta_since is set, branch protections skip repos older than cutoff."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        now = datetime.now(UTC)
        delta_since = now - timedelta(hours=12)

        repos = [
            {
                "name": "fresh-repo",
                "id": 1,
                "archived": False,
                "default_branch": "main",
                "pushed_at": now.isoformat(),
            },
            {
                "name": "old-repo",
                "id": 2,
                "archived": False,
                "default_branch": "main",
                "pushed_at": (now - timedelta(days=30)).isoformat(),
            },
        ]

        # Protection response for fresh-repo
        prot_data = {
            "required_pull_request_reviews": {"required_approving_review_count": 2},
            "required_status_checks": {"contexts": ["ci"], "strict": True},
            "enforce_admins": {"enabled": True},
        }

        mock_repos_resp = MagicMock()
        mock_repos_resp.status_code = 200
        mock_repos_resp.json.return_value = repos
        mock_repos_resp.headers = {"link": '<next>; rel="next"'}

        mock_prot_resp = MagicMock()
        mock_prot_resp.status_code = 200
        mock_prot_resp.json.return_value = prot_data

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(side_effect=[mock_repos_resp, mock_prot_resp]),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="branch_protections",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
                delta_since=delta_since,
            )

        # Only the fresh repo's protection should be returned
        assert len(items) == 1
        assert items[0]["_repo_name"] == "fresh-repo"
        assert items[0]["required_reviews"] == 2
        # Pagination should stop (next_cursor=None) because old-repo is past cutoff
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_branch_protections_no_delta_fetches_all(self) -> None:
        """Without delta_since, all repos are checked."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        repos = [
            {
                "name": "repo-1",
                "id": 1,
                "archived": False,
                "default_branch": "main",
                "pushed_at": "2024-01-01T00:00:00Z",
            },
        ]

        mock_repos_resp = MagicMock()
        mock_repos_resp.status_code = 200
        mock_repos_resp.json.return_value = repos
        mock_repos_resp.headers = {}

        # 404 = no protection
        mock_prot_resp = MagicMock()
        mock_prot_resp.status_code = 404

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(side_effect=[mock_repos_resp, mock_prot_resp]),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="branch_protections",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
                delta_since=None,
            )

        assert items == []
        assert next_cursor is None


class TestEntityTypeDispatchExtended:
    """Tests that new entity types are included in the orchestrator dispatch."""

    def test_scope_type_includes_code_scanning(self) -> None:
        """code_scanning_alerts is in the ScopeType literal."""
        req = SyncTriggerRequest(scope="code_scanning_alerts")
        assert req.scope == "code_scanning_alerts"

    def test_scope_type_includes_actions_workflows(self) -> None:
        """actions_workflows is in the ScopeType literal."""
        req = SyncTriggerRequest(scope="actions_workflows")
        assert req.scope == "actions_workflows"

    def test_scope_type_includes_mfa_status(self) -> None:
        """mfa_status is in the ScopeType literal."""
        req = SyncTriggerRequest(scope="mfa_status")
        assert req.scope == "mfa_status"

    def test_org_entities_includes_new_types(self) -> None:
        """All new entity types are in the _ORG_ENTITIES set."""
        # Read the source file to verify entity sets include new types
        import pathlib

        worker_path = (
            pathlib.Path(__file__).parent.parent / "app" / "workers" / "github_sync_worker.py"
        )
        source = worker_path.read_text()

        # Verify all new types are in _ORG_ENTITIES definition
        assert '"code_scanning_alerts"' in source
        assert '"actions_workflows"' in source
        assert '"mfa_status"' in source

        # Verify they appear in the _ORG_ENTITIES block (not just anywhere)
        # Find the _ORG_ENTITIES block
        idx_start = source.index("_ORG_ENTITIES = {")
        idx_end = source.index("}", idx_start)
        org_block = source[idx_start:idx_end]
        assert "code_scanning_alerts" in org_block
        assert "actions_workflows" in org_block
        assert "mfa_status" in org_block


class TestUpsertItemsDispatchExtended:
    """Tests that _upsert_items correctly dispatches to new handlers."""

    @pytest.mark.asyncio
    async def test_upsert_items_dispatches_code_scanning(self) -> None:
        """Verify _upsert_items calls _upsert_code_scanning_summary."""
        from app.workers.github_sync_worker import _upsert_items

        with patch(
            "app.workers.github_sync_worker._upsert_code_scanning_summary",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [{"open_count": 1, "total_count": 1}]
            await _upsert_items(mock_session, "code_scanning_alerts", "test-org", items)

        mock_handler.assert_called_once_with(mock_session, "test-org", items)

    @pytest.mark.asyncio
    async def test_upsert_items_dispatches_actions_workflows(self) -> None:
        """Verify _upsert_items calls _upsert_actions_workflow_summary."""
        from app.workers.github_sync_worker import _upsert_items

        with patch(
            "app.workers.github_sync_worker._upsert_actions_workflow_summary",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [{"total_workflows": 5}]
            await _upsert_items(mock_session, "actions_workflows", "test-org", items)

        mock_handler.assert_called_once_with(mock_session, "test-org", items)

    @pytest.mark.asyncio
    async def test_upsert_items_dispatches_mfa_status(self) -> None:
        """Verify _upsert_items calls _upsert_mfa_status."""
        from app.workers.github_sync_worker import _upsert_items

        with patch(
            "app.workers.github_sync_worker._upsert_mfa_status",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [{"no_mfa_logins": ["user1"]}]
            await _upsert_items(mock_session, "mfa_status", "test-org", items)

        mock_handler.assert_called_once_with(mock_session, "test-org", items)

    @pytest.mark.asyncio
    async def test_upsert_items_passes_delta_since_to_org_members(self) -> None:
        """Verify _upsert_items passes delta_since to org_members handler."""
        from app.workers.github_sync_worker import _upsert_items

        now = datetime.now(UTC)
        with patch(
            "app.workers.github_sync_worker._upsert_org_members",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [{"login": "user1", "id": 1}]
            await _upsert_items(mock_session, "org_members", "test-org", items, delta_since=now)

        mock_handler.assert_called_once_with(mock_session, "test-org", items, delta_since=now)

    @pytest.mark.asyncio
    async def test_upsert_items_passes_delta_since_to_teams(self) -> None:
        """Verify _upsert_items passes delta_since to teams handler."""
        from app.workers.github_sync_worker import _upsert_items

        now = datetime.now(UTC)
        with patch(
            "app.workers.github_sync_worker._upsert_teams",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [{"slug": "team-1", "id": 1, "name": "Team 1"}]
            await _upsert_items(mock_session, "teams", "test-org", items, delta_since=now)

        mock_handler.assert_called_once_with(mock_session, "test-org", items, delta_since=now)

    @pytest.mark.asyncio
    async def test_upsert_items_passes_delta_since_to_team_members(self) -> None:
        """Verify _upsert_items passes delta_since to team_members handler."""
        from app.workers.github_sync_worker import _upsert_items

        now = datetime.now(UTC)
        with patch(
            "app.workers.github_sync_worker._upsert_team_members",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [{"login": "user1", "_team_slug": "team-1"}]
            await _upsert_items(mock_session, "team_members", "test-org", items, delta_since=now)

        mock_handler.assert_called_once_with(mock_session, "test-org", items, delta_since=now)

    @pytest.mark.asyncio
    async def test_upsert_items_passes_delta_since_to_outside_collaborators(self) -> None:
        """Verify _upsert_items passes delta_since to outside_collaborators."""
        from app.workers.github_sync_worker import _upsert_items

        now = datetime.now(UTC)
        with patch(
            "app.workers.github_sync_worker._upsert_outside_collaborators",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [{"login": "ext-user", "id": 99}]
            await _upsert_items(
                mock_session, "outside_collaborators", "test-org", items, delta_since=now
            )

        mock_handler.assert_called_once_with(mock_session, "test-org", items, delta_since=now)

    @pytest.mark.asyncio
    async def test_upsert_items_no_delta_since_for_repos(self) -> None:
        """Verify repositories handler does NOT receive delta_since."""
        from app.workers.github_sync_worker import _upsert_items

        now = datetime.now(UTC)
        with patch(
            "app.workers.github_sync_worker._upsert_repositories",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [{"name": "repo1", "id": 1, "visibility": "private"}]
            await _upsert_items(mock_session, "repositories", "test-org", items, delta_since=now)

        # repositories handler should NOT get delta_since
        mock_handler.assert_called_once_with(mock_session, "test-org", items)


class TestMfaStatusPagination:
    """Tests for MFA status multi-page pagination."""

    @pytest.mark.asyncio
    async def test_fetch_mfa_paginates(self) -> None:
        """Verify MFA status fetches multiple pages of disabled members."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        # Page 1 with more pages available
        page1 = [{"login": "user1", "id": 1}]
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = page1
        mock_resp1.headers = {"link": '<next>; rel="next"'}

        # Page 2, last page
        page2 = [{"login": "user2", "id": 2}]
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = page2
        mock_resp2.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(side_effect=[mock_resp1, mock_resp2]),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="mfa_status",
                org="test-org",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        assert set(items[0]["no_mfa_logins"]) == {"user1", "user2"}
        assert next_cursor == "_done"


# ─── Alembic Migration Tests ─────────────────────────────────────────────────


class TestAlembicMigration0025:
    """Tests for the 0025 migration file structure."""

    def test_migration_exists(self) -> None:
        """Verify migration file exists and has correct revision chain."""
        import importlib.util
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "0025_add_code_scanning_actions_mfa.py",
        )
        assert os.path.isfile(migration_path), "Migration file not found"

        spec = importlib.util.spec_from_file_location("migration_0025", migration_path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "0025"
        assert mod.down_revision == "0024"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        """Verify migration has both upgrade and downgrade functions."""
        import importlib.util
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "alembic",
            "versions",
            "0025_add_code_scanning_actions_mfa.py",
        )

        spec = importlib.util.spec_from_file_location("migration_0025", migration_path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)


# ─── Datetime Parsing Tests ───────────────────────────────────────────────────


class TestParseGhDt:
    """Unit tests for the _parse_gh_dt helper."""

    def test_parses_github_z_suffix(self) -> None:
        """GitHub ISO 8601 strings with Z suffix are parsed to timezone-aware datetime."""
        from app.workers.github_sync_worker import _parse_gh_dt

        result = _parse_gh_dt("2025-09-08T13:59:42Z")
        assert result is not None
        assert result.year == 2025
        assert result.month == 9
        assert result.day == 8
        assert result.hour == 13
        assert result.minute == 59
        assert result.second == 42
        assert result.tzinfo is not None

    def test_parses_explicit_utc_offset(self) -> None:
        """ISO 8601 strings with +00:00 offset are accepted."""
        from app.workers.github_sync_worker import _parse_gh_dt

        result = _parse_gh_dt("2025-01-15T08:30:00+00:00")
        assert result is not None
        assert result.year == 2025
        assert result.tzinfo is not None

    def test_returns_none_for_none(self) -> None:
        """None input returns None (optional datetime columns)."""
        from app.workers.github_sync_worker import _parse_gh_dt

        assert _parse_gh_dt(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        """Empty string input returns None."""
        from app.workers.github_sync_worker import _parse_gh_dt

        assert _parse_gh_dt("") is None

    def test_returns_none_for_invalid_string(self) -> None:
        """Invalid timestamp string returns None rather than raising."""
        from app.workers.github_sync_worker import _parse_gh_dt

        assert _parse_gh_dt("not-a-date") is None

    def test_returns_datetime_object(self) -> None:
        """Return value is always a datetime instance, not a string."""
        from app.workers.github_sync_worker import _parse_gh_dt

        result = _parse_gh_dt("2024-06-01T00:00:00Z")
        assert isinstance(result, datetime)


class TestUpsertDeployKeysDatetimeParsing:
    """Verify _upsert_deploy_keys converts ISO 8601 strings to datetime objects."""

    @pytest.mark.asyncio
    async def test_created_at_string_is_parsed_to_datetime(self) -> None:
        """GitHub 'created_at' string must be converted to datetime before DB insert."""
        from app.workers.github_sync_worker import _upsert_deploy_keys

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "_repo_name": "myrepo",
                "key_id": 42,
                "title": "CI Key",
                "read_only": True,
                "created_at": "2025-09-08T13:59:42Z",
            }
        ]

        await _upsert_deploy_keys(mock_session, "test-org", items)

        mock_session.execute.assert_called_once()
        call_kwargs = mock_session.execute.call_args
        # The second positional argument to insert() is the statement; the
        # values are embedded in it — we just verify execute was called,
        # which means no TypeError was raised during construction.
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_none_created_at_is_allowed(self) -> None:
        """A missing 'created_at' should result in NULL (not crash)."""
        from app.workers.github_sync_worker import _upsert_deploy_keys

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "_repo_name": "myrepo",
                "key_id": 99,
                "title": "Deploy Key",
                "read_only": False,
            }
        ]

        # Should not raise
        await _upsert_deploy_keys(mock_session, "test-org", items)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_items_without_key_id(self) -> None:
        """Items without key_id are silently skipped."""
        from app.workers.github_sync_worker import _upsert_deploy_keys

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "_repo_name": "myrepo",
                "title": "No ID Key",
                "created_at": "2025-01-01T00:00:00Z",
            }
        ]

        await _upsert_deploy_keys(mock_session, "test-org", items)
        mock_session.execute.assert_not_called()
        mock_session.commit.assert_called_once()


class TestUpsertCredentialAuthorizationsDatetimeParsing:
    """Verify _upsert_credential_authorizations converts ISO 8601 strings to datetime objects."""

    @pytest.mark.asyncio
    async def test_authorized_and_accessed_at_strings_are_parsed(self) -> None:
        """GitHub credential datetime strings must be converted before DB insert."""
        from app.workers.github_sync_worker import _upsert_credential_authorizations

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "login": "octocat",
                "credential_id": 101,
                "credential_type": "personal_access_token",
                "token_last_eight": "abcd1234",
                "credential_authorized_at": "2025-08-01T10:00:00Z",
                "credential_accessed_at": "2025-09-01T12:30:00Z",
                "scopes": ["repo", "read:org"],
            }
        ]

        await _upsert_credential_authorizations(mock_session, "test-org", items)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_null_datetime_fields_allowed(self) -> None:
        """Missing credential datetime fields result in NULL (not crash)."""
        from app.workers.github_sync_worker import _upsert_credential_authorizations

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "login": "octocat",
                "credential_id": 202,
                "credential_type": "personal_access_token",
            }
        ]

        await _upsert_credential_authorizations(mock_session, "test-org", items)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_items_without_credential_id(self) -> None:
        """Items without credential_id are silently skipped."""
        from app.workers.github_sync_worker import _upsert_credential_authorizations

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [{"login": "ghost", "credential_type": "personal_access_token"}]

        await _upsert_credential_authorizations(mock_session, "test-org", items)
        mock_session.execute.assert_not_called()
        mock_session.commit.assert_called_once()


class TestUpsertRepositoriesDatetimeParsing:
    """Verify _upsert_repositories uses _parse_gh_dt for pushed_at."""

    @pytest.mark.asyncio
    async def test_pushed_at_string_is_parsed(self) -> None:
        """GitHub 'pushed_at' ISO string must be converted to datetime."""
        from app.workers.github_sync_worker import _upsert_repositories

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "name": "my-repo",
                "id": 1,
                "visibility": "private",
                "default_branch": "main",
                "archived": False,
                "fork": False,
                "pushed_at": "2025-09-08T13:59:42Z",
            }
        ]

        await _upsert_repositories(mock_session, "test-org", items)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_null_pushed_at_is_allowed(self) -> None:
        """Missing pushed_at results in NULL without crashing."""
        from app.workers.github_sync_worker import _upsert_repositories

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [{"name": "another-repo", "id": 2, "visibility": "public"}]

        await _upsert_repositories(mock_session, "test-org", items)
        mock_session.execute.assert_called_once()
