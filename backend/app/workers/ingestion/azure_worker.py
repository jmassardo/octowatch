"""Celery worker: poll Azure Blob Storage containers for new audit log exports.

Each active ``IngestionCursor`` with ``source_type='azure_blob'`` defines a
container + prefix to poll.  The worker lists blobs newer than the cursor's
``last_file``, downloads each JSON/NDJSON blob, and pushes events through the
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

# Maximum blobs to process per poll cycle.
_MAX_BLOBS_PER_POLL = 100

# Maximum events to batch-insert per file.
_BATCH_SIZE = 500


@celery_app.task(
    name="app.workers.ingestion.azure_worker.poll_azure_sources",
    bind=True,
    max_retries=3,
)
def poll_azure_sources(self: Task) -> dict[str, object]:
    """Celery beat task: iterate active Azure Blob ingestion cursors and ingest new blobs."""
    try:
        result = asyncio.run(_poll_all_azure_sources())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("poll_azure_sources.failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _poll_all_azure_sources() -> dict[str, Any]:
    """Poll every active Azure Blob ingestion cursor and ingest new blobs."""
    import redis.asyncio as aioredis
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings
    from app.workers.ingestion.base import AbstractIngestWorker

    class AzureBlobIngestWorker(AbstractIngestWorker):
        ingestion_source: str = "azure_blob"

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
        async with tmp_session_factory() as db:
            rows = await db.execute(
                text(
                    "SELECT id, source_name, source_region, source_prefix, last_file "
                    "FROM ingestion_cursors "
                    "WHERE source_type = 'azure_blob' AND status = 'active' "
                    "FOR UPDATE SKIP LOCKED"
                )
            )
            cursors = rows.fetchall()

        total_blobs = 0
        total_events = 0

        for cursor in cursors:
            cursor_id, container_url, _region, prefix, last_file = cursor
            try:
                blobs, events = await _poll_single_azure_source(
                    cursor_id=cursor_id,
                    container_url=container_url,
                    prefix=prefix or "",
                    last_file=last_file,
                    session_factory=tmp_session_factory,
                    valkey_client=valkey,
                    worker_cls=AzureBlobIngestWorker,
                )
                total_blobs += blobs
                total_events += events
            except Exception:
                logger.exception(
                    "poll_azure_sources.source_failed",
                    cursor_id=cursor_id,
                    container_url=container_url,
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
            "poll_azure_sources.complete",
            sources=len(cursors),
            blobs=total_blobs,
            events=total_events,
        )
        return {"sources": len(cursors), "blobs": total_blobs, "events": total_events}
    finally:
        await valkey.aclose()
        await tmp_engine.dispose()


async def _poll_single_azure_source(
    *,
    cursor_id: int,
    container_url: str,
    prefix: str,
    last_file: str | None,
    session_factory: Any,
    valkey_client: Any,
    worker_cls: type,
) -> tuple[int, int]:
    """List new blobs in a single Azure container and ingest them.

    ``container_url`` is the full container URL including SAS token or
    the storage account connection string.  The ``source_name`` field
    on the IngestionCursor stores this value.

    Returns (blobs_processed, events_inserted).
    """
    from azure.storage.blob import ContainerClient
    from sqlalchemy import text

    container_client = ContainerClient.from_container_url(container_url)

    # List blobs with the given prefix
    blob_list = []
    count = 0
    for blob in container_client.list_blobs(name_starts_with=prefix):
        # Skip blobs at or before the cursor position (lexicographic)
        if last_file and blob.name <= last_file:
            continue
        blob_list.append(blob)
        count += 1
        if count >= _MAX_BLOBS_PER_POLL:
            break

    if not blob_list:
        return 0, 0

    worker = worker_cls(valkey_client=valkey_client, db_session_factory=session_factory)

    blobs_processed = 0
    total_inserted = 0
    latest_blob = last_file

    for blob in blob_list:
        blob_name = blob.name
        if blob_name.endswith("/"):
            continue

        try:
            events = await _download_and_parse_blob(container_client, blob_name)
            if events:
                for i in range(0, len(events), _BATCH_SIZE):
                    batch = events[i : i + _BATCH_SIZE]
                    inserted = await worker.ingest_batch(
                        raw_events=batch,
                        source_file_path=f"azure://{blob_name}",
                    )
                    total_inserted += inserted

            blobs_processed += 1
            latest_blob = blob_name

            logger.info(
                "poll_azure_sources.blob_processed",
                container=container_url[:50],
                blob=blob_name,
                events=len(events),
            )
        except Exception:
            logger.exception(
                "poll_azure_sources.blob_failed",
                blob=blob_name,
            )

    # Update cursor position
    if latest_blob and latest_blob != last_file:
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
                    "last_file": latest_blob,
                    "events": total_inserted,
                    "ts": datetime.now(UTC),
                },
            )
            await db.commit()

    return blobs_processed, total_inserted


async def _download_and_parse_blob(
    container_client: Any,
    blob_name: str,
) -> list[dict[str, Any]]:
    """Download and parse a JSON or NDJSON blob from Azure Blob Storage.

    Supports .json, .ndjson, .json.gz, and .ndjson.gz files.
    Runs the blocking download in a thread to avoid blocking the event loop.
    """
    loop = asyncio.get_running_loop()

    def _download() -> bytes:
        blob_client = container_client.get_blob_client(blob_name)
        return blob_client.download_blob().readall()

    raw_bytes = await loop.run_in_executor(None, _download)

    if blob_name.endswith(".gz"):
        raw_bytes = gzip.decompress(raw_bytes)

    text_content = raw_bytes.decode("utf-8")

    events: list[dict[str, Any]] = []
    if blob_name.endswith((".ndjson", ".ndjson.gz")):
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
