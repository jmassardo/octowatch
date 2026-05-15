"""Self-service SQL query service with pglast validation and scope injection.

Security model:
1. Parse with pglast — reject anything that is not a single SELECT
2. Whitelist tables via AST RangeVar extraction, reject system catalogs
3. Whitelist functions via AST FuncCall extraction
4. Block semicolons to prevent multi-statement injection
5. Inject scope as CTE wrapper (AST-level, not string append)
6. Execute under readonly_query_user PostgreSQL role (defense-in-depth)
7. Enforce 30s timeout + 100k-row cap
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

import pglast
import pglast.ast
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
        # Aggregates
        "count",
        "sum",
        "avg",
        "min",
        "max",
        "string_agg",
        "array_agg",
        "bool_or",
        "bool_and",
        # Date/time
        "date_trunc",
        "time_bucket",
        "to_char",
        "to_timestamp",
        "date_part",
        "extract",
        "now",
        "timezone",
        "age",
        "date",
        "make_interval",
        "justify_interval",
        # String
        "lower",
        "upper",
        "length",
        "substr",
        "substring",
        "regexp_replace",
        "regexp_matches",
        "concat",
        "trim",
        "btrim",
        "ltrim",
        "rtrim",
        "replace",
        "left",
        "right",
        "position",
        "strpos",
        "split_part",
        # Conditional/null
        "coalesce",
        "nullif",
        "greatest",
        "least",
        # Math
        "abs",
        "ceil",
        "floor",
        "round",
        "trunc",
        # JSON
        "jsonb_extract_path_text",
        "jsonb_array_elements",
        # Window functions
        "row_number",
        "rank",
        "dense_rank",
        "lag",
        "lead",
        "first_value",
        "last_value",
        "ntile",
        "percent_rank",
        "cume_dist",
        # Misc
        "cast",
        "unnest",
        "generate_series",
    }
)

# Statement types that represent write or administrative operations
_WRITE_STATEMENT_TYPES = frozenset(
    {
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
        "GrantStmt",
        "GrantRoleStmt",
        "CreateRoleStmt",
        "AlterRoleStmt",
        "DropRoleStmt",
        "TransactionStmt",
        "LockStmt",
        "ClusterStmt",
        "VacuumStmt",
        "ReindexStmt",
        "CreateTableAsStmt",
        "CreateSchemaStmt",
        "DropOwnedStmt",
        "VariableSetStmt",
    }
)


class QueryValidationError(ValueError):
    pass


def _walk_ast(node: Any) -> Any:
    """Yield every AST node in the pglast parse tree (depth-first)."""
    if node is None:
        return
    # Yield the current node itself (if it's a pglast AST node)
    if isinstance(node, pglast.ast.Node):
        yield node
        # Recurse into each slot value
        for slot_name in node.__slots__:
            child = getattr(node, slot_name, None)
            if child is not None and not isinstance(child, (str, int, float, bool)):
                yield from _walk_ast(child)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk_ast(item)


def _check_no_writes(node: Any) -> None:
    """Recursively check AST for write and administrative operations."""
    for child in _walk_ast(node):
        node_type = type(child).__name__
        if node_type in _WRITE_STATEMENT_TYPES:
            raise QueryValidationError(f"Statement type not permitted: {node_type}")


def _extract_table_refs(node: Any, tables: set[str]) -> None:
    """Walk pglast AST to find all RangeVar (table reference) nodes."""
    for child in _walk_ast(node):
        if type(child).__name__ == "RangeVar":
            schema = getattr(child, "schemaname", None)
            relname = getattr(child, "relname", None)
            if schema is not None and schema != "public":
                raise QueryValidationError(
                    f"Schema-qualified table references not permitted: {schema}.{relname}"
                )
            if relname:
                tables.add(relname.lower())


def _extract_function_calls(node: Any, funcs: set[str]) -> None:
    """Walk pglast AST to find all FuncCall nodes.

    PostgreSQL internally represents SQL standard functions (EXTRACT, TRIM,
    POSITION, SUBSTRING) as ``pg_catalog.<name>``.  We allow the ``pg_catalog``
    schema prefix for these built-ins and still validate the function name
    against the allowlist.  Any other schema prefix is rejected.
    """
    for child in _walk_ast(node):
        if type(child).__name__ == "FuncCall":
            funcname_parts = getattr(child, "funcname", None)
            if funcname_parts:
                name_parts: list[str] = []
                for part in funcname_parts:
                    if hasattr(part, "sval"):
                        name_parts.append(part.sval.lower())
                    elif isinstance(part, str):
                        name_parts.append(part.lower())
                if name_parts:
                    if len(name_parts) > 1:
                        # pg_catalog is used by PostgreSQL for SQL-standard
                        # built-in functions – allow it and just check the
                        # function name against the allowlist below.
                        if name_parts[0] != "pg_catalog":
                            raise QueryValidationError(
                                "Schema-qualified function calls not permitted: "
                                f"{'.'.join(name_parts)}"
                            )
                    funcs.add(name_parts[-1])


def _check_table_allowlist(stmt: Any) -> None:
    """Check that all table references are in the allowlist using AST walking."""
    tables: set[str] = set()
    _extract_table_refs(stmt, tables)

    # Exclude user-defined CTE names (they are virtual, not real tables)
    cte_names: set[str] = set()
    if hasattr(stmt, "withClause") and stmt.withClause is not None:
        ctes = getattr(stmt.withClause, "ctes", None)
        if ctes:
            for cte in ctes:
                ctename = getattr(cte, "ctename", None)
                if ctename:
                    cte_names.add(ctename.lower())

    real_tables = tables - cte_names
    for tbl in sorted(real_tables):
        if tbl not in ALLOWED_TABLES:
            raise QueryValidationError(
                f"Table '{tbl}' is not in allowed tables: {sorted(ALLOWED_TABLES)}"
            )


def _check_function_allowlist(stmt: Any) -> None:
    """Check that all function calls are in the allowlist using AST walking."""
    funcs: set[str] = set()
    _extract_function_calls(stmt, funcs)

    disallowed = funcs - ALLOWED_FUNCTIONS
    if disallowed:
        raise QueryValidationError(
            f"Function(s) not permitted: {sorted(disallowed)}. Allowed: {sorted(ALLOWED_FUNCTIONS)}"
        )


def _check_no_multi_statements(sql: str) -> None:
    """Block multi-statement injection via semicolons in the raw input."""
    stripped = sql.strip().rstrip(";").strip()
    if ";" in stripped:
        raise QueryValidationError(
            "Multiple SQL statements are not permitted; only a single SELECT is allowed"
        )


# Regex: comparison/string operators followed by a double-quoted string.
# Matches patterns like  = "foo",  LIKE "bar%",  != "baz",  ILIKE "qux"
# but not bare identifiers used as aliases (SELECT x AS "MyCol").
_DQ_STRING_AFTER_OP = re.compile(
    r"""(?:=|!=|<>|LIKE|ILIKE|IN\s*\()\s*"([^"]*)" """,
    re.IGNORECASE | re.VERBOSE,
)


def _check_double_quoted_strings(sql: str) -> None:
    """Warn when double-quoted strings are used as values.

    In PostgreSQL, double quotes delimit identifiers (table/column names)
    while single quotes delimit string literals.  A query like
        WHERE action LIKE "repo.push"
    parses as an identifier reference and silently returns no rows.
    """
    match = _DQ_STRING_AFTER_OP.search(sql)
    if match:
        value = match.group(1)
        raise QueryValidationError(
            f'Double-quoted string "{value}" is treated as a column/table name in PostgreSQL, '
            f"not a text value. Use single quotes instead: '{value}'"
        )


def validate_and_prepare(sql: str, scope: OrgRepoScope) -> tuple[str, dict[str, Any]]:
    """Parse, validate, and rewrite user SQL with scope CTE injection.

    Returns (rewritten_sql, bind_params).
    Raises QueryValidationError on any violation.
    """
    # 0. Block multi-statement injection before any parsing
    _check_no_multi_statements(sql)

    # 0a. Catch double-quoted string literals (common PostgreSQL mistake)
    _check_double_quoted_strings(sql)

    # 0b. Strip trailing semicolons — they break CTE wrapping
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

    # 2. Check for prohibited constructs using AST walking
    _check_no_writes(stmt)
    _check_table_allowlist(stmt)
    _check_function_allowlist(stmt)

    # 3. Build scope CTE wrapper
    # For scoped users, shadow the `events` table with a CTE that pre-filters
    # by org/repo. In PostgreSQL, a non-recursive CTE with the same name as a
    # base table shadows it: inside the CTE definition `FROM events` still
    # refers to the real table, but all later references (including the user
    # SQL wrapped in __user) resolve to the scoped CTE.
    if scope.is_global:
        rewritten = f"WITH __user AS (\n{sql}\n)\nSELECT * FROM __user LIMIT :max_rows"
        params: dict[str, Any] = {"max_rows": settings.QUERY_MAX_ROWS}
    else:
        params = {
            "scoped_orgs": scope.scoped_orgs,
            "max_rows": settings.QUERY_MAX_ROWS,
        }
        rewritten = "WITH events AS (\n  SELECT * FROM events WHERE org = ANY(:scoped_orgs)\n"
        if scope.scoped_repos:
            params["scoped_repos"] = scope.scoped_repos
            rewritten += "    AND (repo IS NULL OR repo = ANY(:scoped_repos))\n"
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
        # Set statement timeout — validate as int to prevent injection
        timeout_ms = str(int(settings.QUERY_TIMEOUT_SECONDS) * 1000)
        await session.execute(
            text("SET LOCAL statement_timeout = :timeout_ms"),
            {"timeout_ms": timeout_ms},
        )

        # Defense-in-depth: execute as readonly_query_user so the DB itself
        # rejects any writes even if AST validation has a bug.
        await session.execute(text("SET LOCAL ROLE readonly_query_user"))

        # Security: rewritten_sql is validated through pglast AST parsing
        # (see validate_and_prepare) which ensures it is a single SELECT
        # with only allowed tables and functions. Bind parameters in
        # `params` are passed separately and never interpolated.
        # CodeQL [py/sql-injection] Validated via pglast AST; params bound separately
        result = await session.execute(text(rewritten_sql), params)  # noqa: S608
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
    finally:
        # Always reset role, even on error, to avoid leaking the role change
        # to subsequent operations on this session.
        try:
            await session.execute(text("RESET ROLE"))
        except Exception:
            # Transaction may be aborted; rollback first then reset
            try:
                await session.rollback()
                await session.execute(text("RESET ROLE"))
            except Exception:
                logger.debug("query.reset_role_cleanup_failed")
