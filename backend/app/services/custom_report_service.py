"""Custom report execution service.

Translates user-defined custom report definitions into SQL queries
against the events table and returns structured results.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Allowed data source → table/view mapping
_DATA_SOURCE_TABLES: dict[str, str] = {
    "events": "events",
    "detections": "detections",
    "posture": "code_scanning_alerts",
    "copilot": "events",
    "workflows": "workflow_scan_activities",
    "users": "events",
}

# Field allowlists per data source (used for column selection and grouping)
_ALLOWED_FIELDS: dict[str, set[str]] = {
    "events": {
        "action",
        "actor",
        "actor_id",
        "org",
        "repo",
        "created_at",
        "country",
        "actor_ip",
    },
    "detections": {
        "title",
        "severity",
        "status",
        "actor",
        "org",
        "repo",
        "created_at",
        "rule_id",
    },
    "posture": {
        "rule_id",
        "severity",
        "state",
        "tool_name",
        "created_at",
    },
    "copilot": {
        "action",
        "actor",
        "org",
        "created_at",
    },
    "workflows": {
        "org",
        "repo",
        "workflow_path",
        "status",
        "started_at",
        "findings_count",
    },
    "users": {
        "actor",
        "org",
        "action",
        "created_at",
    },
}

# Data source specific WHERE clauses for scoping
_DATA_SOURCE_SCOPES: dict[str, str] = {
    "copilot": "AND action LIKE 'copilot%%'",
    "users": "AND actor IS NOT NULL",
}


def _validate_field(field: str, data_source: str) -> bool:
    """Validate that a field is allowed for the given data source."""
    allowed = _ALLOWED_FIELDS.get(data_source, set())
    return field in allowed


def _get_timestamp_column(data_source: str) -> str:
    """Return the timestamp column name for a data source."""
    if data_source == "workflows":
        return "started_at"
    return "created_at"


async def run_custom_report(
    session: AsyncSession,
    *,
    data_sources: list[str],
    columns: list[dict[str, Any]],
    filters: list[dict[str, Any]],
    grouping: dict[str, Any],
    window_days: int = 30,
    start_date: str | None = None,
    end_date: str | None = None,
    org: str | None = None,
    granularity: str = "daily",
) -> list[dict[str, Any]]:
    """Execute a custom report query and return results.

    Builds a safe parameterised query from the report definition.  Only
    allowlisted fields and operators are accepted to prevent injection.
    """
    if not data_sources:
        return []

    primary_source = data_sources[0]
    table = _DATA_SOURCE_TABLES.get(primary_source)
    if table is None:
        logger.warning("custom_report.unknown_source", source=primary_source)
        return []

    ts_col = _get_timestamp_column(primary_source)

    # Resolve time window
    now = datetime.now(UTC)
    if end_date:
        end_dt = datetime.fromisoformat(end_date)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=UTC)
    else:
        end_dt = now

    if start_date:
        start_dt = datetime.fromisoformat(start_date)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=UTC)
    else:
        start_dt = end_dt - timedelta(days=window_days)

    # Build SELECT columns
    select_fields: list[str] = []
    if columns:
        for col in columns:
            field = col.get("field", "")
            if _validate_field(field, primary_source):
                select_fields.append(field)

    # If no valid columns specified, use a sensible default set
    if not select_fields:
        default_fields = sorted(_ALLOWED_FIELDS.get(primary_source, set()))
        select_fields = default_fields[:6] if default_fields else ["*"]

    # Build WHERE clauses
    where_parts: list[str] = [f"{ts_col} >= :start_dt", f"{ts_col} <= :end_dt"]
    params: dict[str, Any] = {"start_dt": start_dt, "end_dt": end_dt}

    if org:
        where_parts.append("org = :org")
        params["org"] = org

    # Data source scope
    scope_clause = _DATA_SOURCE_SCOPES.get(primary_source, "")

    # Apply filters with parameterised values
    _OPERATOR_MAP = {
        "eq": "=",
        "neq": "!=",
        "gt": ">",
        "gte": ">=",
        "lt": "<",
        "lte": "<=",
        "contains": "LIKE",
    }

    for i, filt in enumerate(filters):
        field = filt.get("field", "")
        operator = filt.get("operator", "eq")
        value = filt.get("value")

        if not _validate_field(field, primary_source):
            continue

        param_name = f"filt_{i}"

        if operator == "in" and isinstance(value, list):
            # Use ANY(array) for IN-style filtering
            where_parts.append(f"{field} = ANY(:filt_{i})")
            params[param_name] = value
        elif operator == "contains":
            where_parts.append(f"{field} LIKE :filt_{i}")
            params[param_name] = f"%{value}%"
        else:
            sql_op = _OPERATOR_MAP.get(operator, "=")
            where_parts.append(f"{field} {sql_op} :{param_name}")
            params[param_name] = value

    where_clause = " AND ".join(where_parts)

    # Build GROUP BY
    group_by_field = grouping.get("group_by") if grouping else None
    time_bucket = grouping.get("time_bucket") if grouping else None

    if group_by_field and _validate_field(group_by_field, primary_source):
        # Aggregated query
        interval_map = {
            "hourly": timedelta(hours=1),
            "daily": timedelta(days=1),
            "weekly": timedelta(days=7),
            "monthly": timedelta(days=30),
        }
        interval = interval_map.get(time_bucket or granularity, timedelta(days=1))
        params["bucket_interval"] = interval

        query = f"""
            SELECT
                time_bucket(:bucket_interval, {ts_col}) AS bucket,
                {group_by_field},
                COUNT(*) AS count
            FROM {table}
            WHERE {where_clause}
            {scope_clause}
            GROUP BY 1, 2
            ORDER BY 1 ASC, 3 DESC
            LIMIT 10000
        """
    elif time_bucket:
        interval_map = {
            "hourly": timedelta(hours=1),
            "daily": timedelta(days=1),
            "weekly": timedelta(days=7),
            "monthly": timedelta(days=30),
        }
        interval = interval_map.get(time_bucket, timedelta(days=1))
        params["bucket_interval"] = interval

        query = f"""
            SELECT
                time_bucket(:bucket_interval, {ts_col}) AS bucket,
                COUNT(*) AS count
            FROM {table}
            WHERE {where_clause}
            {scope_clause}
            GROUP BY 1
            ORDER BY 1 ASC
            LIMIT 10000
        """
    else:
        # Non-aggregated query — return individual rows
        select_clause = ", ".join(select_fields)
        query = f"""
            SELECT {select_clause}
            FROM {table}
            WHERE {where_clause}
            {scope_clause}
            ORDER BY {ts_col} DESC
            LIMIT 10000
        """

    logger.info(
        "custom_report.execute",
        data_source=primary_source,
        table=table,
        filter_count=len(filters),
    )

    result = await session.execute(text(query), params)
    rows = result.fetchall()

    # Convert rows to dicts
    if not rows:
        return []

    col_names = list(result.keys())
    return [{col_names[i]: _serialize_value(row[i]) for i in range(len(col_names))} for row in rows]


def _serialize_value(value: Any) -> Any:
    """Serialize a database value to JSON-safe form."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value
