"""Tests for S3 and Azure Blob ingestion workers."""

from __future__ import annotations

import gzip
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── S3 worker tests ─────────────────────────────────────────────────────────


class TestS3DownloadAndParse:
    """Test the S3 file download and parsing logic."""

    @pytest.mark.asyncio
    async def test_parses_json_array(self):
        from app.workers.ingestion.s3_worker import _download_and_parse_s3_object

        events = [
            {"action": "repos.create", "actor": "alice"},
            {"action": "repos.delete", "actor": "bob"},
        ]
        body_mock = MagicMock()
        body_mock.read.return_value = json.dumps(events).encode("utf-8")

        s3 = MagicMock()
        s3.get_object.return_value = {"Body": body_mock}

        result = await _download_and_parse_s3_object(s3, "my-bucket", "logs/export.json")
        assert len(result) == 2
        assert result[0]["action"] == "repos.create"
        assert result[1]["actor"] == "bob"

    @pytest.mark.asyncio
    async def test_parses_ndjson(self):
        from app.workers.ingestion.s3_worker import _download_and_parse_s3_object

        ndjson = '{"action": "a"}\n{"action": "b"}\n'
        body_mock = MagicMock()
        body_mock.read.return_value = ndjson.encode("utf-8")

        s3 = MagicMock()
        s3.get_object.return_value = {"Body": body_mock}

        result = await _download_and_parse_s3_object(s3, "bucket", "logs/export.ndjson")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_parses_gzipped_json(self):
        from app.workers.ingestion.s3_worker import _download_and_parse_s3_object

        events = [{"action": "repos.create"}]
        compressed = gzip.compress(json.dumps(events).encode("utf-8"))
        body_mock = MagicMock()
        body_mock.read.return_value = compressed

        s3 = MagicMock()
        s3.get_object.return_value = {"Body": body_mock}

        result = await _download_and_parse_s3_object(s3, "bucket", "logs/export.json.gz")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_parses_single_object(self):
        from app.workers.ingestion.s3_worker import _download_and_parse_s3_object

        event = {"action": "repos.create", "actor": "alice"}
        body_mock = MagicMock()
        body_mock.read.return_value = json.dumps(event).encode("utf-8")

        s3 = MagicMock()
        s3.get_object.return_value = {"Body": body_mock}

        result = await _download_and_parse_s3_object(s3, "bucket", "logs/single.json")
        assert len(result) == 1
        assert result[0]["action"] == "repos.create"

    @pytest.mark.asyncio
    async def test_parses_gzipped_ndjson(self):
        from app.workers.ingestion.s3_worker import _download_and_parse_s3_object

        ndjson = '{"action": "a"}\n{"action": "b"}\n'
        compressed = gzip.compress(ndjson.encode("utf-8"))
        body_mock = MagicMock()
        body_mock.read.return_value = compressed

        s3 = MagicMock()
        s3.get_object.return_value = {"Body": body_mock}

        result = await _download_and_parse_s3_object(s3, "bucket", "logs/export.ndjson.gz")
        assert len(result) == 2


class TestS3PollSingleSource:
    """Test cursor-based S3 polling logic."""

    @pytest.mark.asyncio
    async def test_skips_directory_markers(self):
        from app.workers.ingestion.s3_worker import _poll_single_s3_source

        s3_mock = MagicMock()
        s3_mock.list_objects_v2.return_value = {
            "Contents": [{"Key": "logs/"}, {"Key": "logs/subdir/"}]
        }

        with patch("boto3.client", return_value=s3_mock):
            worker_cls = MagicMock()
            session_factory = AsyncMock()

            files, events = await _poll_single_s3_source(
                cursor_id=1,
                bucket="test-bucket",
                region="us-east-1",
                prefix="logs/",
                last_file=None,
                session_factory=session_factory,
                valkey_client=AsyncMock(),
                worker_cls=worker_cls,
            )

        assert files == 0
        assert events == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_objects(self):
        from app.workers.ingestion.s3_worker import _poll_single_s3_source

        s3_mock = MagicMock()
        s3_mock.list_objects_v2.return_value = {}

        with patch("boto3.client", return_value=s3_mock):
            files, events = await _poll_single_s3_source(
                cursor_id=1,
                bucket="test-bucket",
                region="us-east-1",
                prefix="logs/",
                last_file=None,
                session_factory=AsyncMock(),
                valkey_client=AsyncMock(),
                worker_cls=MagicMock(),
            )

        assert files == 0
        assert events == 0


# ── Azure worker tests ──────────────────────────────────────────────────────


class TestAzureDownloadAndParse:
    """Test the Azure Blob download and parsing logic."""

    @pytest.mark.asyncio
    async def test_parses_json_array(self):
        from app.workers.ingestion.azure_worker import _download_and_parse_blob

        events = [
            {"action": "repos.create", "actor": "alice"},
            {"action": "repos.delete", "actor": "bob"},
        ]
        blob_client = MagicMock()
        download_stream = MagicMock()
        download_stream.readall.return_value = json.dumps(events).encode("utf-8")
        blob_client.download_blob.return_value = download_stream

        container = MagicMock()
        container.get_blob_client.return_value = blob_client

        result = await _download_and_parse_blob(container, "logs/export.json")
        assert len(result) == 2
        assert result[0]["action"] == "repos.create"

    @pytest.mark.asyncio
    async def test_parses_ndjson(self):
        from app.workers.ingestion.azure_worker import _download_and_parse_blob

        ndjson = '{"action": "a"}\n{"action": "b"}\n'
        blob_client = MagicMock()
        download_stream = MagicMock()
        download_stream.readall.return_value = ndjson.encode("utf-8")
        blob_client.download_blob.return_value = download_stream

        container = MagicMock()
        container.get_blob_client.return_value = blob_client

        result = await _download_and_parse_blob(container, "logs/export.ndjson")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_parses_gzipped_json(self):
        from app.workers.ingestion.azure_worker import _download_and_parse_blob

        events = [{"action": "repos.create"}]
        compressed = gzip.compress(json.dumps(events).encode("utf-8"))
        blob_client = MagicMock()
        download_stream = MagicMock()
        download_stream.readall.return_value = compressed
        blob_client.download_blob.return_value = download_stream

        container = MagicMock()
        container.get_blob_client.return_value = blob_client

        result = await _download_and_parse_blob(container, "logs/export.json.gz")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_parses_single_object(self):
        from app.workers.ingestion.azure_worker import _download_and_parse_blob

        event = {"action": "repos.create", "actor": "alice"}
        blob_client = MagicMock()
        download_stream = MagicMock()
        download_stream.readall.return_value = json.dumps(event).encode("utf-8")
        blob_client.download_blob.return_value = download_stream

        container = MagicMock()
        container.get_blob_client.return_value = blob_client

        result = await _download_and_parse_blob(container, "logs/single.json")
        assert len(result) == 1


class TestAzurePollSingleSource:
    """Test cursor-based Azure Blob polling logic."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_blobs(self):
        from app.workers.ingestion.azure_worker import _poll_single_azure_source

        container_mock = MagicMock()
        container_mock.list_blobs.return_value = iter([])

        with patch(
            "azure.storage.blob.ContainerClient.from_container_url",
            return_value=container_mock,
        ):
            blobs, events = await _poll_single_azure_source(
                cursor_id=1,
                container_url="https://account.blob.core.windows.net/container?sas=token",
                prefix="logs/",
                last_file=None,
                session_factory=AsyncMock(),
                valkey_client=AsyncMock(),
                worker_cls=MagicMock(),
            )

        assert blobs == 0
        assert events == 0

    @pytest.mark.asyncio
    async def test_skips_blobs_before_cursor(self):
        from app.workers.ingestion.azure_worker import _poll_single_azure_source

        blob1 = MagicMock()
        blob1.name = "logs/2024-01-01.json"
        blob2 = MagicMock()
        blob2.name = "logs/2024-01-02.json"

        container_mock = MagicMock()
        container_mock.list_blobs.return_value = iter([blob1, blob2])

        with patch(
            "azure.storage.blob.ContainerClient.from_container_url",
            return_value=container_mock,
        ):
            # last_file = blob2's name, so both should be skipped
            blobs, events = await _poll_single_azure_source(
                cursor_id=1,
                container_url="https://account.blob.core.windows.net/container",
                prefix="logs/",
                last_file="logs/2024-01-02.json",
                session_factory=AsyncMock(),
                valkey_client=AsyncMock(),
                worker_cls=MagicMock(),
            )

        assert blobs == 0
        assert events == 0
