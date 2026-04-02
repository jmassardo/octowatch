"""Azure Blob Storage ingest worker: polls a container for new audit log blobs."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from app.config import settings
from app.workers.ingestion.base import AbstractIngestWorker

logger = structlog.get_logger(__name__)


class AzureBlobIngestWorker(AbstractIngestWorker):
    """Periodically lists new blobs in an Azure Blob Storage container."""

    async def run(self) -> None:
        """Single poll cycle: list new blobs, ingest, advance cursor."""
        azure_cfg = settings.AZURE
        if not azure_cfg.AZURE_AUDIT_CONTAINER:
            logger.info("azure_worker.no_container_configured")
            return

        from azure.storage.blob import ContainerClient

        # The connection string is validated at startup (SSRF check in config.py)
        container_client = ContainerClient.from_connection_string(
            conn_str=azure_cfg.AZURE_STORAGE_CONNECTION_STRING,
            container_name=azure_cfg.AZURE_AUDIT_CONTAINER,
        )

        cursor = await self._load_cursor(source_type="azure_blob")
        total_inserted = 0

        try:
            blobs = await asyncio.to_thread(
                lambda: list(container_client.list_blobs(name_starts_with=""))
            )
        except Exception as exc:
            logger.error("azure_worker.list_failed", error=str(exc))
            return

        # Sort by last_modified to process in chronological order
        blobs.sort(key=lambda b: b.last_modified)

        for blob in blobs:
            blob_name = blob.name

            # Skip already-processed blobs using cursor (name-based ordering)
            if cursor and blob_name <= cursor:
                continue

            if not blob_name.endswith((".json", ".ndjson", ".jsonl", ".gz")):
                continue

            events = await self._download_and_parse_blob(container_client, blob_name)
            if events:
                inserted = await self.ingest_batch(events)
                total_inserted += inserted
                logger.info(
                    "azure_worker.ingested",
                    blob=blob_name,
                    inserted=inserted,
                )

            # Advance cursor
            await self._save_cursor(source_type="azure_blob", cursor_value=blob_name)

        if total_inserted:
            logger.info("azure_worker.poll_complete", inserted=total_inserted)

        await asyncio.to_thread(container_client.close)

    async def _download_and_parse_blob(
        self,
        container_client: Any,
        blob_name: str,
    ) -> list[dict[str, Any]]:
        """Download and parse an Azure blob (NDJSON or JSON array)."""
        import gzip

        try:
            blob_client = container_client.get_blob_client(blob_name)
            data = await asyncio.to_thread(lambda: blob_client.download_blob().readall())
        except Exception as exc:
            logger.error("azure_worker.download_failed", blob=blob_name, error=str(exc))
            return []

        if blob_name.endswith(".gz"):
            try:
                data = gzip.decompress(data)
            except Exception as exc:
                logger.warning("azure_worker.gunzip_failed", blob=blob_name, error=str(exc))
                return []

        content = data.decode("utf-8")
        events: list[dict[str, Any]] = []

        # Parse NDJSON
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

        # Fallback: JSON array
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
        """Persist the cursor value (upsert)."""
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
