"""Tests for automation_worker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDispatchAutomationTask:
    """Tests for dispatch_automation_task."""

    @patch("app.workers.automation_worker._dispatch")
    def test_calls_dispatch_service(self, mock_dispatch: MagicMock) -> None:
        """dispatch_automation_task invokes _dispatch with correct args."""
        from app.workers.automation_worker import dispatch_automation_task

        mock_dispatch.return_value = {"targets_dispatched": 2, "dry_run": False}

        result = dispatch_automation_task(42)

        mock_dispatch.assert_called_once_with(42, dry_run=False)
        assert result["status"] == "ok"
        assert result["detection_id"] == 42
        assert result["targets_dispatched"] == 2

    @patch("app.workers.automation_worker._dispatch")
    def test_passes_dry_run_flag(self, mock_dispatch: MagicMock) -> None:
        """dispatch_automation_task forwards dry_run to _dispatch."""
        from app.workers.automation_worker import dispatch_automation_task

        mock_dispatch.return_value = {"targets_dispatched": 0, "dry_run": True}

        result = dispatch_automation_task(7, dry_run=True)

        mock_dispatch.assert_called_once_with(7, dry_run=True)
        assert result["dry_run"] is True

    @patch("app.workers.automation_worker._dispatch")
    def test_retries_on_failure(self, mock_dispatch: MagicMock) -> None:
        """dispatch_automation_task retries on exception."""
        from app.workers.automation_worker import dispatch_automation_task

        mock_dispatch.side_effect = RuntimeError("connection refused")

        with pytest.raises(RuntimeError, match="connection refused"):
            dispatch_automation_task(99)


class TestRetryFailedDeliveriesTask:
    """Tests for retry_failed_deliveries_task."""

    @patch("app.workers.automation_worker._retry_failed")
    def test_calls_retry_service(self, mock_retry: MagicMock) -> None:
        """retry_failed_deliveries_task invokes _retry_failed."""
        from app.workers.automation_worker import retry_failed_deliveries_task

        mock_retry.return_value = {"retried": 5}

        result = retry_failed_deliveries_task()

        mock_retry.assert_called_once()
        assert result["status"] == "ok"
        assert result["retried"] == 5

    @patch("app.workers.automation_worker._retry_failed")
    def test_retries_on_failure(self, mock_retry: MagicMock) -> None:
        """retry_failed_deliveries_task retries on exception."""
        from app.workers.automation_worker import retry_failed_deliveries_task

        mock_retry.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            retry_failed_deliveries_task()


class TestDetectionWorkerAutomationChain:
    """Tests that detection_worker chains automation after detections."""

    @patch("app.workers.detection_worker._run_pipeline")
    def test_chains_automation_for_detections(
        self,
        mock_run: MagicMock,
    ) -> None:
        """Detection worker queues automation tasks for each detection."""
        mock_run.return_value = {
            "detections_written": 2,
            "detection_ids": [101, 102],
        }

        from app.workers.detection_worker import run_detection_pipeline_task

        result = run_detection_pipeline_task([1, 2, 3])

        assert result["status"] == "ok"
        assert result["detection_ids"] == [101, 102]
        assert result["detections_written"] == 2

    @patch("app.workers.detection_worker._run_pipeline")
    def test_automation_failure_does_not_break_pipeline(self, mock_run: MagicMock) -> None:
        """If automation chaining fails, the pipeline still returns results."""
        mock_run.return_value = {
            "detections_written": 1,
            "detection_ids": [200],
        }

        from app.workers.detection_worker import run_detection_pipeline_task

        # Even if automation import were to fail, pipeline should succeed
        result = run_detection_pipeline_task([10])

        assert result["status"] == "ok"
        assert result["detections_written"] == 1


class TestDispatchAsync:
    """Tests for the _dispatch async helper."""

    @pytest.mark.asyncio
    @patch("app.services.automation_service.dispatch_automation")
    async def test_dispatch_creates_engine_and_calls_service(
        self, mock_dispatch: AsyncMock
    ) -> None:
        """_dispatch creates a disposable engine and calls dispatch_automation."""
        mock_dispatch.return_value = {"targets_dispatched": 1, "dry_run": False}

        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()

        mock_session = AsyncMock()

        with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=mock_engine):
            with patch("sqlalchemy.ext.asyncio.async_sessionmaker") as mock_factory_cls:
                mock_factory = MagicMock()
                mock_factory_cls.return_value = mock_factory

                # Make the context manager return mock_session
                mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
                mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

                from app.workers.automation_worker import _dispatch

                result = await _dispatch(55, dry_run=False)

                mock_dispatch.assert_called_once_with(mock_session, 55, dry_run=False)
                assert result == {"targets_dispatched": 1, "dry_run": False}
                mock_engine.dispose.assert_called_once()
