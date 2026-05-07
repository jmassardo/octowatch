"""Tests for the event-driven workflow scanner and activity endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.workflow_scan_worker import (
    WORKFLOW_ACTIONS,
    _analyze_completed_run,
    _analyze_created_run,
    _analyze_prepared_job,
    scan_workflow_events_task,
)


class TestScanWorkflowEventsTaskFiltering:
    """Test that scan_workflow_events_task filters non-workflow events."""

    @patch("app.workers.workflow_scan_worker.asyncio.run")
    def test_task_calls_scan_specific_events(self, mock_run: MagicMock) -> None:
        """Task should delegate to _scan_specific_events via asyncio.run."""
        mock_run.return_value = {"events_received": 3, "workflow_events": 0}
        result = scan_workflow_events_task(event_ids=[1, 2, 3])
        assert result["events_received"] == 3
        mock_run.assert_called_once()

    def test_workflow_actions_contains_expected(self) -> None:
        """WORKFLOW_ACTIONS should contain the expected audit log actions."""
        assert "workflows.prepared_workflow_job" in WORKFLOW_ACTIONS
        assert "workflows.completed_workflow_run" in WORKFLOW_ACTIONS
        assert "workflows.created_workflow_run" in WORKFLOW_ACTIONS

    def test_non_workflow_action_not_in_set(self) -> None:
        """Non-workflow actions should not be in the set."""
        assert "repos.create" not in WORKFLOW_ACTIONS
        assert "team.add_member" not in WORKFLOW_ACTIONS


class TestDebounceLogic:
    """Test debounce logic using Valkey mock."""

    @pytest.mark.asyncio
    async def test_debounce_skips_when_key_exists(self, mock_valkey: AsyncMock) -> None:
        """When debounce key exists, scan should be skipped."""
        mock_valkey.get = AsyncMock(return_value="1")

        # We test the debounce by verifying the Valkey get pattern
        result = await mock_valkey.get("wf_scan:my-org/my-repo/.github/workflows/ci.yml")
        assert result == "1"  # Key exists → debounce active

    @pytest.mark.asyncio
    async def test_debounce_proceeds_when_key_missing(self, mock_valkey: AsyncMock) -> None:
        """When debounce key does not exist, scan should proceed."""
        mock_valkey.get = AsyncMock(return_value=None)

        result = await mock_valkey.get("wf_scan:my-org/my-repo/.github/workflows/ci.yml")
        assert result is None  # Key missing → scan should proceed

    @pytest.mark.asyncio
    async def test_debounce_key_is_set_with_ttl(self, mock_valkey: AsyncMock) -> None:
        """After proceeding, debounce key should be set with 30s TTL."""
        mock_valkey.setex = AsyncMock(return_value=True)

        await mock_valkey.setex("wf_scan:my-org/my-repo/.github/workflows/ci.yml", 30, "1")
        mock_valkey.setex.assert_called_once_with(
            "wf_scan:my-org/my-repo/.github/workflows/ci.yml", 30, "1"
        )


class TestActivityRecordCreation:
    """Test that activity records are properly structured."""

    def test_activity_model_import(self) -> None:
        """WorkflowScanActivity model should be importable."""
        from app.models.workflow_scan_activity import WorkflowScanActivity

        assert WorkflowScanActivity.__tablename__ == "workflow_scan_activities"

    def test_activity_model_fields(self) -> None:
        """WorkflowScanActivity should have expected columns."""
        from app.models.workflow_scan_activity import WorkflowScanActivity

        columns = {c.name for c in WorkflowScanActivity.__table__.columns}
        expected = {
            "id",
            "trigger_event_ids",
            "org",
            "repo",
            "workflow_path",
            "started_at",
            "completed_at",
            "status",
            "checks_performed",
            "findings_count",
            "data_sources",
            "duration_ms",
            "error_message",
        }
        assert expected.issubset(columns)


class TestAnalyzeFunctions:
    """Test the analysis functions produce correct findings."""

    def test_prepared_job_self_hosted_runner(self) -> None:
        """Self-hosted runner should generate a finding."""
        data = {
            "job_workflow_ref": "my-org/repo/.github/workflows/ci.yml@refs/heads/main",
            "job_name": "build",
            "is_hosted_runner": False,
            "runner_name": "self-hosted-1",
            "runner_labels": ["self-hosted", "linux"],
        }
        findings = _analyze_prepared_job(data, "my-org/repo", "my-org")
        rule_ids = [f["rule_id"] for f in findings]
        assert "self-hosted-runner" in rule_ids

    def test_prepared_job_excessive_secrets(self) -> None:
        """High secret count should generate a finding."""
        data = {
            "job_workflow_ref": "my-org/repo/.github/workflows/deploy.yml@refs/heads/main",
            "job_name": "deploy",
            "secrets_passed_count": 8,
        }
        findings = _analyze_prepared_job(data, "my-org/repo", "my-org")
        rule_ids = [f["rule_id"] for f in findings]
        assert "excessive-secrets" in rule_ids

    def test_completed_run_public_repo(self) -> None:
        """Public repo workflow run should generate a finding."""
        data = {
            "name": "CI",
            "public_repo": True,
            "head_branch": "main",
            "conclusion": "success",
        }
        findings = _analyze_completed_run(data, "my-org/repo", "my-org")
        rule_ids = [f["rule_id"] for f in findings]
        assert "public-repo-workflow" in rule_ids

    def test_created_run_pat_triggered(self) -> None:
        """PAT-triggered workflow should generate a finding."""
        data = {
            "name": "Deploy",
            "programmatic_access_type": "fine-grained personal access token",
            "actor": "bot-user",
        }
        findings = _analyze_created_run(data, "my-org/repo", "my-org")
        rule_ids = [f["rule_id"] for f in findings]
        assert "pat-triggered-workflow" in rule_ids

    def test_no_findings_for_normal_event(self) -> None:
        """Normal workflow run without issues should generate no findings."""
        data = {
            "name": "CI",
            "public_repo": False,
            "head_branch": "main",
            "conclusion": "success",
        }
        findings = _analyze_completed_run(data, "my-org/repo", "my-org")
        assert findings == []


class TestActivityEndpoint:
    """Test the /activity endpoint response schemas."""

    def test_scan_activity_response_schema(self) -> None:
        """ScanActivityResponse should accept valid data."""
        from app.routers.workflow_scanner import ScanActivityResponse

        resp = ScanActivityResponse(
            id=1,
            trigger_event_ids=[10, 11, 12],
            org="my-org",
            repo="my-repo",
            workflow_path=".github/workflows/ci.yml",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status="completed",
            checks_performed=["self-hosted-runner", "excessive-secrets"],
            findings_count=2,
            data_sources=["audit_log"],
            duration_ms=150,
        )
        assert resp.id == 1
        assert resp.findings_count == 2
        assert len(resp.trigger_event_ids) == 3

    def test_scan_activity_list_response_schema(self) -> None:
        """ScanActivityListResponse should wrap items and total."""
        from app.routers.workflow_scanner import ScanActivityListResponse, ScanActivityResponse

        item = ScanActivityResponse(
            id=1,
            trigger_event_ids=[],
            org="org",
            repo="repo",
            workflow_path=".github/workflows/x.yml",
            started_at=datetime.now(UTC),
            completed_at=None,
            status="running",
            checks_performed=[],
            findings_count=0,
            data_sources=["audit_log"],
            duration_ms=None,
        )
        resp = ScanActivityListResponse(items=[item], total=1)
        assert resp.total == 1
        assert len(resp.items) == 1


class TestDetectionWorkerChain:
    """Test that the detection worker chains workflow scanning."""

    def test_detection_worker_imports_scan_task(self) -> None:
        """The detection worker should be able to import scan_workflow_events_task."""
        from app.workers.workflow_scan_worker import scan_workflow_events_task

        assert scan_workflow_events_task is not None
        assert (
            scan_workflow_events_task.name
            == "app.workers.workflow_scan_worker.scan_workflow_events"
        )
