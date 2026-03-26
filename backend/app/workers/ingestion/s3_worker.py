"""S3 ingest worker: polls an S3 bucket for new audit log objects."""

from __future__ import annotations

import json
from typing import Any

import structlog

from app.config import settings
from app.workers.ingestion.base import AbstractIngestWorker

logger = structlog.get_logger(__name__)


class S3IngestWorker(AbstractIngestWorker):
    """Periodically lists new objects in an S3 bucket using StartAfter cursor."""

    async def run(self) -> None:
        """Single poll cycle: list new objects, ingest, advance cursor."""
        s3_cfg = settings.S3
        if not s3_cfg.S3_AUDIT_BUCKET:
            logger.info("s3_worker.no_bucket_configured")
            return

        import boto3
        from botocore.client import Config

        s3_client = boto3.client(
            "s3",
            region_name=s3_cfg.AWS_DEFAULT_REGION,
            aws_access_key_id=s3_cfg.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=s3_cfg.AWS_SECRET_ACCESS_KEY,
            config=Config(connect_timeout=10, read_timeout=30),
        )

        # Load cursor from DB
        cursor = await self._load_cursor(source_type="s3")
        start_after = cursor or ""

        page_size = 100
        total_inserted = 0

        paginator = s3_client.get_paginator("list_objects_v2")

        for page in paginator.paginate(
            Bucket=s3_cfg.S3_AUDIT_BUCKET,
            Prefix="",
            StartAfter=start_after,
            PaginationConfig={"PageSize": page_size},
        ):
            objects = page.get("Contents", [])
            if not objects:
                break

            for obj in objects:
                key = obj["Key"]
                if not key.endswith((".json", ".ndjson", ".jsonl", ".gz")):
                    continue

                events = await self._download_and_parse_s3(s3_client, s3_cfg.S3_AUDIT_BUCKET, key)
                if events:
                    inserted = await self.ingest_batch(events)
                    total_inserted += inserted
                    logger.info(
                        "s3_worker.ingested",
                        key=key,
                        inserted=inserted,
                    )

                # Advance cursor after each object
                await self._save_cursor(source_type="s3", cursor_value=key)

        if total_inserted:
            logger.info("s3_worker.poll_complete", inserted=total_inserted)

    async def _download_and_parse_s3(
        self,
        s3_client: Any,
        bucket: str,
        key: str,
    ) -> list[dict[str, Any]]:
        """Download and parse an S3 object (NDJSON or JSON array)."""
        import gzip

        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read()
        except Exception as exc:
            logger.error("s3_worker.download_failed", key=key, error=str(exc))
            return []

        # Decompress if gzip
        if key.endswith(".gz"):
            try:
                body = gzip.decompress(body)
            except Exception as exc:
                logger.warning("s3_worker.gunzip_failed", key=key, error=str(exc))
                return []

        content = body.decode("utf-8")
        events: list[dict[str, Any]] = []

        # Try NDJSON first
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    events.append(obj)
                elif isinstance(obj, list):
                    events.extend([e for e in obj if isinstance(e, dict)])
            except json.JSONDecodeError:
                continue

        # If no events parsed as NDJSON, try as JSON array
        if not events:
            try:
                parsed = json.loads(content)
                if isinstance(parsed, list):
                    events = [e for e in parsed if isinstance(e, dict)]
                elif isinstance(parsed, dict):
                    events = [parsed]
            except json.JSONDecodeError:
                pass

        return events

    async def _load_cursor(self, source_type: str) -> str | None:
        """Load the last cursor value from the DB."""
        from sqlalchemy import text

        async with self._make_session() as session:
            result = await session.execute(
                text(
                    "SELECT cursor_value FROM ingestion_cursors "
                    "WHERE source_type = :st ORDER BY updated_at DESC LIMIT 1"
                ),
                {"st": source_type},
            )
            row = result.fetchone()
            return row[0] if row else None

    async def _save_cursor(self, source_type: str, cursor_value: str) -> None:
        """Persist the cursor value to DB (upsert)."""
        from sqlalchemy import text

        async with self._make_session() as session:
            await session.execute(
                text("""
                    INSERT INTO ingestion_cursors (source_type, cursor_value)
                    VALUES (:st, :cv)
                    ON CONFLICT (source_type)
                    DO UPDATE SET cursor_value = EXCLUDED.cursor_value,
                                  updated_at = NOW()
                """),
                {"st": source_type, "cv": cursor_value},
            )
            await session.commit()
