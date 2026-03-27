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
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis


def parse_file(path: Path) -> list[dict[str, Any]]:
    """Read a .json.gz or .json file and return a list of event dicts."""
    if path.suffix == ".gz" or path.name.endswith(".json.gz"):
        opener = gzip.open(path, "rt", encoding="utf-8")
    else:
        opener = open(path, encoding="utf-8")  # noqa: SIM115

    with opener as fh:
        content = fh.read()

    events: list[dict[str, Any]] = []

    # Try NDJSON first (one JSON object per line)
    parse_errors = 0
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            parse_errors += 1

    # If NDJSON failed entirely, try JSON array format
    if not events and parse_errors > 0:
        try:
            parsed = json.loads(content)
            events = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError as exc:
            print(f"  ERROR: Could not parse {path.name}: {exc}", file=sys.stderr)

    return events


async def main(files: list[str]) -> None:
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.workers.ingestion.base import AbstractIngestWorker

    class LocalImportWorker(AbstractIngestWorker):
        ingestion_source = "minio"  # closest valid value per DB CHECK constraint

        async def run(self) -> None:
            pass  # not used for one-time import

    valkey = aioredis.from_url(settings.VALKEY_URL)
    worker = LocalImportWorker(
        valkey_client=valkey,
        db_session_factory=AsyncSessionLocal,
    )

    total_parsed = 0
    total_inserted = 0

    for path_str in files:
        path = Path(path_str)
        if not path.exists():
            print(f"  SKIP: {path} not found", file=sys.stderr)
            continue

        size_kb = path.stat().st_size / 1024
        print(f"\nParsing {path.name}  ({size_kb:.1f} KB)...")

        events = parse_file(path)
        if not events:
            print(f"  SKIP: no events parsed from {path.name}")
            continue

        print(f"  Parsed {len(events):,} events. Inserting...")
        total_parsed += len(events)

        inserted = await worker.ingest_batch(events, source_file_path=path.name)
        skipped = len(events) - inserted
        print(f"  ✓ {inserted:,} inserted  ({skipped:,} duplicates skipped)")
        total_inserted += inserted

    print(f"\n{'─'*50}")
    print(f"Total parsed:   {total_parsed:,}")
    print(f"Total inserted: {total_inserted:,}")
    print(f"Total skipped:  {total_parsed - total_inserted:,}")

    await valkey.aclose()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(sys.argv[1:]))
