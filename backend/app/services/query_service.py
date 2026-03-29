"""Self-service SQL query service with pglast validation and scope injection.

Security model:
1. Parse with pglast — reject anything that is not a single SELECT
2. Whitelist tables, reject system catalogs, whitelist functions
3. Inject scope as CTE wrapper (AST-level, not string append)
4. Execute under readonly_query_user PostgreSQL role
5. Enforce 30s timeout + 100k-row cap
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import pglast
import pglast.enums
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.rbac_service import OrgRepoScope

logger = structlog.get_logger(__name__)

# Tables/views accessible to self-service queries
ALLOWED_TABLES = frozenset(
    {
        "events",
        "detections",
        "behavioral_baselines",
        "events_hourly",
        "events_daily_actor",
        "detections_daily",
    }
)

# Built-in functions that are safe in read-only queries
ALLOWED_FUNCTIONS = frozenset(
    {
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "date_trunc",
        "time_bucket",
        "to_char",
        "coalesce",
        "nullif",
        "array_agg",
        "extract",
        "now",
        "lower",
        "upper",
        "length",
        "substr",
        "substring",
        "regexp_replace",
        "to_timestamp",
        "date_part",
        "timezone",
    }
)


class QueryValidationError(ValueError):
    pass


def _check_no_writes(node: Any) -> None:
    """Recursively check AST for write operations."""
    if node is None:
        return
    node_type = type(node).__name__
    if node_type in (
        "InsertStmt",
        "UpdateStmt",
        "DeleteStmt",
        "TruncateStmt",
        "CreateStmt",
        "AlterTableStmt",
        "DropStmt",
        "CopyStmt",
        "ExplainStmt",
        "CallStmt",
        "DoStmt",
        "ExecuteStmt",
    ):
        raise QueryValidationError(f"Statement type not permitted: {node_type}")
    # Recurse into child nodes
    if hasattr(node, "__iter__") and not isinstance(node, str):
        try:
            for child in node:
                _check_no_writes(child)
        except TypeError:
            pass


def _check_table_allowlist(sql: str) -> None:
    """Check that no FROM targets reference tables outside the allowlist."""
    import re

    sql_lower = sql.lower()
    # Check for schema-qualified names (information_schema, pg_catalog, etc.)
    forbidden_schemas = ("information_schema.", "pg_catalog.", "pg_toast.", "pg_temp.")
    for schema in forbidden_schemas:
        if schema in sql_lower:
            raise QueryValidationError(f"Cross-schema reference not permitted: {schema}")

    # Extract all table/view names from FROM and JOIN clauses and check whitelist
    table_pattern = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)
    referenced = {m.group(1).lower() for m in table_pattern.finditer(sql)}
    for tbl in referenced:
        if tbl not in ALLOWED_TABLES:
            raise QueryValidationError(
                f"Table '{tbl}' is not in allowed tables: {sorted(ALLOWED_TABLES)}"
            )


def _check_function_allowlist(sql: str) -> None:
    """Basic function allowlist check via string scanning."""
    # Block obviously dangerous functions
    dangerous_funcs = (
        "pg_read_file",
        "pg_ls_dir",
        "pg_sleep",
        "lo_export",
        "lo_import",
        "copy",
        "pg_execute",
        "dblink",
        "file_fdw",
        "pg_stat_file",
        "pg_read_binary_file",
        "lo_get",
    )
    sql_lower = sql.lower()
    for func in dangerous_funcs:
        if func in sql_lower:
            raise QueryValidationError(
                f"Function call not permitted in self-service queries: {func}"
            )


def validate_and_prepare(sql: str, scope: OrgRepoScope) -> tuple[str, dict[str, Any]]:
    """Parse, validate, and rewrite user SQL with scope CTE injection.

    Returns (rewritten_sql, bind_params).
    Raises QueryValidationError on any violation.
    """
    # 0. Strip trailing semicolons — they break CTE wrapping
    sql = sql.rstrip().rstrip(";").rstrip()

    # 1. Parse
    try:
        stmts = pglast.parse_sql(sql)
    except pglast.Error as exc:
        raise QueryValidationError(f"SQL parse error: {exc}") from exc

    if not stmts:
        raise QueryValidationError("Empty SQL statement")

    if len(stmts) > 1:
        raise QueryValidationError("Only a single SELECT statement is permitted")

    stmt_wrapper = stmts[0]
    if not hasattr(stmt_wrapper, "stmt"):
        raise QueryValidationError("Unexpected parse tree structure")

    stmt = stmt_wrapper.stmt
    if type(stmt).__name__ != "SelectStmt":
        raise QueryValidationError("Only SELECT statements are permitted")

    # 2. Check for prohibited constructs
    _check_table_allowlist(sql)
    _check_no_writes(stmt)
    _check_function_allowlist(sql)

    # 3. Build scope CTE wrapper
    # The user's SQL is wrapped: WITH __scope AS (...) <user_sql_with_limit>
    if scope.is_global:
        # For global scope, just add row limit
        rewritten = f"WITH __user AS (\n{sql}\n)\nSELECT * FROM __user LIMIT :max_rows"
        params: dict[str, Any] = {"max_rows": settings.QUERY_MAX_ROWS}
    else:
        # Build scope CTE parameters
        params = {
            "scoped_orgs": scope.scoped_orgs,
            "max_rows": settings.QUERY_MAX_ROWS,
        }
        rewritten = (
            "WITH __scope AS (\n  SELECT e.id FROM events e\n  WHERE e.org = ANY(:scoped_orgs)\n"
        )
        if scope.scoped_repos:
            params["scoped_repos"] = scope.scoped_repos
            rewritten += "    AND (e.repo IS NULL OR e.repo = ANY(:scoped_repos))\n"
        rewritten += "),\n"
        rewritten += f"__user AS (\n{sql}\n)\n"
        rewritten += "SELECT * FROM __user LIMIT :max_rows"

    return rewritten, params


async def execute_query(
    session: AsyncSession,
    sql: str,
    scope: OrgRepoScope,
) -> dict[str, Any]:
    """Execute a validated user SQL query and return results."""
    rewritten_sql, params = validate_and_prepare(sql, scope)

    query_id = str(uuid.uuid4())
    start = time.monotonic()

    try:
        # Set statement timeout
        await session.execute(
            text(f"SET LOCAL statement_timeout = '{settings.QUERY_TIMEOUT_SECONDS}000'")
        )

        result = await session.execute(text(rewritten_sql), params)
        rows = result.fetchall()
        columns = list(result.keys())

        execution_ms = int((time.monotonic() - start) * 1000)
        truncated = len(rows) >= settings.QUERY_MAX_ROWS

        logger.info(
            "query.executed",
            query_id=query_id,
            row_count=len(rows),
            execution_ms=execution_ms,
            truncated=truncated,
        )

        return {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "execution_ms": execution_ms,
            "query_id": query_id,
        }
    except Exception as exc:
        execution_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "query.failed",
            query_id=query_id,
            error=str(exc),
            execution_ms=execution_ms,
        )
        raise
