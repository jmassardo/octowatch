"""Archive service: export expired data to S3/Azure Blob before deletion.

Archives are written as compressed NDJSON files organised by table and date:
``archive/{table}/{year}/{month}/data.ndjson.gz``

The service also supports restoring archived data from an S3 path back into
the database.
"""

from __future__ import annotations

import gzip
import io
import json
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retention_service import RETENTION_TABLES

logger = structlog.get_logger(__name__)


def _archive_key(table_name: str, cutoff: datetime) -> str:
    """Build the S3 object key for an archive file."""
    return f"archive/{table_name}/{cutoff.year}/{cutoff.month:02d}/data.ndjson.gz"


# ── Archival ─────────────────────────────────────────────────────────────────


async def archive_rows(
    db: AsyncSession,
    table_name: str,
    cutoff: datetime,
    *,
    s3_client: Any,
    bucket: str,
) -> str:
    """Export rows older than *cutoff* as compressed NDJSON and upload to S3.

    Returns the S3 object key of the uploaded archive.
    """
    meta = RETENTION_TABLES.get(table_name)
    if meta is None:
        raise ValueError(f"Unknown archive table: {table_name}")

    time_col = meta["time_col"]

    # Stream rows via raw SQL to avoid ORM overhead on bulk reads
    result = await db.execute(
        text(f"SELECT row_to_json(t) FROM {table_name} t WHERE {time_col} < :cutoff"),  # noqa: S608
        {"cutoff": cutoff},
    )
    rows = result.fetchall()

    if not rows:
        logger.info("archive.no_rows", table=table_name, cutoff=cutoff.isoformat())
        return ""

    # Build NDJSON in memory then gzip-compress
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for (row_json,) in rows:
            line = json.dumps(row_json, default=str) + "\n"
            gz.write(line.encode("utf-8"))

    buf.seek(0)
    key = _archive_key(table_name, cutoff)

    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=buf.getvalue(),
        ContentType="application/x-ndjson",
        ContentEncoding="gzip",
    )

    logger.info(
        "archive.uploaded",
        table=table_name,
        key=key,
        rows=len(rows),
        size_bytes=buf.getbuffer().nbytes,
    )
    return key


# ── Restore ──────────────────────────────────────────────────────────────────

# Column-name allow-list per table. Only these columns are written on restore.
_RESTORE_COLUMNS: dict[str, list[str]] = {
    "events": [
        "id",
        "created_at",
        "document_id",
        "ingested_at",
        "action",
        "actor",
        "actor_id",
        "actor_is_bot",
        "org",
        "org_id",
        "repo",
        "repo_id",
        "business",
        "business_id",
        "source_ip",
        "user_agent",
        "geo_country_code",
        "geo_city",
        "geo_latitude",
        "geo_longitude",
        "geo_is_proxy",
        "data",
        "ingestion_source",
        "source_file_path",
    ],
    "audit_trail": [
        "id",
        "timestamp",
        "user_login",
        "user_github_id",
        "ip_address",
        "user_agent",
        "action_type",
        "resource_type",
        "resource_id",
        "parameters",
        "outcome",
        "error_detail",
    ],
    "detections": [
        "id",
        "rule_id",
        "rule_version",
        "triggered_at",
        "window_start",
        "window_end",
        "severity",
        "confidence",
        "confidence_score",
        "status",
        "assigned_to",
        "title",
        "description",
        "actor",
        "org",
        "repo",
        "source_ip",
        "event_ids",
        "context_data",
        "resolved_at",
        "resolved_by",
        "resolution_note",
        "suppressed_by",
        "created_at",
        "updated_at",
    ],
    "event_raw_payloads": [
        "id",
        "document_id",
        "source_file",
        "raw_json",
        "event_id",
        "ingested_at",
    ],
    "event_dedup": ["document_id", "event_id", "created_at", "ingested_at"],
    "enterprise_sync_log_entries": [
        "id",
        "run_id",
        "seq",
        "timestamp",
        "level",
        "message",
        "entity_type",
        "org",
        "details",
    ],
    "behavioral_baselines": [
        "id",
        "baseline_type",
        "scope_key",
        "metric_name",
        "window_start",
        "window_end",
        "mean",
        "stddev",
        "p95",
        "p99",
        "sample_count",
        "computed_at",
    ],
    "system_health_events": [
        "id",
        "occurred_at",
        "org",
        "signal_type",
        "severity",
        "detail",
        "resolved_at",
    ],
}


async def restore_archive(
    db: AsyncSession,
    archive_path: str,
    *,
    s3_client: Any,
    bucket: str,
) -> int:
    """Download an NDJSON.gz archive from S3 and re-import rows.

    Rows that conflict on primary key are skipped (``ON CONFLICT DO NOTHING``).
    Returns the count of restored rows.
    """
    # Determine table from path: archive/{table}/...
    parts = archive_path.strip("/").split("/")
    if len(parts) < 2 or parts[0] != "archive":
        raise ValueError(f"Invalid archive path: {archive_path}")
    table_name = parts[1]
    if table_name not in RETENTION_TABLES:
        raise ValueError(f"Unknown table in archive path: {table_name}")

    columns = _RESTORE_COLUMNS.get(table_name)
    if columns is None:
        raise ValueError(f"Restore not supported for table: {table_name}")

    # Download from S3
    resp = s3_client.get_object(Bucket=bucket, Key=archive_path)
    compressed = resp["Body"].read()

    # Decompress and parse NDJSON
    raw = gzip.decompress(compressed)
    lines = raw.decode("utf-8").strip().split("\n")

    restored = 0
    for line in lines:
        if not line.strip():
            continue
        record = json.loads(line)

        # Filter to allowed columns only
        values = {c: record[c] for c in columns if c in record}
        if not values:
            continue

        col_names = ", ".join(values.keys())
        placeholders = ", ".join(f":{k}" for k in values.keys())

        # Serialise complex types for PostgreSQL
        for k, v in values.items():
            if isinstance(v, (dict, list)):
                values[k] = json.dumps(v)

        await db.execute(
            text(
                f"INSERT INTO {table_name} ({col_names}) "  # noqa: S608
                f"VALUES ({placeholders}) "
                "ON CONFLICT DO NOTHING"
            ),
            values,
        )
        restored += 1

    await db.commit()
    logger.info("archive.restored", table=table_name, path=archive_path, rows=restored)
    return restored


# ── List archives ────────────────────────────────────────────────────────────


def list_archives(
    *,
    s3_client: Any,
    bucket: str,
    table_name: str | None = None,
) -> list[dict[str, Any]]:
    """List archive objects in the bucket, optionally filtered by table."""
    prefix = f"archive/{table_name}/" if table_name else "archive/"

    paginator = s3_client.get_paginator("list_objects_v2")
    archives: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            archives.append(
                {
                    "key": obj["Key"],
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat()
                    if hasattr(obj["LastModified"], "isoformat")
                    else str(obj["LastModified"]),
                }
            )
    return archives


# ── S3 client factory ────────────────────────────────────────────────────────


def get_s3_client() -> Any:
    """Create a boto3 S3 client using environment-based configuration."""
    import os

    import boto3

    endpoint_url = os.environ.get("AWS_S3_ENDPOINT_URL")
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def get_archive_bucket() -> str:
    """Return the configured archive bucket name."""
    import os

    return os.environ.get("ARCHIVE_BUCKET", "audit-logs")
