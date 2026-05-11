"""Celery worker: poll S3 buckets for new GitHub audit log exports and ingest them.

Each active ``IngestionCursor`` with ``source_type='s3'`` defines a bucket +
prefix to poll.  The worker lists objects newer than the cursor's
``last_file``, downloads each JSON/NDJSON file, and pushes events through the
standard dedup → insert → detection pipeline.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import secrets
from datetime import UTC, datetime
from typing import Any

import structlog
from celery import Task

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)

# Maximum objects to process per poll cycle to bound memory and runtime.
_MAX_OBJECTS_PER_POLL = 100

# Maximum events to batch-insert per file before committing.
_BATCH_SIZE = 500


@celery_app.task(
    name="app.workers.ingestion.s3_worker.poll_s3_sources",
    bind=True,
    max_retries=3,
)
def poll_s3_sources(self: Task) -> dict[str, object]:
    """Celery beat task: iterate active S3 ingestion cursors and ingest new files."""
    try:
        result = asyncio.run(_poll_all_s3_sources())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("poll_s3_sources.failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _poll_all_s3_sources() -> dict[str, Any]:
    """Poll every active S3 ingestion cursor and ingest new objects."""
    import redis.asyncio as aioredis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings
    from app.workers.ingestion.base import AbstractIngestWorker

    class S3IngestWorker(AbstractIngestWorker):
        ingestion_source: str = "s3"

        async def run(self) -> None:
            raise NotImplementedError

    tmp_engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=settings.LOG_LEVEL == "DEBUG",
    )
    tmp_session_factory = async_sessionmaker(
        bind=tmp_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    valkey = aioredis.from_url(settings.VALKEY_URL, decode_responses=False)

    try:
        # Fetch active S3 cursors with row-level locking
        async with tmp_session_factory() as db:
            rows = await db.execute(
                text(
                    "SELECT id, source_name, source_region, source_prefix, last_file "
                    "FROM ingestion_cursors "
                    "WHERE source_type = 's3' AND status = 'active' "
                    "FOR UPDATE SKIP LOCKED"
                )
            )
            cursors = rows.fetchall()

        total_files = 0
        total_events = 0

        for cursor in cursors:
            cursor_id, bucket, region, prefix, last_file = cursor
            try:
                files, events = await _poll_single_s3_source(
                    cursor_id=cursor_id,
                    bucket=bucket,
                    region=region or "us-east-1",
                    prefix=prefix or "",
                    last_file=last_file,
                    session_factory=tmp_session_factory,
                    valkey_client=valkey,
                    worker_cls=S3IngestWorker,
                )
                total_files += files
                total_events += events
            except Exception:
                logger.exception(
                    "poll_s3_sources.source_failed",
                    cursor_id=cursor_id,
                    bucket=bucket,
                )
                async with tmp_session_factory() as db:
                    await db.execute(
                        text(
                            "UPDATE ingestion_cursors "
                            "SET error_count = error_count + 1, "
                            "    error_message = :msg, "
                            "    updated_at = NOW() "
                            "WHERE id = :id"
                        ),
                        {"id": cursor_id, "msg": "Poll failed — see worker logs"},
                    )
                    await db.commit()

        logger.info(
            "poll_s3_sources.complete",
            sources=len(cursors),
            files=total_files,
            events=total_events,
        )
        return {"sources": len(cursors), "files": total_files, "events": total_events}
    finally:
        await valkey.aclose()
        await tmp_engine.dispose()


async def _poll_single_s3_source(
    *,
    cursor_id: int,
    bucket: str,
    region: str,
    prefix: str,
    last_file: str | None,
    session_factory: Any,
    valkey_client: Any,
    worker_cls: type,
) -> tuple[int, int]:
    """List new objects in a single S3 source and ingest them.

    Returns (files_processed, events_inserted).
    """
    import boto3
    from sqlalchemy import text

    s3 = boto3.client("s3", region_name=region)

    # List objects after the last processed file (lexicographic ordering)
    list_kwargs: dict[str, Any] = {
        "Bucket": bucket,
        "Prefix": prefix,
        "MaxKeys": _MAX_OBJECTS_PER_POLL,
    }
    if last_file:
        list_kwargs["StartAfter"] = last_file

    response = s3.list_objects_v2(**list_kwargs)
    objects = response.get("Contents", [])

    if not objects:
        return 0, 0

    worker = worker_cls(valkey_client=valkey_client, db_session_factory=session_factory)

    files_processed = 0
    total_inserted = 0
    latest_file = last_file

    for obj in objects:
        key = obj["Key"]
        # Skip directory markers
        if key.endswith("/"):
            continue

        try:
            events = await _download_and_parse_s3_object(s3, bucket, key)
            if events:
                # Process in batches
                for i in range(0, len(events), _BATCH_SIZE):
                    batch = events[i : i + _BATCH_SIZE]
                    inserted = await worker.ingest_batch(
                        raw_events=batch,
                        source_file_path=f"s3://{bucket}/{key}",
                    )
                    total_inserted += inserted

            files_processed += 1
            latest_file = key

            logger.info(
                "poll_s3_sources.file_processed",
                bucket=bucket,
                key=key,
                events=len(events),
            )
        except Exception:
            logger.exception(
                "poll_s3_sources.file_failed",
                bucket=bucket,
                key=key,
            )
            # Continue with next file rather than aborting the whole source

    # Update cursor position
    if latest_file and latest_file != last_file:
        async with session_factory() as db:
            await db.execute(
                text(
                    "UPDATE ingestion_cursors "
                    "SET last_file = :last_file, "
                    "    last_event_count = last_event_count + :events, "
                    "    last_processed_at = :ts, "
                    "    error_count = 0, "
                    "    error_message = NULL, "
                    "    updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {
                    "id": cursor_id,
                    "last_file": latest_file,
                    "events": total_inserted,
                    "ts": datetime.now(UTC),
                },
            )
            await db.commit()

    return files_processed, total_inserted


async def _download_and_parse_s3_object(
    s3_client: Any,
    bucket: str,
    key: str,
) -> list[dict[str, Any]]:
    """Download and parse a JSON or NDJSON file from S3.

    Supports .json, .ndjson, .json.gz, and .ndjson.gz files.
    Runs the blocking S3 download in a thread to avoid blocking the event loop.
    """
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: s3_client.get_object(Bucket=bucket, Key=key),
    )
    raw_bytes = response["Body"].read()

    # Decompress if gzipped
    if key.endswith(".gz"):
        raw_bytes = gzip.decompress(raw_bytes)

    text_content = raw_bytes.decode("utf-8")

    # Parse as NDJSON (one JSON object per line) or single JSON array
    events: list[dict[str, Any]] = []
    if key.endswith((".ndjson", ".ndjson.gz")):
        for line in text_content.splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
    else:
        parsed = json.loads(text_content)
        if isinstance(parsed, list):
            events = parsed
        elif isinstance(parsed, dict):
            events = [parsed]

    return events
