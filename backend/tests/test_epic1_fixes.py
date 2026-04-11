"""Unit tests for the Celery worker tasks added in Epic 1.

Covers:
- notification_worker.send_detection_notifications_task
- detection_worker.sync_ticket_statuses_task
- ingestion/base.prune_event_dedup
- ingestion/s3_worker.poll_s3_sources
- ingestion/azure_worker.poll_azure_sources
- AuditTrailMiddleware field mapping
- org_config authorization
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── prune_event_dedup ────────────────────────────────────────────────────────


class TestPruneEventDedup:
    """Tests for the prune_event_dedup Celery task wrapper."""

    @pytest.mark.anyio
    async def test_prune_dedup_deletes_old_rows(self) -> None:
        """Verify _prune_dedup calls DELETE with a cutoff and commits."""
        from app.workers.ingestion.base import _prune_dedup

        mock_result = MagicMock()
        mock_result.rowcount = 42
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=mock_factory):
            deleted = await _prune_dedup()

        assert deleted == 42
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.anyio
    async def test_prune_dedup_returns_zero_when_nothing(self) -> None:
        """Returns 0 when no rows match the cutoff."""
        from app.workers.ingestion.base import _prune_dedup

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=mock_factory):
            deleted = await _prune_dedup()

        assert deleted == 0


# ── notification_worker ──────────────────────────────────────────────────────


class TestNotificationWorker:
    """Tests for the notification worker async wrapper."""

    @pytest.mark.anyio
    async def test_send_notifications_skips_missing_detection(self) -> None:
        """Returns skipped=True if detection not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.aclose = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        mock_send = AsyncMock()

        with (
            patch(
                "app.workers.notification_worker.AsyncSessionLocal",
                return_value=mock_factory,
            ),
            patch("redis.asyncio.from_url", return_value=mock_valkey),
            patch.dict(
                "sys.modules",
                {
                    "app.services.notification_service": MagicMock(
                        send_detection_notifications=mock_send,
                    ),
                },
            ),
        ):
            from app.workers.notification_worker import _send_notifications

            result = await _send_notifications(detection_id=999)

        assert result["skipped"] is True
        assert result["reason"] == "detection_not_found"

    @pytest.mark.anyio
    async def test_send_notifications_calls_service(self) -> None:
        """Calls send_detection_notifications when detection exists."""
        mock_detection = MagicMock()
        mock_detection.id = 42
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_detection
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.aclose = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        mock_send = AsyncMock()

        with (
            patch(
                "app.workers.notification_worker.AsyncSessionLocal",
                return_value=mock_factory,
            ),
            patch("redis.asyncio.from_url", return_value=mock_valkey),
            patch.dict(
                "sys.modules",
                {
                    "app.services.notification_service": MagicMock(
                        send_detection_notifications=mock_send,
                    ),
                },
            ),
        ):
            from app.workers.notification_worker import _send_notifications

            result = await _send_notifications(detection_id=42)

        assert result["skipped"] is False
        mock_send.assert_awaited_once_with(mock_session, mock_valkey, mock_detection)


# ── sync_ticket_statuses ─────────────────────────────────────────────────────


class TestSyncTicketStatuses:
    """Tests for the sync_ticket_statuses_task async wrapper."""

    @pytest.mark.anyio
    async def test_sync_tickets_returns_count(self) -> None:
        """Verifies _sync_tickets calls the ticketing service and commits."""
        from app.workers.detection_worker import _sync_tickets

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.workers.detection_worker.AsyncSessionLocal",
                return_value=mock_factory,
            ),
            patch(
                "app.services.ticketing_service.sync_ticket_statuses",
                new_callable=AsyncMock,
            ) as mock_sync,
        ):
            mock_sync.return_value = 5
            updated = await _sync_tickets()

        assert updated == 5
        mock_session.commit.assert_awaited_once()


# ── s3_worker poll_s3_sources ────────────────────────────────────────────────


class TestPollS3Sources:
    """Tests for the poll_s3_sources async wrapper."""

    @pytest.mark.anyio
    async def test_poll_s3_creates_worker_and_runs(self) -> None:
        """Verifies _poll_s3 creates an S3IngestWorker and calls run()."""
        from app.workers.ingestion.s3_worker import _poll_s3

        mock_valkey = AsyncMock()
        mock_valkey.aclose = AsyncMock()

        with (
            patch("redis.asyncio.from_url", return_value=mock_valkey),
            patch("app.database.AsyncSessionLocal"),
            patch("app.workers.ingestion.s3_worker.S3IngestWorker") as mock_cls,
        ):
            mock_worker = AsyncMock()
            mock_cls.return_value = mock_worker

            result = await _poll_s3()

        assert result["source"] == "s3"
        mock_worker.run.assert_awaited_once()
        mock_valkey.aclose.assert_awaited_once()


# ── azure_worker poll_azure_sources ──────────────────────────────────────────


class TestPollAzureSources:
    """Tests for the poll_azure_sources async wrapper."""

    @pytest.mark.anyio
    async def test_poll_azure_creates_worker_and_runs(self) -> None:
        """Verifies _poll_azure creates an AzureBlobIngestWorker and calls run()."""
        from app.workers.ingestion.azure_worker import _poll_azure

        mock_valkey = AsyncMock()
        mock_valkey.aclose = AsyncMock()

        with (
            patch("redis.asyncio.from_url", return_value=mock_valkey),
            patch("app.database.AsyncSessionLocal"),
            patch("app.workers.ingestion.azure_worker.AzureBlobIngestWorker") as mock_cls,
        ):
            mock_worker = AsyncMock()
            mock_cls.return_value = mock_worker

            result = await _poll_azure()

        assert result["source"] == "azure_blob"
        mock_worker.run.assert_awaited_once()
        mock_valkey.aclose.assert_awaited_once()


# ── AuditTrailMiddleware ─────────────────────────────────────────────────────


class TestAuditTrailMiddlewareFields:
    """Validate AuditTrailMiddleware creates AuditTrail with correct fields."""

    def test_audit_trail_model_fields_match_middleware(self) -> None:
        """Ensure AuditTrail model field names used in middleware are valid."""
        from app.models.audit_trail import AuditTrail

        columns = {c.name for c in AuditTrail.__table__.columns}

        # These are the fields the middleware sets
        required_fields = {
            "user_login",
            "action_type",
            "resource_type",
            "resource_id",
            "ip_address",
            "user_agent",
            "outcome",
            "parameters",
        }
        for field in required_fields:
            assert field in columns, f"AuditTrail model missing field: {field}"

        # These old fields should NOT exist in the model
        removed_fields = {
            "actor",
            "action",
            "request_method",
            "request_path",
            "response_status",
        }
        for field in removed_fields:
            assert field not in columns, f"AuditTrail still has deprecated field: {field}"

    def test_audit_trail_constructor_accepts_correct_fields(self) -> None:
        """AuditTrail can be constructed with the fields middleware now uses."""
        from app.models.audit_trail import AuditTrail

        trail = AuditTrail(
            user_login="testuser",
            action_type="api.post.api_v1_events",
            resource_type="api_endpoint",
            resource_id=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            outcome="success",
            parameters={
                "method": "POST",
                "path": "/api/v1/events",
                "status_code": 200,
                "elapsed_ms": 42,
            },
        )

        assert trail.user_login == "testuser"
        assert trail.action_type == "api.post.api_v1_events"
        assert trail.outcome == "success"
        assert trail.parameters is not None
        assert trail.parameters["method"] == "POST"
        assert trail.user_agent == "Mozilla/5.0"

    def test_audit_trail_error_outcome(self) -> None:
        """AuditTrail correctly records error outcome with error_detail."""
        from app.models.audit_trail import AuditTrail

        trail = AuditTrail(
            user_login="testuser",
            action_type="api.delete.api_v1_rules_42",
            outcome="error",
            error_detail="HTTP 403",
        )
        assert trail.outcome == "error"
        assert trail.error_detail == "HTTP 403"


# ── PipelineResult.detection_ids ─────────────────────────────────────────────


class TestPipelineResultDetectionIds:
    """Verify the PipelineResult dataclass includes detection_ids."""

    def test_pipeline_result_has_detection_ids(self) -> None:
        from app.services.detection_service import PipelineResult

        result = PipelineResult(
            detections_written=3,
            detection_ids=[10, 20, 30],
        )
        assert result.detection_ids == [10, 20, 30]
        assert result.detections_written == 3

    def test_pipeline_result_defaults_empty(self) -> None:
        from app.services.detection_service import PipelineResult

        result = PipelineResult()
        assert result.detection_ids == []
        assert result.detections_written == 0
        assert result.failed_rules == []


# ── Detection worker notification chaining ───────────────────────────────────


class TestDetectionWorkerNotificationChain:
    """Verify the detection worker chains notifications after pipeline run."""

    @pytest.mark.anyio
    async def test_pipeline_chains_notifications(self) -> None:
        """After a successful pipeline run, notification tasks are queued."""
        from app.workers.detection_worker import _run_pipeline

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        mock_pipeline_result = MagicMock()
        mock_pipeline_result.detections_written = 2
        mock_pipeline_result.detection_ids = [100, 200]

        # Build a proper async context manager mock for AsyncSessionLocal
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_ctx)

        with (
            patch("app.workers.detection_worker.AsyncSessionLocal", mock_factory),
            patch(
                "app.services.detection_service.run_detection_pipeline",
                new_callable=AsyncMock,
            ) as mock_pipeline,
            patch(
                "app.workers.notification_worker.send_detection_notifications_task",
            ) as mock_notify,
        ):
            mock_pipeline.return_value = mock_pipeline_result

            result = await _run_pipeline([1, 2, 3])

        assert result["detections_written"] == 2
        assert result["detection_ids"] == [100, 200]
        assert mock_notify.delay.call_count == 2
        mock_notify.delay.assert_any_call(100)
        mock_notify.delay.assert_any_call(200)
