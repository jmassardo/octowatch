"""MinIO ingest worker: subscribes to MinIO bucket notifications via Valkey pub/sub."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import structlog

from app.config import settings
from app.workers.ingestion.base import AbstractIngestWorker

logger = structlog.get_logger(__name__)


class MinioIngestWorker(AbstractIngestWorker):
    """Processes audit log objects pushed to a MinIO bucket via webhook notifications.

    MinIO publishes a JSON notification to a Valkey channel when a new object
    is created. The worker subscribes, verifies the HMAC-SHA256 signature,
    downloads the object, and ingests the NDJSON payload.
    """

    CHANNEL = "minio:events"

    async def run(self) -> None:
        """Subscribe to the MinIO events channel and process notifications."""
        pubsub = self._valkey.pubsub()
        await pubsub.subscribe(self.CHANNEL)
        logger.info("minio_worker.subscribed", channel=self.CHANNEL)

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = json.loads(message["data"])
                await self._process_notification(data)
            except json.JSONDecodeError as exc:
                logger.warning("minio_worker.json_error", error=str(exc))
            except Exception as exc:
                logger.error("minio_worker.processing_error", error=str(exc))

    async def _process_notification(self, notification: dict[str, Any]) -> None:
        """Validate HMAC signature and ingest the referenced object."""
        # Verify HMAC-SHA256 signature
        signature = notification.get("signature", "")
        payload_bytes = json.dumps(
            {k: v for k, v in notification.items() if k != "signature"}, sort_keys=True
        ).encode()
        expected = hmac.new(
            (settings.MINIO.MINIO_HMAC_SECRET or "").encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            logger.warning("minio_worker.hmac_invalid")
            return

        # Extract object key
        records = notification.get("Records", [])
        for record in records:
            bucket_name = record.get("s3", {}).get("bucket", {}).get("name", "")
            object_key = record.get("s3", {}).get("object", {}).get("key", "")
            if not object_key:
                continue

            events = await self._download_and_parse(bucket_name, object_key)
            if events:
                inserted = await self.ingest_batch(events)
                logger.info(
                    "minio_worker.ingested",
                    bucket=bucket_name,
                    key=object_key,
                    inserted=inserted,
                )

    async def _download_and_parse(self, bucket: str, key: str) -> list[dict[str, Any]]:
        """Download an NDJSON object from MinIO and parse events."""

        import boto3
        from botocore.client import Config

        minio_cfg = settings.MINIO

        s3_client = boto3.client(
            "s3",
            endpoint_url=minio_cfg.MINIO_ENDPOINT_URL,
            aws_access_key_id=minio_cfg.MINIO_INGEST_USER,
            aws_secret_access_key=minio_cfg.MINIO_INGEST_PASSWORD,
            config=Config(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
            ),
        )

        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
        except Exception as exc:
            logger.error("minio_worker.download_failed", bucket=bucket, key=key, error=str(exc))
            return []

        events: list[dict[str, Any]] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("minio_worker.json_line_error", key=key)

        return events
