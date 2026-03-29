"""Unit tests for MinioIngestWorker — HMAC verification, notification processing, download."""

from __future__ import annotations

import gzip
import hashlib
import hmac as hmac_mod
import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.ingestion.minio_worker import MinioIngestWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_worker() -> MinioIngestWorker:
    """Create a worker with mocked Valkey and DB session factory."""
    return MinioIngestWorker(
        valkey_client=AsyncMock(),
        db_session_factory=AsyncMock(),
    )


def _s3_notification(
    bucket: str = "audit-logs",
    key: str = "2024/events.json.gz",
) -> dict[str, Any]:
    """Return a minimal S3 event notification matching MinIO's access format."""
    return {
        "Records": [
            {
                "eventVersion": "2.0",
                "eventSource": "minio:s3",
                "eventName": "s3:ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key, "size": 1234},
                },
            }
        ]
    }


def _sign_notification(notification: dict[str, Any], secret: str) -> dict[str, Any]:
    """Add a valid HMAC-SHA256 signature to a notification dict."""
    payload_bytes = json.dumps(notification, sort_keys=True).encode()
    sig = hmac_mod.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return {**notification, "signature": sig}


# ---------------------------------------------------------------------------
# _process_notification — HMAC behaviour
# ---------------------------------------------------------------------------


class TestProcessNotificationHMAC:
    """Verify that HMAC verification is optional and works when configured."""

    @pytest.mark.asyncio
    async def test_skips_hmac_when_secret_not_configured(self) -> None:
        """When MINIO_HMAC_SECRET is None, HMAC check is skipped and records are processed."""
        worker = _make_worker()
        notification = _s3_notification()

        with (
            patch.object(
                worker,
                "_download_and_parse",
                new_callable=AsyncMock,
                return_value=[{"action": "x"}],
            ) as mock_dl,
            patch.object(worker, "ingest_batch", new_callable=AsyncMock, return_value=1),
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = None
            await worker._process_notification(notification)

        mock_dl.assert_called_once_with("audit-logs", "2024/events.json.gz")

    @pytest.mark.asyncio
    async def test_skips_hmac_when_secret_is_empty_string(self) -> None:
        """An empty string secret should also skip HMAC (falsy)."""
        worker = _make_worker()
        notification = _s3_notification()

        with (
            patch.object(
                worker,
                "_download_and_parse",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = ""
            await worker._process_notification(notification)

        # Should not raise / should not reject

    @pytest.mark.asyncio
    async def test_rejects_invalid_hmac_when_secret_configured(self) -> None:
        """When HMAC secret is set, an invalid signature causes rejection."""
        worker = _make_worker()
        notification = {**_s3_notification(), "signature": "bad_sig"}

        with (
            patch.object(worker, "_download_and_parse", new_callable=AsyncMock) as mock_dl,
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = "my-secret"
            await worker._process_notification(notification)

        mock_dl.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_valid_hmac_when_secret_configured(self) -> None:
        """A correctly signed notification is accepted when HMAC secret is set."""
        worker = _make_worker()
        secret = "supersecret"
        notification = _s3_notification()
        signed = _sign_notification(notification, secret)

        with (
            patch.object(
                worker,
                "_download_and_parse",
                new_callable=AsyncMock,
                return_value=[{"action": "x"}],
            ) as mock_dl,
            patch.object(
                worker,
                "ingest_batch",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = secret
            await worker._process_notification(signed)

        mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_missing_signature_when_secret_configured(self) -> None:
        """No signature field + HMAC secret configured → rejection."""
        worker = _make_worker()
        notification = _s3_notification()  # no "signature" key

        with (
            patch.object(worker, "_download_and_parse", new_callable=AsyncMock) as mock_dl,
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = "my-secret"
            await worker._process_notification(notification)

        mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# _process_notification — Records extraction
# ---------------------------------------------------------------------------


class TestProcessNotificationRecords:
    """Verify that S3 event records are extracted and processed correctly."""

    @pytest.mark.asyncio
    async def test_processes_each_record_in_notification(self) -> None:
        """Multiple records in one notification should each trigger a download."""
        worker = _make_worker()
        notification = {
            "Records": [
                {"s3": {"bucket": {"name": "b"}, "object": {"key": "k1"}}},
                {"s3": {"bucket": {"name": "b"}, "object": {"key": "k2"}}},
            ]
        }

        with (
            patch.object(
                worker,
                "_download_and_parse",
                new_callable=AsyncMock,
                return_value=[{"action": "x"}],
            ) as mock_dl,
            patch.object(
                worker,
                "ingest_batch",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = None
            await worker._process_notification(notification)

        assert mock_dl.call_count == 2
        mock_dl.assert_any_call("b", "k1")
        mock_dl.assert_any_call("b", "k2")

    @pytest.mark.asyncio
    async def test_skips_records_without_object_key(self) -> None:
        """Records missing an object key should be silently skipped."""
        worker = _make_worker()
        notification = {
            "Records": [
                {"s3": {"bucket": {"name": "b"}, "object": {"key": ""}}},
                {"s3": {"bucket": {"name": "b"}, "object": {"key": "valid.json"}}},
            ]
        }

        with (
            patch.object(
                worker,
                "_download_and_parse",
                new_callable=AsyncMock,
                return_value=[{"action": "x"}],
            ) as mock_dl,
            patch.object(
                worker,
                "ingest_batch",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = None
            await worker._process_notification(notification)

        mock_dl.assert_called_once_with("b", "valid.json")

    @pytest.mark.asyncio
    async def test_no_ingest_when_download_returns_empty(self) -> None:
        """If download returns no events, ingest_batch should not be called."""
        worker = _make_worker()
        notification = _s3_notification()

        with (
            patch.object(worker, "_download_and_parse", new_callable=AsyncMock, return_value=[]),
            patch.object(worker, "ingest_batch", new_callable=AsyncMock) as mock_ingest,
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = None
            await worker._process_notification(notification)

        mock_ingest.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_records_list_is_noop(self) -> None:
        """A notification with no Records should be a no-op."""
        worker = _make_worker()
        notification: dict[str, Any] = {"Records": []}

        with (
            patch.object(worker, "_download_and_parse", new_callable=AsyncMock) as mock_dl,
            patch("app.workers.ingestion.minio_worker.settings") as mock_settings,
        ):
            mock_settings.MINIO.MINIO_HMAC_SECRET = None
            await worker._process_notification(notification)

        mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# _download_and_parse
# ---------------------------------------------------------------------------


class TestDownloadAndParse:
    """Verify NDJSON download, gzip decompression, and line parsing."""

    def _mock_s3_body(self, content: bytes) -> MagicMock:
        """Create a mock S3 response body."""
        body = MagicMock()
        body.read.return_value = content
        return body

    @pytest.mark.asyncio
    async def test_parses_plain_ndjson(self) -> None:
        """Plain (non-gzipped) NDJSON content should be parsed into events."""
        worker = _make_worker()
        ndjson = b'{"action":"repos.create"}\n{"action":"repos.delete"}\n'

        mock_client = MagicMock()
        mock_client.get_object.return_value = {
            "Body": self._mock_s3_body(ndjson),
        }

        with patch("boto3.client", return_value=mock_client):
            events = await worker._download_and_parse("bucket", "events.ndjson")

        assert len(events) == 2
        assert events[0]["action"] == "repos.create"
        assert events[1]["action"] == "repos.delete"

    @pytest.mark.asyncio
    async def test_decompresses_gzip_by_extension(self) -> None:
        """Files ending in .gz should be decompressed before parsing."""
        worker = _make_worker()
        raw = b'{"action":"member.add"}\n'
        gz_content = gzip.compress(raw)

        mock_client = MagicMock()
        mock_client.get_object.return_value = {
            "Body": self._mock_s3_body(gz_content),
        }

        with patch("boto3.client", return_value=mock_client):
            events = await worker._download_and_parse(
                "bucket",
                "events.json.gz",
            )

        assert len(events) == 1
        assert events[0]["action"] == "member.add"

    @pytest.mark.asyncio
    async def test_decompresses_gzip_by_magic_bytes(self) -> None:
        """Gzip content should be detected by magic bytes even without .gz extension."""
        worker = _make_worker()
        raw = b'{"action":"org.update"}\n'
        gz_content = gzip.compress(raw)

        mock_client = MagicMock()
        mock_client.get_object.return_value = {
            "Body": self._mock_s3_body(gz_content),
        }

        with patch("boto3.client", return_value=mock_client):
            events = await worker._download_and_parse("bucket", "events.ndjson")

        assert len(events) == 1
        assert events[0]["action"] == "org.update"

    @pytest.mark.asyncio
    async def test_skips_invalid_json_lines(self) -> None:
        """Invalid JSON lines should be skipped, valid lines still parsed."""
        worker = _make_worker()
        ndjson = b'{"action":"repos.create"}\nINVALID_JSON\n{"action":"repos.delete"}\n'

        mock_client = MagicMock()
        mock_client.get_object.return_value = {
            "Body": self._mock_s3_body(ndjson),
        }

        with patch("boto3.client", return_value=mock_client):
            events = await worker._download_and_parse("bucket", "events.ndjson")

        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_skips_empty_lines(self) -> None:
        """Blank lines in NDJSON content should be silently skipped."""
        worker = _make_worker()
        ndjson = b'\n{"action":"repos.create"}\n\n\n{"action":"repos.delete"}\n\n'

        mock_client = MagicMock()
        mock_client.get_object.return_value = {
            "Body": self._mock_s3_body(ndjson),
        }

        with patch("boto3.client", return_value=mock_client):
            events = await worker._download_and_parse("bucket", "events.ndjson")

        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_on_download_failure(self) -> None:
        """S3 download errors should return an empty list, not raise."""
        worker = _make_worker()

        mock_client = MagicMock()
        mock_client.get_object.side_effect = Exception("ConnectionError")

        with patch("boto3.client", return_value=mock_client):
            events = await worker._download_and_parse("bucket", "events.ndjson")

        assert events == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_gzip_error(self) -> None:
        """Corrupt gzip content should return an empty list."""
        worker = _make_worker()
        # Starts with gzip magic bytes but is not valid gzip
        corrupt_gz = b"\x1f\x8b" + b"corrupted_data_here"

        mock_client = MagicMock()
        mock_client.get_object.return_value = {
            "Body": self._mock_s3_body(corrupt_gz),
        }

        with patch("boto3.client", return_value=mock_client):
            events = await worker._download_and_parse("bucket", "events.ndjson")

        assert events == []


# ---------------------------------------------------------------------------
# run() — pub/sub message loop
# ---------------------------------------------------------------------------


class TestRunLoop:
    """Verify the pub/sub subscription loop handles messages correctly."""

    @pytest.mark.asyncio
    async def test_processes_valid_message(self) -> None:
        """A valid JSON message of type 'message' should be forwarded to _process_notification."""
        worker = _make_worker()
        notification = _s3_notification()

        # Create an async iterator that yields one message then stops
        async def _listen() -> AsyncGenerator[dict[str, Any], None]:
            yield {
                "type": "message",
                "data": json.dumps(notification).encode(),
            }

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = _listen
        # pubsub() is a synchronous call — use MagicMock return
        worker._valkey.pubsub = MagicMock(return_value=mock_pubsub)

        with patch.object(
            worker,
            "_process_notification",
            new_callable=AsyncMock,
        ) as mock_process:
            await worker.run()

        mock_process.assert_called_once_with(notification)

    @pytest.mark.asyncio
    async def test_ignores_non_message_types(self) -> None:
        """Messages with type != 'message' (e.g., 'subscribe') should be ignored."""
        worker = _make_worker()

        async def _listen() -> AsyncGenerator[dict[str, Any], None]:
            yield {"type": "subscribe", "data": b"1"}

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = _listen
        worker._valkey.pubsub = MagicMock(return_value=mock_pubsub)

        with patch.object(
            worker,
            "_process_notification",
            new_callable=AsyncMock,
        ) as mock_process:
            await worker.run()

        mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_json_decode_error_gracefully(self) -> None:
        """Invalid JSON in a message should be logged but not crash the loop."""
        worker = _make_worker()

        async def _listen() -> AsyncGenerator[dict[str, Any], None]:
            yield {"type": "message", "data": b"NOT VALID JSON"}

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = _listen
        worker._valkey.pubsub = MagicMock(return_value=mock_pubsub)

        with patch.object(
            worker,
            "_process_notification",
            new_callable=AsyncMock,
        ) as mock_process:
            await worker.run()

        mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_processing_error_gracefully(self) -> None:
        """Exceptions in _process_notification should be caught, not crash the loop."""
        worker = _make_worker()
        notification = _s3_notification()

        async def _listen() -> AsyncGenerator[dict[str, Any], None]:
            yield {
                "type": "message",
                "data": json.dumps(notification).encode(),
            }

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = _listen
        worker._valkey.pubsub = MagicMock(return_value=mock_pubsub)

        with patch.object(
            worker,
            "_process_notification",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            # Should not raise
            await worker.run()
