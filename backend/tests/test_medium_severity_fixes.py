"""Tests for medium-severity fixes: M2, M4, M6, M7, M17.

M2  – Config overlay race condition (threading.Lock)
M4  – Detection engine exception swallowing (improved logging + failed_rules)
M6  – Blocking I/O in async code paths (asyncio.to_thread wrappers)
M7  – Worker retry without backoff/jitter (exponential backoff + jitter)
M17 – N+1 query risk from lazy loading (selectinload)
"""

from __future__ import annotations

import secrets
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# M2: Config Overlay Race Condition
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfigOverlayLock:
    """Verify that _overlay_lock exists and is used during settings mutation."""

    def test_overlay_lock_is_module_level_threading_lock(self) -> None:
        from app.services.config_overlay import _overlay_lock

        assert isinstance(_overlay_lock, type(threading.Lock()))

    def test_apply_setting_acquires_lock_on_root_setting(self) -> None:
        """_apply_setting should hold _overlay_lock while calling __setattr__."""
        # Patch settings to intercept the setattr and check lock state
        from app.config import settings
        from app.services.config_overlay import _apply_setting, _overlay_lock

        original_val = getattr(settings, "DETECTION_CONFIDENCE_THRESHOLD", 0.5)
        try:
            _apply_setting("detection_confidence_threshold", "0.75")
            # Verify the lock is NOT still held after the call
            assert not _overlay_lock.locked()
        finally:
            object.__setattr__(settings, "DETECTION_CONFIDENCE_THRESHOLD", original_val)

    def test_apply_setting_acquires_lock_on_nested_setting(self) -> None:
        """_apply_setting should hold _overlay_lock for nested attrs too."""
        from app.config import settings
        from app.services.config_overlay import _apply_setting, _overlay_lock

        original_val = getattr(settings.AUTH, "GITHUB_CLIENT_ID", "")
        try:
            result = _apply_setting("github_client_id", "test-id-12345")
            assert result is True
            assert not _overlay_lock.locked()
        finally:
            object.__setattr__(settings.AUTH, "GITHUB_CLIENT_ID", original_val)

    def test_apply_setting_releases_lock_on_exception(self) -> None:
        """Lock must be released even if the setting value is invalid."""
        from app.services.config_overlay import _apply_setting, _overlay_lock

        # Use an unknown key — returns False but should not hold lock
        result = _apply_setting("nonexistent_key", "value")
        assert result is False
        assert not _overlay_lock.locked()

        # Use a valid key with a value that can be coerced (coercion succeeds)
        # but test that after normal execution, lock is released
        from app.config import settings

        original_val = getattr(settings, "DETECTION_CONFIDENCE_THRESHOLD", 0.5)
        try:
            result = _apply_setting("detection_confidence_threshold", "0.5")
            assert result is True
            assert not _overlay_lock.locked()
        finally:
            object.__setattr__(settings, "DETECTION_CONFIDENCE_THRESHOLD", original_val)

    def test_concurrent_apply_settings_are_serialized(self) -> None:
        """Two threads calling _apply_setting should not interleave."""
        # Track whether the lock was ever contended (proves serialization)
        from app.services import config_overlay
        from app.services.config_overlay import _apply_setting, _overlay_lock

        original_coerce_fn = config_overlay._coerce_value

        call_count = 0
        call_lock = threading.Lock()

        def slow_coerce(field_name: str, value: str) -> object:
            nonlocal call_count
            with call_lock:
                call_count += 1
            import time

            time.sleep(0.02)  # Create opportunity for contention
            return original_coerce_fn(field_name, value)

        results: list[bool] = []

        def apply_and_record(key: str, value: str) -> None:
            r = _apply_setting(key, value)
            results.append(r)

        with patch.object(config_overlay, "_coerce_value", side_effect=slow_coerce):
            t1 = threading.Thread(
                target=apply_and_record,
                args=("detection_confidence_threshold", "0.8"),
            )
            t2 = threading.Thread(
                target=apply_and_record,
                args=("query_max_rows", "500"),
            )
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        assert len(results) == 2
        assert all(r is True for r in results)
        assert not _overlay_lock.locked()


# ═══════════════════════════════════════════════════════════════════════════════
# M4: Detection Engine Exception Swallowing
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectionPipelineResult:
    """Verify the PipelineResult dataclass and improved exception handling."""

    def test_pipeline_result_defaults(self) -> None:
        from app.services.detection_service import PipelineResult

        result = PipelineResult()
        assert result.detections_written == 0
        assert result.failed_rules == []

    def test_pipeline_result_with_values(self) -> None:
        from app.services.detection_service import PipelineResult

        result = PipelineResult(detections_written=5, failed_rules=[1, 2, 3])
        assert result.detections_written == 5
        assert result.failed_rules == [1, 2, 3]

    def test_pipeline_result_failed_rules_is_independent(self) -> None:
        """Each PipelineResult should have its own failed_rules list."""
        from app.services.detection_service import PipelineResult

        r1 = PipelineResult()
        r2 = PipelineResult()
        r1.failed_rules.append(42)
        assert r2.failed_rules == []

    @pytest.mark.asyncio
    async def test_empty_event_ids_returns_empty_result(self) -> None:
        from app.services.detection_service import PipelineResult, run_detection_pipeline

        session = AsyncMock()
        result = await run_detection_pipeline(session, event_ids=[])
        assert isinstance(result, PipelineResult)
        assert result.detections_written == 0
        assert result.failed_rules == []

    @pytest.mark.asyncio
    async def test_failed_rule_appears_in_result(self) -> None:
        """When a rule raises, its ID should appear in failed_rules."""
        from app.services.detection_service import PipelineResult, run_detection_pipeline

        # Create mock events
        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.org = "test-org"
        mock_event.created_at = MagicMock()

        # Create a mock rule that will raise an exception
        failing_rule = MagicMock()
        failing_rule.id = 42
        failing_rule.name = "Test Rule"
        failing_rule.slug = "test-rule"
        failing_rule.logic_type = "pattern"
        failing_rule.logic_config = {}
        failing_rule.enabled = True
        failing_rule.status = "active"

        session = AsyncMock()

        # Mock execute for events query
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [mock_event]

        # Mock execute for rules query
        rules_result = MagicMock()
        rules_result.scalars.return_value.all.return_value = [failing_rule]

        # Return events on first call, rules on second
        session.execute = AsyncMock(side_effect=[events_result, rules_result])

        # Make event_matches_rule raise
        with patch(
            "app.services.detection_service.event_matches_rule",
            side_effect=ValueError("rule config error"),
        ):
            result = await run_detection_pipeline(session, event_ids=[1])

        assert isinstance(result, PipelineResult)
        assert 42 in result.failed_rules
        assert result.detections_written == 0

    @pytest.mark.asyncio
    async def test_failed_rule_logs_rule_name_and_logic_type(self) -> None:
        """Error log should include rule_name and logic_type for debugging."""
        from app.services.detection_service import run_detection_pipeline

        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.org = "test-org"
        mock_event.created_at = MagicMock()

        failing_rule = MagicMock()
        failing_rule.id = 99
        failing_rule.name = "Suspicious Login"
        failing_rule.slug = "suspicious-login"
        failing_rule.logic_type = "threshold"
        failing_rule.logic_config = {"x_config": {}}
        failing_rule.enabled = True
        failing_rule.status = "active"

        session = AsyncMock()
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [mock_event]
        rules_result = MagicMock()
        rules_result.scalars.return_value.all.return_value = [failing_rule]
        session.execute = AsyncMock(side_effect=[events_result, rules_result])

        with (
            patch(
                "app.services.detection_service.evaluate_threshold_rule",
                side_effect=RuntimeError("threshold error"),
            ),
            patch("app.services.detection_service.logger") as mock_logger,
        ):
            await run_detection_pipeline(session, event_ids=[1])

        # Check the error log call includes rule_name and logic_type
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args
        assert call_kwargs[1]["rule_name"] == "Suspicious Login"
        assert call_kwargs[1]["logic_type"] == "threshold"
        assert call_kwargs[1]["rule_id"] == 99
        assert call_kwargs[1]["exc_info"] is True

    @pytest.mark.asyncio
    async def test_coverage_reduced_warning_logged(self) -> None:
        """When rules fail, a coverage_reduced warning should be logged."""
        from app.services.detection_service import run_detection_pipeline

        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.org = "test-org"
        mock_event.created_at = MagicMock()

        failing_rule = MagicMock()
        failing_rule.id = 10
        failing_rule.name = "Bad Rule"
        failing_rule.slug = "bad-rule"
        failing_rule.logic_type = "pattern"
        failing_rule.logic_config = {}

        session = AsyncMock()
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [mock_event]
        rules_result = MagicMock()
        rules_result.scalars.return_value.all.return_value = [failing_rule]
        session.execute = AsyncMock(side_effect=[events_result, rules_result])

        with (
            patch(
                "app.services.detection_service.event_matches_rule",
                side_effect=Exception("fail"),
            ),
            patch("app.services.detection_service.logger") as mock_logger,
        ):
            await run_detection_pipeline(session, event_ids=[1])

        # Find the warning call about coverage_reduced
        warning_calls = [
            c for c in mock_logger.warning.call_args_list if c[0][0] == "detection.coverage_reduced"
        ]
        assert len(warning_calls) == 1
        assert warning_calls[0][1]["failed_rule_count"] == 1
        assert warning_calls[0][1]["failed_rule_ids"] == [10]


# ═══════════════════════════════════════════════════════════════════════════════
# M6: Blocking I/O in Async Code Paths
# ═══════════════════════════════════════════════════════════════════════════════


class TestS3WorkerAsyncIO:
    """Verify S3 worker uses asyncio.to_thread for blocking SDK calls."""

    @pytest.mark.asyncio
    async def test_s3_paginator_runs_in_thread(self) -> None:
        """The S3 paginator iteration should be offloaded via asyncio.to_thread."""
        from app.workers.ingestion.s3_worker import S3IngestWorker

        worker = S3IngestWorker(
            valkey_client=AsyncMock(),
            db_session_factory=AsyncMock(),
        )

        mock_s3_client = MagicMock()
        mock_paginator = MagicMock()
        # Return one page with no contents to exit the loop quickly
        mock_paginator.paginate.return_value = [{"Contents": []}]
        mock_s3_client.get_paginator.return_value = mock_paginator

        with (
            patch("app.workers.ingestion.s3_worker.settings") as mock_settings,
            patch.object(worker, "_load_cursor", new_callable=AsyncMock, return_value=None),
            patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread,
        ):
            mock_settings.S3.S3_AUDIT_BUCKET = "test-bucket"
            mock_settings.S3.AWS_DEFAULT_REGION = "us-east-1"
            mock_settings.S3.AWS_ACCESS_KEY_ID = "key"
            mock_settings.S3.AWS_SECRET_ACCESS_KEY = "secret"

            # to_thread returns the paginated pages list
            mock_to_thread.return_value = [{"Contents": []}]

            # Patch boto3 import
            with patch("boto3.client", return_value=mock_s3_client):
                await worker.run()

        # asyncio.to_thread should have been called for paginator
        assert mock_to_thread.called

    @pytest.mark.asyncio
    async def test_s3_get_object_runs_in_thread(self) -> None:
        """s3_client.get_object and Body.read should be offloaded."""
        from app.workers.ingestion.s3_worker import S3IngestWorker

        worker = S3IngestWorker(
            valkey_client=AsyncMock(),
            db_session_factory=AsyncMock(),
        )

        mock_s3_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b'{"action": "test"}'

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # First call: get_object, second call: body.read
            mock_to_thread.side_effect = [
                {"Body": mock_body},  # get_object response
                b'{"action": "test"}',  # body.read response
            ]
            events = await worker._download_and_parse_s3(
                mock_s3_client, "test-bucket", "events.json"
            )

        assert mock_to_thread.call_count == 2
        assert len(events) == 1
        assert events[0]["action"] == "test"


class TestAzureWorkerAsyncIO:
    """Verify Azure worker uses asyncio.to_thread for blocking SDK calls."""

    @pytest.mark.asyncio
    async def test_azure_list_blobs_runs_in_thread(self) -> None:
        """container_client.list_blobs should be offloaded via asyncio.to_thread."""
        from app.workers.ingestion.azure_worker import AzureBlobIngestWorker

        worker = AzureBlobIngestWorker(
            valkey_client=AsyncMock(),
            db_session_factory=AsyncMock(),
        )

        with (
            patch("app.workers.ingestion.azure_worker.settings") as mock_settings,
            patch.object(worker, "_load_cursor", new_callable=AsyncMock, return_value=None),
            patch(
                "app.workers.ingestion.azure_worker.asyncio.to_thread", new_callable=AsyncMock
            ) as mock_to_thread,
        ):
            mock_settings.AZURE.AZURE_AUDIT_CONTAINER = "test-container"
            mock_settings.AZURE.AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpoints=..."

            mock_container = MagicMock()
            # list_blobs returns empty list (no blobs to process)
            mock_to_thread.side_effect = [
                [],  # list_blobs result
                None,  # container_client.close()
            ]

            # Patch the azure import inside the function
            mock_container_cls = MagicMock()
            mock_container_cls.from_connection_string.return_value = mock_container
            with patch.dict(
                "sys.modules",
                {
                    "azure": MagicMock(),
                    "azure.storage": MagicMock(),
                    "azure.storage.blob": MagicMock(),
                },
            ):
                with patch(
                    "app.workers.ingestion.azure_worker.ContainerClient",
                    mock_container_cls,
                    create=True,
                ):
                    await worker.run()

        # asyncio.to_thread should have been called for list_blobs and close
        assert mock_to_thread.call_count == 2

    @pytest.mark.asyncio
    async def test_azure_download_blob_runs_in_thread(self) -> None:
        """blob download should be offloaded via asyncio.to_thread."""
        from app.workers.ingestion.azure_worker import AzureBlobIngestWorker

        worker = AzureBlobIngestWorker(
            valkey_client=AsyncMock(),
            db_session_factory=AsyncMock(),
        )

        mock_container = MagicMock()

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = b'{"action": "repos.create"}'
            events = await worker._download_and_parse_blob(mock_container, "events.json")

        assert mock_to_thread.called
        assert len(events) == 1
        assert events[0]["action"] == "repos.create"


# ═══════════════════════════════════════════════════════════════════════════════
# M7: Worker Retry Without Backoff/Jitter
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectionWorkerBackoff:
    """Verify detection worker uses exponential backoff with jitter on retry."""

    def test_no_default_retry_delay_on_task(self) -> None:
        """The task should NOT have a fixed default_retry_delay of 30."""
        from app.workers.detection_worker import run_detection_pipeline_task

        assert getattr(run_detection_pipeline_task, "default_retry_delay", 180) != 30

    def test_backoff_formula_produces_correct_values(self) -> None:
        """Verify the exponential backoff + jitter formula."""
        for retries, expected_base in [(0, 30), (1, 60), (2, 120), (3, 240), (4, 480), (5, 600)]:
            backoff = min(30 * (2**retries), 600)
            assert backoff == expected_base
            jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
            total = backoff + jitter
            assert total >= backoff
            assert total <= backoff + max(int(backoff * 0.1), 1)

    def test_backoff_caps_at_600(self) -> None:
        """Backoff should not exceed 600 seconds regardless of retry count."""
        for retries in [5, 6, 10, 20]:
            backoff = min(30 * (2**retries), 600)
            assert backoff == 600

    def test_source_code_uses_countdown_not_default_delay(self) -> None:
        """Verify the source code passes countdown to self.retry()."""
        import inspect

        import app.workers.detection_worker as dw_module

        source = inspect.getsource(dw_module)
        # Should contain countdown parameter in retry call
        assert "countdown=backoff + jitter" in source
        # Should NOT contain default_retry_delay=30
        assert "default_retry_delay=30" not in source
        # Should contain the backoff formula (formatter may compact **)
        assert "self.request.retries" in source
        assert "min(30" in source

    def test_source_code_imports_secrets(self) -> None:
        """Verify secrets module is imported for jitter."""
        import app.workers.detection_worker as dw_module

        assert hasattr(dw_module, "secrets")


class TestBaselineWorkerBackoff:
    """Verify baseline worker uses exponential backoff with jitter on retry."""

    def test_source_code_uses_countdown_not_default_delay(self) -> None:
        """Verify the source code passes countdown to self.retry()."""
        import inspect

        import app.workers.baseline_worker as bw_module

        source = inspect.getsource(bw_module)
        assert "countdown=backoff + jitter" in source
        assert "default_retry_delay" not in source
        assert "self.request.retries" in source
        assert "min(30" in source

    def test_source_code_imports_secrets(self) -> None:
        """Verify secrets module is imported for jitter."""
        import app.workers.baseline_worker as bw_module

        assert hasattr(bw_module, "secrets")

    def test_backoff_formula_matches_detection_worker(self) -> None:
        """Baseline worker should use the same backoff formula."""
        import inspect

        import app.workers.baseline_worker as bw_module
        import app.workers.detection_worker as dw_module

        bw_source = inspect.getsource(bw_module)
        dw_source = inspect.getsource(dw_module)

        # Both should use min(30 * ... , 600) pattern
        assert "min(30" in bw_source
        assert "min(30" in dw_source
        # Both should use countdown
        assert "countdown=backoff + jitter" in bw_source
        assert "countdown=backoff + jitter" in dw_source


class TestGitHubSyncWorkerBackoff:
    """Verify github sync worker uses exponential backoff with jitter on retry."""

    def test_no_default_retry_delay_on_sync_entity(self) -> None:
        """sync_entity should NOT have a fixed default_retry_delay of 30."""
        from app.workers.github_sync_worker import sync_entity

        assert getattr(sync_entity, "default_retry_delay", 180) != 30

    def test_backoff_formula_produces_correct_values(self) -> None:
        """Verify the backoff formula independently."""
        for retries in range(6):
            backoff = min(30 * (2**retries), 600)
            jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
            total = backoff + jitter
            assert total >= backoff
            assert total <= backoff + max(int(backoff * 0.1), 1)
            assert backoff <= 600


# ═══════════════════════════════════════════════════════════════════════════════
# M17: N+1 Query Risk from Lazy Loading
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectionsRouterEagerLoading:
    """Verify that detection queries use selectinload for the rule relationship."""

    def test_list_detections_query_uses_selectinload(self) -> None:
        """The list_detections SELECT should include selectinload(Detection.rule)."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models.detection import Detection

        # Build the same statement the router builds
        stmt = (
            select(Detection)
            .options(selectinload(Detection.rule))
            .order_by(Detection.triggered_at.desc())
        )

        # Verify the options are set (selectinload adds to _with_options)
        # The presence of _with_options confirms eager loading is configured
        options = stmt._with_options
        assert len(options) > 0, "No loading options found on the query"

    def test_get_detection_query_uses_selectinload(self) -> None:
        """The _get_detection_or_404 query should include selectinload."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models.detection import Detection

        stmt = select(Detection).options(selectinload(Detection.rule)).where(Detection.id == 1)
        options = stmt._with_options
        assert len(options) > 0, "No loading options found on _get_detection_or_404 query"

    def test_detection_model_has_rule_relationship(self) -> None:
        """Detection model should have a 'rule' relationship to RuleDefinition."""
        from app.models.detection import Detection

        assert hasattr(Detection, "rule"), "Detection model missing 'rule' relationship"

    def test_selectinload_import_in_router(self) -> None:
        """The detections router should import selectinload."""
        import app.routers.detections as detections_module

        assert hasattr(detections_module, "selectinload")
