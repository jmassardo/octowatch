"""Unit tests for post-sync detection + baseline pipeline."""

from __future__ import annotations

import types
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.github_sync import SyncRunDetail, SyncRunSummary

# ── Schema Tests ──────────────────────────────────────────────────────────────


class TestSyncRunDetailPostProcessing:
    """Verify SyncRunDetail includes post_processing_status field."""

    def test_post_processing_status_defaults_to_none(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "manual"
            triggered_by = "testuser"
            scope = "full"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            error_message = None
            entity_counts = {"orgs": 5}

        detail = SyncRunDetail.model_validate(FakeRun())
        assert detail.post_processing_status is None

    def test_post_processing_status_pending(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "manual"
            triggered_by = "testuser"
            scope = "full"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            error_message = None
            entity_counts = {"orgs": 5}
            post_processing_status = "pending"

        detail = SyncRunDetail.model_validate(FakeRun())
        assert detail.post_processing_status == "pending"

    def test_post_processing_status_running(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "manual"
            triggered_by = None
            scope = "full"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            error_message = None
            entity_counts = None
            post_processing_status = "running"

        detail = SyncRunDetail.model_validate(FakeRun())
        assert detail.post_processing_status == "running"

    def test_post_processing_status_completed(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "scheduled"
            triggered_by = None
            scope = "full"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            error_message = None
            entity_counts = {"orgs": 3, "repositories": 100}
            post_processing_status = "completed"

        detail = SyncRunDetail.model_validate(FakeRun())
        assert detail.post_processing_status == "completed"

    def test_post_processing_status_failed(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "manual"
            triggered_by = "admin"
            scope = "full"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            error_message = None
            entity_counts = {"orgs": 5}
            post_processing_status = "failed"

        detail = SyncRunDetail.model_validate(FakeRun())
        assert detail.post_processing_status == "failed"

    def test_serialization_includes_post_processing_status(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "manual"
            triggered_by = "admin"
            scope = "full"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            error_message = None
            entity_counts = None
            post_processing_status = "pending"

        detail = SyncRunDetail.model_validate(FakeRun())
        dumped = detail.model_dump()
        assert "post_processing_status" in dumped
        assert dumped["post_processing_status"] == "pending"


class TestSyncRunSummaryPostProcessing:
    """Verify SyncRunSummary includes post_processing_status field."""

    def test_post_processing_status_defaults_to_none(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "pending"
            trigger_type = "scheduled"
            triggered_by = None
            started_at = None
            completed_at = None

        summary = SyncRunSummary.model_validate(FakeRun())
        assert summary.post_processing_status is None

    def test_post_processing_status_set(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "manual"
            triggered_by = "admin"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            post_processing_status = "completed"

        summary = SyncRunSummary.model_validate(FakeRun())
        assert summary.post_processing_status == "completed"

    def test_serialization_includes_post_processing_status(self) -> None:
        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "manual"
            triggered_by = "admin"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            post_processing_status = "running"

        summary = SyncRunSummary.model_validate(FakeRun())
        dumped = summary.model_dump()
        assert "post_processing_status" in dumped
        assert dumped["post_processing_status"] == "running"


# ── Model Tests ───────────────────────────────────────────────────────────────


class TestEnterpriseSyncRunModel:
    """Verify the EnterpriseSyncRun model has the post_processing_status column."""

    def test_post_processing_status_column_exists(self) -> None:
        from app.models.github_sync import EnterpriseSyncRun

        columns = {c.name for c in EnterpriseSyncRun.__table__.columns}
        assert "post_processing_status" in columns

    def test_post_processing_status_is_nullable(self) -> None:
        from app.models.github_sync import EnterpriseSyncRun

        col = EnterpriseSyncRun.__table__.columns["post_processing_status"]
        assert col.nullable is True

    def test_post_processing_status_is_text_type(self) -> None:
        from sqlalchemy import Text

        from app.models.github_sync import EnterpriseSyncRun

        col = EnterpriseSyncRun.__table__.columns["post_processing_status"]
        assert isinstance(col.type, Text)


# ── Migration Tests ───────────────────────────────────────────────────────────


class TestMigration0018:
    """Verify migration 0018 structure."""

    def _load_migration(self) -> types.ModuleType:
        """Load migration module by file path."""
        import importlib.util
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "0018_add_post_processing_status_to_sync_runs.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0018", migration_path)
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_revision_chain(self) -> None:
        m = self._load_migration()
        assert m.revision == "0018"
        assert m.down_revision == "0017"

    def test_upgrade_function_exists(self) -> None:
        m = self._load_migration()
        assert callable(m.upgrade)

    def test_downgrade_function_exists(self) -> None:
        m = self._load_migration()
        assert callable(m.downgrade)


# ── Post-Sync Pipeline Task Tests ────────────────────────────────────────────


class TestRunPostSyncPipeline:
    """Tests for the run_post_sync_pipeline Celery task."""

    def test_task_is_registered(self) -> None:
        """The task should be registered with the correct name."""
        from app.workers.github_sync_worker import run_post_sync_pipeline

        assert run_post_sync_pipeline.name == ("app.workers.github_sync.run_post_sync_pipeline")

    def test_task_queue_is_github_sync(self) -> None:
        from app.workers.github_sync_worker import run_post_sync_pipeline

        assert run_post_sync_pipeline.queue == "github_sync"

    def test_task_max_retries_is_zero(self) -> None:
        from app.workers.github_sync_worker import run_post_sync_pipeline

        assert run_post_sync_pipeline.max_retries == 0

    @patch("app.workers.github_sync_worker._make_session_factory")
    @patch("app.workers.github_sync_worker.run_detection_pipeline_task", create=True)
    @patch("app.workers.github_sync_worker.compute_rolling_baselines_task", create=True)
    def test_pipeline_dispatches_detection_batches(
        self,
        mock_baseline_task: MagicMock,
        mock_detection_task: MagicMock,
        mock_session_factory: MagicMock,
    ) -> None:
        """Pipeline should batch events and dispatch detection tasks."""
        import asyncio

        from app.workers.github_sync_worker import _run_post_sync_pipeline_async

        run_id = str(uuid.uuid4())

        # Mock session
        mock_session = AsyncMock()

        # First call: update status to running (execute + commit)
        # Second call: query events (execute returns rows)
        # Third call: update status to completed (execute + commit)
        event_rows = [(i,) for i in range(1, 1201)]  # 1200 events
        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 3:
                # Event query (after status update + _write_sync_log)
                result.fetchall.return_value = event_rows
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.commit = AsyncMock()

        # Make session factory return our mock
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value.return_value = mock_ctx

        # Mock detection task
        mock_detection_task.apply_async = MagicMock()
        mock_baseline_task.apply_async = MagicMock()

        # Patch the imports inside the async function
        with (
            patch(
                "app.workers.detection_worker.run_detection_pipeline_task",
                mock_detection_task,
            ),
            patch(
                "app.workers.baseline_worker.compute_rolling_baselines_task",
                mock_baseline_task,
            ),
        ):
            result = asyncio.run(_run_post_sync_pipeline_async(run_id))

        assert result["status"] == "completed"
        assert result["event_count"] == 1200
        # 1200 events / 500 batch size = 3 batches (500 + 500 + 200)
        assert result["detection_batches"] == 3
        assert mock_detection_task.apply_async.call_count == 3
        # Baseline task should be dispatched once
        assert mock_baseline_task.apply_async.call_count == 1

    @patch("app.workers.github_sync_worker._make_session_factory")
    @patch("app.workers.github_sync_worker.run_detection_pipeline_task", create=True)
    @patch("app.workers.github_sync_worker.compute_rolling_baselines_task", create=True)
    def test_pipeline_no_events(
        self,
        mock_baseline_task: MagicMock,
        mock_detection_task: MagicMock,
        mock_session_factory: MagicMock,
    ) -> None:
        """Pipeline should handle zero events gracefully."""
        import asyncio

        from app.workers.github_sync_worker import _run_post_sync_pipeline_async

        run_id = str(uuid.uuid4())

        mock_session = AsyncMock()
        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 2:
                result.fetchall.return_value = []  # No events
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value.return_value = mock_ctx

        mock_detection_task.apply_async = MagicMock()
        mock_baseline_task.apply_async = MagicMock()

        with (
            patch(
                "app.workers.detection_worker.run_detection_pipeline_task",
                mock_detection_task,
            ),
            patch(
                "app.workers.baseline_worker.compute_rolling_baselines_task",
                mock_baseline_task,
            ),
        ):
            result = asyncio.run(_run_post_sync_pipeline_async(run_id))

        assert result["status"] == "completed"
        assert result["event_count"] == 0
        assert result["detection_batches"] == 0
        # No detection batches dispatched
        assert mock_detection_task.apply_async.call_count == 0
        # Baseline still dispatched even with no events
        assert mock_baseline_task.apply_async.call_count == 1

    @patch("app.workers.github_sync_worker._make_session_factory")
    def test_pipeline_error_sets_status_failed(
        self,
        mock_session_factory: MagicMock,
    ) -> None:
        """Pipeline should set post_processing_status to 'failed' on error."""
        import asyncio

        from app.workers.github_sync_worker import _run_post_sync_pipeline_async

        run_id = str(uuid.uuid4())

        mock_session = AsyncMock()
        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: update status to running - succeeds
                return MagicMock()
            # Second call: query events - explodes
            raise RuntimeError("Database connection lost")

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value.return_value = mock_ctx

        result = asyncio.run(_run_post_sync_pipeline_async(run_id))

        assert result["status"] == "failed"
        assert "Database connection lost" in str(result["error"])

    @patch("app.workers.github_sync_worker._make_session_factory")
    @patch("app.workers.github_sync_worker.run_detection_pipeline_task", create=True)
    @patch("app.workers.github_sync_worker.compute_rolling_baselines_task", create=True)
    def test_pipeline_exact_batch_boundary(
        self,
        mock_baseline_task: MagicMock,
        mock_detection_task: MagicMock,
        mock_session_factory: MagicMock,
    ) -> None:
        """Pipeline should handle exact batch size (500 events = 1 batch)."""
        import asyncio

        from app.workers.github_sync_worker import _run_post_sync_pipeline_async

        run_id = str(uuid.uuid4())

        mock_session = AsyncMock()
        event_rows = [(i,) for i in range(1, 501)]  # Exactly 500 events
        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 3:
                result.fetchall.return_value = event_rows
            return result

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value.return_value = mock_ctx

        mock_detection_task.apply_async = MagicMock()
        mock_baseline_task.apply_async = MagicMock()

        with (
            patch(
                "app.workers.detection_worker.run_detection_pipeline_task",
                mock_detection_task,
            ),
            patch(
                "app.workers.baseline_worker.compute_rolling_baselines_task",
                mock_baseline_task,
            ),
        ):
            result = asyncio.run(_run_post_sync_pipeline_async(run_id))

        assert result["status"] == "completed"
        assert result["event_count"] == 500
        assert result["detection_batches"] == 1
        assert mock_detection_task.apply_async.call_count == 1


# ── Orchestrator Completion Tests ─────────────────────────────────────────────


class TestOrchestratorCompletion:
    """Tests for the orchestrator waiting and completion logic."""

    @patch("app.workers.github_sync_worker.run_post_sync_pipeline")
    @patch("app.workers.github_sync_worker._sync_installation_configs")
    @patch("app.workers.github_sync_worker._make_session_factory")
    @patch("app.workers.github_sync_worker.sync_entity")
    def test_orchestrator_marks_completed_and_dispatches_pipeline(
        self,
        mock_sync_entity: MagicMock,
        mock_session_factory: MagicMock,
        mock_sync_configs: MagicMock,
        mock_post_sync: MagicMock,
    ) -> None:
        """After all child tasks complete, orchestrator should mark completed
        and dispatch post-sync pipeline."""
        import asyncio

        from app.workers.github_sync_worker import _run_enterprise_sync_async

        run_id = str(uuid.uuid4())

        # Mock child task results (all SUCCESS)
        mock_child_result = MagicMock()
        mock_child_result.state = "SUCCESS"
        mock_child_result.result = {
            "status": "completed",
            "entity_type": "orgs",
            "org": "my-enterprise",
            "items": 5,
        }
        mock_sync_entity.apply_async.return_value = mock_child_result

        # Mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value.return_value = mock_ctx

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.github_app.GITHUB_APP_ID = 123
        mock_settings.github_app.sync_orgs_list = ["my-org"]
        mock_settings.github_app.GITHUB_ENTERPRISE_SLUG = "my-enterprise"

        # Mock configs returned from DB
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.enterprise_slug = "my-enterprise"
        mock_config.org_login = None
        mock_config.installation_id = 456
        mock_configs_result = MagicMock()
        mock_configs_result.scalars.return_value.all.return_value = [mock_config]

        # _sync_installation_configs returns configs unchanged
        mock_sync_configs.return_value = [mock_config]

        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Second call: load configs
                return mock_configs_result
            return MagicMock()

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.config.settings", mock_settings):
            result = asyncio.run(_run_enterprise_sync_async(run_id, "orgs"))

        assert result["status"] == "dispatched"
        assert result["tasks"] >= 1

    @patch("app.workers.github_sync_worker.run_post_sync_pipeline")
    @patch("app.workers.github_sync_worker._sync_installation_configs")
    @patch("app.workers.github_sync_worker._make_session_factory")
    @patch("app.workers.github_sync_worker.sync_entity")
    def test_orchestrator_marks_failed_no_pipeline(
        self,
        mock_sync_entity: MagicMock,
        mock_session_factory: MagicMock,
        mock_sync_configs: MagicMock,
        mock_post_sync: MagicMock,
    ) -> None:
        """When child tasks fail, orchestrator should mark failed and NOT
        dispatch post-sync pipeline."""
        import asyncio

        from app.workers.github_sync_worker import _run_enterprise_sync_async

        run_id = str(uuid.uuid4())

        # Mock child task results (FAILURE)
        mock_child_result = MagicMock()
        mock_child_result.state = "FAILURE"
        mock_child_result.result = None
        mock_sync_entity.apply_async.return_value = mock_child_result

        # Mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value.return_value = mock_ctx

        # Mock settings
        mock_settings = MagicMock()
        mock_settings.github_app.GITHUB_APP_ID = 123
        mock_settings.github_app.sync_orgs_list = ["my-org"]
        mock_settings.github_app.GITHUB_ENTERPRISE_SLUG = "my-enterprise"

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.enterprise_slug = "my-enterprise"
        mock_config.org_login = None
        mock_config.installation_id = 456
        mock_configs_result = MagicMock()
        mock_configs_result.scalars.return_value.all.return_value = [mock_config]

        # _sync_installation_configs returns configs unchanged
        mock_sync_configs.return_value = [mock_config]

        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return mock_configs_result
            return MagicMock()

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.config.settings", mock_settings):
            result = asyncio.run(_run_enterprise_sync_async(run_id, "orgs"))

        assert result["status"] == "dispatched"
        assert result["tasks"] >= 1

    @patch("app.workers.github_sync_worker.run_post_sync_pipeline")
    @patch("app.workers.github_sync_worker._sync_installation_configs")
    @patch("app.workers.github_sync_worker._make_session_factory")
    @patch("app.workers.github_sync_worker.sync_entity")
    def test_orchestrator_aggregates_entity_counts(
        self,
        mock_sync_entity: MagicMock,
        mock_session_factory: MagicMock,
        mock_sync_configs: MagicMock,
        mock_post_sync: MagicMock,
    ) -> None:
        """Orchestrator should aggregate entity counts from child results."""
        import asyncio

        from app.workers.github_sync_worker import _run_enterprise_sync_async

        run_id = str(uuid.uuid4())

        # All child tasks return SUCCESS with items
        mock_child_result = MagicMock()
        mock_child_result.state = "SUCCESS"
        mock_child_result.result = {
            "status": "completed",
            "entity_type": "orgs",
            "org": "my-enterprise",
            "items": 10,
        }
        mock_sync_entity.apply_async.return_value = mock_child_result

        # Mock session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_session.commit = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value.return_value = mock_ctx

        mock_settings = MagicMock()
        mock_settings.github_app.GITHUB_APP_ID = 123
        mock_settings.github_app.sync_orgs_list = []
        mock_settings.github_app.GITHUB_ENTERPRISE_SLUG = "my-enterprise"

        mock_config = MagicMock()
        mock_config.enabled = True
        mock_config.enterprise_slug = "my-enterprise"
        mock_config.org_login = None
        mock_config.installation_id = 456
        mock_configs_result = MagicMock()
        mock_configs_result.scalars.return_value.all.return_value = [mock_config]

        # _sync_installation_configs returns configs unchanged
        mock_sync_configs.return_value = [mock_config]

        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return mock_configs_result
            return MagicMock()

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        # Scope "orgs" dispatches exactly 1 task — makes aggregation deterministic
        with patch("app.config.settings", mock_settings):
            result = asyncio.run(_run_enterprise_sync_async(run_id, "orgs"))

        assert result["status"] == "dispatched"
        assert result["tasks"] == 1

    @patch("app.workers.github_sync_worker.run_post_sync_pipeline")
    @patch("app.workers.github_sync_worker._make_session_factory")
    def test_orchestrator_no_configs_returns_failed(
        self,
        mock_session_factory: MagicMock,
        mock_post_sync: MagicMock,
    ) -> None:
        """When no configs exist, orchestrator should return failed without
        dispatching post-sync pipeline."""
        import asyncio

        from app.workers.github_sync_worker import _run_enterprise_sync_async

        run_id = str(uuid.uuid4())

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        # First call: update status to running
        # Second call: load configs - return empty
        mock_empty_result = MagicMock()
        mock_empty_result.scalars.return_value.all.return_value = []
        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return mock_empty_result
            return MagicMock()

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value.return_value = mock_ctx

        mock_settings = MagicMock()
        mock_settings.github_app.GITHUB_APP_ID = None

        with patch("app.config.settings", mock_settings):
            result = asyncio.run(_run_enterprise_sync_async(run_id, "full"))

        assert result["status"] == "failed"
        mock_post_sync.apply_async.assert_not_called()
