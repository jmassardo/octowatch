#!/usr/bin/env python3
"""One-time import of local .json.gz (or .json) audit log files into the database.

Usage (from repo root):
    docker compose run --rm \
        -v /path/to/your/exports:/import:ro \
        api python import_local.py /import/file1.json.gz /import/file2.json.gz
"""

from __future__ import annotations

import asyncio
import gzip
import json
import sys
import time
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


def parse_file(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read a .json.gz or .json file and return a list of event dicts and parse error count."""
    if path.suffix == ".gz" or path.name.endswith(".json.gz"):
        opener = gzip.open(path, "rt", encoding="utf-8")
    else:
        opener = open(path, encoding="utf-8")  # noqa: SIM115

    with opener as fh:
        content = fh.read()

    events: list[dict[str, Any]] = []

    # Try NDJSON first (one JSON object per line)
    parse_errors = 0
    for line_number, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            parse_errors += 1
            logger.warning(
                "import_local.json_parse_error",
                file=path.name,
                line_number=line_number,
                error=str(exc),
                raw_line_preview=line[:200],
            )

    # If NDJSON failed entirely, try JSON array format
    if not events and parse_errors > 0:
        try:
            parsed = json.loads(content)
            events = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError as exc:
            logger.error(
                "import_local.file_parse_failed",
                file=path.name,
                error=str(exc),
            )

    return events, parse_errors


async def main(files: list[str]) -> None:
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.workers.ingestion.base import AbstractIngestWorker

    class LocalImportWorker(AbstractIngestWorker):
        ingestion_source = "hec"  # default source; subclasses override

        async def run(self) -> None:
            pass  # not used for one-time import

    valkey = aioredis.from_url(settings.VALKEY_URL)
    worker = LocalImportWorker(
        valkey_client=valkey,
        db_session_factory=AsyncSessionLocal,
    )

    total_parsed = 0
    total_inserted = 0
    total_parse_errors = 0
    source_files: list[str] = []
    start_time = time.monotonic()

    for path_str in files:
        path = Path(path_str)
        if not path.exists():
            logger.warning("import_local.file_not_found", file=str(path))
            continue

        size_kb = path.stat().st_size / 1024
        logger.info("import_local.parsing_file", file=path.name, size_kb=round(size_kb, 1))

        events, parse_errors = parse_file(path)
        total_parse_errors += parse_errors
        source_files.append(path.name)

        if not events:
            logger.warning("import_local.no_events_parsed", file=path.name)
            continue

        logger.info("import_local.inserting_events", file=path.name, event_count=len(events))
        total_parsed += len(events)

        inserted = await worker.ingest_batch(events, source_file_path=path.name)
        skipped = len(events) - inserted
        logger.info(
            "import_local.batch_complete",
            file=path.name,
            inserted=inserted,
            duplicates_skipped=skipped,
        )
        total_inserted += inserted

    duration = time.monotonic() - start_time
    logger.info(
        "import_local.summary",
        records_imported=total_inserted,
        records_parsed=total_parsed,
        records_skipped=total_parsed - total_inserted,
        parse_errors=total_parse_errors,
        source_file=source_files,
        duration_seconds=round(duration, 2),
    )

    await valkey.aclose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.info("import_local.usage", message=__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1:]))
