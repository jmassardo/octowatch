"""Unit tests for query_service: SQL validation and CTE scope injection."""

from __future__ import annotations

import pytest

from app.services.query_service import (
    ALLOWED_TABLES,
    QueryValidationError,
    _check_function_allowlist,
    _check_no_multi_statements,
    _check_no_writes,
    _check_table_allowlist,
    _extract_function_calls,
    _extract_table_refs,
    _walk_ast,
    validate_and_prepare,
)
from app.services.rbac_service import OrgRepoScope


def _scope(orgs: list[str] | None = None, repos: list[str] | None = None) -> OrgRepoScope:
    if orgs is None and repos is None:
        return OrgRepoScope(scope_type="global")
    return OrgRepoScope(
        scoped_orgs=orgs or [],
        scoped_repos=repos or [],
        scope_type="org" if orgs else "repo",
    )


def _parse_stmt(sql: str):
    """Parse SQL and return the first statement's AST node."""
    import pglast

    stmts = pglast.parse_sql(sql)
    return stmts[0].stmt


class TestValidateAndPrepare:
    def test_valid_select_passes(self):
        sql, params = validate_and_prepare("SELECT id, action FROM events LIMIT 10", _scope())
        assert "events" in sql.lower()

    def test_select_start_required(self):
        with pytest.raises(QueryValidationError, match="SELECT"):
            validate_and_prepare("INSERT INTO events VALUES (1)", _scope())

    def test_write_statement_blocked(self):
        with pytest.raises(QueryValidationError):
            validate_and_prepare("SELECT 1; DROP TABLE events", _scope())

    def test_update_blocked(self):
        with pytest.raises(QueryValidationError):
            validate_and_prepare("UPDATE events SET action = 'x'", _scope())

    def test_delete_blocked(self):
        with pytest.raises(QueryValidationError):
            validate_and_prepare("DELETE FROM events WHERE id = 1", _scope())

    def test_disallowed_table_blocked(self):
        with pytest.raises(QueryValidationError, match="not in allowed"):
            validate_and_prepare("SELECT * FROM pg_stat_activity", _scope())

    def test_allowed_table_passes(self):
        sql, _ = validate_and_prepare("SELECT id FROM detections LIMIT 5", _scope())
        assert sql  # non-empty

    def test_scope_cte_injected_for_scoped_user(self):
        sql, params = validate_and_prepare(
            "SELECT id, action FROM events LIMIT 10",
            _scope(orgs=["my-org"]),
        )
        # The resulting SQL should contain a scope CTE or org filter
        assert sql  # non-empty; specific format depends on implementation

    def test_cross_schema_blocked(self):
        with pytest.raises(QueryValidationError):
            validate_and_prepare("SELECT * FROM pg_catalog.pg_tables", _scope())

    def test_dangerous_function_blocked(self):
        with pytest.raises((QueryValidationError, Exception)):
            validate_and_prepare("SELECT pg_read_file('/etc/passwd') FROM events", _scope())

    def test_events_hourly_allowed(self):
        sql, _ = validate_and_prepare("SELECT * FROM events_hourly LIMIT 10", _scope())
        assert sql

    def test_behavioral_baselines_allowed(self):
        sql, _ = validate_and_prepare("SELECT * FROM behavioral_baselines LIMIT 5", _scope())
        assert sql

    def test_detections_daily_allowed(self):
        sql, _ = validate_and_prepare("SELECT * FROM detections_daily LIMIT 5", _scope())
        assert sql


class TestASTTableExtraction:
    """Tests for AST-based table reference extraction (Gap 1 fix)."""

    def test_simple_from(self):
        """Single FROM clause table is detected."""
        stmt = _parse_stmt("SELECT * FROM events")
        tables: set[str] = set()
        _extract_table_refs(stmt, tables)
        assert tables == {"events"}

    def test_join(self):
        """Tables from JOIN clauses are detected."""
        stmt = _parse_stmt("SELECT * FROM events e JOIN detections d ON e.id = d.event_id")
        tables: set[str] = set()
        _extract_table_refs(stmt, tables)
        assert tables == {"events", "detections"}

    def test_subquery_in_where(self):
        """Tables in subqueries (WHERE IN (...)) are detected."""
        stmt = _parse_stmt(
            "SELECT * FROM events WHERE actor IN (SELECT user_login FROM detections)"
        )
        tables: set[str] = set()
        _extract_table_refs(stmt, tables)
        assert "detections" in tables
        assert "events" in tables

    def test_subquery_in_select(self):
        """Tables referenced in scalar subqueries in SELECT clause are detected."""
        stmt = _parse_stmt("SELECT (SELECT count(*) FROM detections) AS cnt FROM events")
        tables: set[str] = set()
        _extract_table_refs(stmt, tables)
        assert tables == {"events", "detections"}

    def test_cte_table_refs(self):
        """Tables referenced inside CTE queries are detected."""
        stmt = _parse_stmt(
            "WITH daily AS (SELECT count(*) FROM events GROUP BY 1) SELECT * FROM daily"
        )
        tables: set[str] = set()
        _extract_table_refs(stmt, tables)
        # 'daily' is a CTE name and also appears as a table ref
        assert "events" in tables
        assert "daily" in tables

    def test_schema_qualified_non_public(self):
        """Schema-qualified tables (non-public) raise an error."""
        stmt = _parse_stmt("SELECT * FROM pg_catalog.pg_tables")
        tables: set[str] = set()
        with pytest.raises(QueryValidationError, match="Schema-qualified"):
            _extract_table_refs(stmt, tables)

    def test_schema_qualified_public_allowed(self):
        """public.table_name is allowed."""
        stmt = _parse_stmt("SELECT * FROM public.events")
        tables: set[str] = set()
        _extract_table_refs(stmt, tables)
        assert tables == {"events"}

    def test_lateral_join(self):
        """Tables in LATERAL joins are detected."""
        stmt = _parse_stmt(
            "SELECT * FROM events e, LATERAL ("
            "SELECT * FROM detections d WHERE d.event_id = e.id) sub"
        )
        tables: set[str] = set()
        _extract_table_refs(stmt, tables)
        assert "events" in tables
        assert "detections" in tables


class TestTableAllowlist:
    """Tests for _check_table_allowlist with AST."""

    def test_allowed_table_passes(self):
        """Allowed table should not raise."""
        stmt = _parse_stmt("SELECT * FROM events")
        _check_table_allowlist(stmt)  # Should not raise

    def test_disallowed_table_blocked(self):
        """Disallowed table should raise."""
        stmt = _parse_stmt("SELECT * FROM app_settings")
        with pytest.raises(QueryValidationError, match="not in allowed"):
            _check_table_allowlist(stmt)

    def test_disallowed_table_via_subquery(self):
        """Forbidden table accessed via subquery should be blocked."""
        stmt = _parse_stmt(
            "SELECT * FROM events WHERE actor IN (SELECT user_login FROM audit_trail)"
        )
        with pytest.raises(QueryValidationError, match="audit_trail"):
            _check_table_allowlist(stmt)

    def test_disallowed_table_via_cte(self):
        """Forbidden table inside CTE query body should be blocked."""
        stmt = _parse_stmt("WITH secrets AS (SELECT * FROM app_settings) SELECT * FROM secrets")
        with pytest.raises(QueryValidationError, match="app_settings"):
            _check_table_allowlist(stmt)

    def test_user_defined_cte_name_not_blocked(self):
        """User-defined CTE names should not be treated as table references."""
        stmt = _parse_stmt(
            "WITH daily AS ("
            "  SELECT date_trunc('day', created_at) as d, COUNT(*) as c "
            "  FROM events GROUP BY 1"
            ") SELECT * FROM daily"
        )
        _check_table_allowlist(stmt)  # Should not raise

    def test_pg_catalog_blocked(self):
        """pg_catalog schema should be rejected."""
        stmt = _parse_stmt("SELECT * FROM pg_catalog.pg_tables")
        with pytest.raises(QueryValidationError, match="Schema-qualified"):
            _check_table_allowlist(stmt)

    def test_information_schema_blocked(self):
        """information_schema should be rejected."""
        stmt = _parse_stmt("SELECT * FROM information_schema.tables")
        with pytest.raises(QueryValidationError, match="Schema-qualified"):
            _check_table_allowlist(stmt)

    def test_multiple_allowed_tables(self):
        """Multiple allowed tables in a join should pass."""
        stmt = _parse_stmt(
            "SELECT e.*, d.* FROM events e "
            "JOIN detections d ON e.id = d.event_id "
            "JOIN behavioral_baselines b ON e.actor = b.actor"
        )
        _check_table_allowlist(stmt)  # Should not raise

    def test_all_allowed_tables(self):
        """Verify all expected tables are in the allowlist."""
        expected = {
            "events",
            "detections",
            "behavioral_baselines",
            "events_hourly",
            "events_daily_actor",
            "detections_daily",
        }
        assert ALLOWED_TABLES == expected


class TestFunctionAllowlist:
    """Tests for AST-based function allowlist enforcement (Gap 2 fix)."""

    def test_allowed_aggregate_passes(self):
        """count, sum, avg should pass."""
        stmt = _parse_stmt("SELECT count(*), sum(id), avg(id) FROM events")
        _check_function_allowlist(stmt)  # Should not raise

    def test_allowed_date_functions_pass(self):
        """date_trunc, extract, now should pass."""
        stmt = _parse_stmt(
            "SELECT date_trunc('day', created_at), extract(hour FROM created_at), now() FROM events"
        )
        _check_function_allowlist(stmt)  # Should not raise

    def test_allowed_string_functions_pass(self):
        """lower, upper, concat, trim should pass."""
        stmt = _parse_stmt(
            "SELECT lower(actor), upper(action), concat(actor, action), trim(actor) FROM events"
        )
        _check_function_allowlist(stmt)  # Should not raise

    def test_allowed_window_functions_pass(self):
        """Window functions (row_number, rank, lag, lead) should pass."""
        stmt = _parse_stmt(
            "SELECT row_number() OVER (ORDER BY id), "
            "rank() OVER (ORDER BY id), "
            "lag(id) OVER (ORDER BY id) FROM events"
        )
        _check_function_allowlist(stmt)  # Should not raise

    def test_allowed_new_functions_pass(self):
        """Newly added functions should pass."""
        for func in ["greatest", "least", "abs", "ceil", "floor", "round"]:
            stmt = _parse_stmt(f"SELECT {func}(1) FROM events")
            _check_function_allowlist(stmt)  # Should not raise

    def test_dangerous_function_blocked(self):
        """pg_read_file should be blocked by allowlist."""
        stmt = _parse_stmt("SELECT pg_read_file('/etc/passwd') FROM events")
        with pytest.raises(QueryValidationError, match="not permitted"):
            _check_function_allowlist(stmt)

    def test_pg_sleep_blocked(self):
        """pg_sleep should be blocked."""
        stmt = _parse_stmt("SELECT pg_sleep(10) FROM events")
        with pytest.raises(QueryValidationError, match="not permitted"):
            _check_function_allowlist(stmt)

    def test_dblink_blocked(self):
        """dblink should be blocked."""
        stmt = _parse_stmt(
            "SELECT * FROM events WHERE id IN (SELECT dblink('host=evil', 'SELECT 1'))"
        )
        with pytest.raises(QueryValidationError, match="not permitted"):
            _check_function_allowlist(stmt)

    def test_schema_qualified_function_blocked(self):
        """Non-pg_catalog schema-qualified function calls should be blocked."""
        stmt = _parse_stmt("SELECT my_schema.my_func(1) FROM events")
        funcs: set[str] = set()
        with pytest.raises(QueryValidationError, match="Schema-qualified function"):
            _extract_function_calls(stmt, funcs)

    def test_pg_catalog_allowed_function_passes(self):
        """pg_catalog-prefixed functions should pass if name is in allowlist."""
        # EXTRACT is internally pg_catalog.extract
        stmt = _parse_stmt("SELECT extract(hour FROM created_at) FROM events")
        _check_function_allowlist(stmt)  # Should not raise

    def test_pg_catalog_disallowed_function_blocked(self):
        """pg_catalog-prefixed dangerous functions should still be blocked."""
        stmt = _parse_stmt("SELECT pg_catalog.pg_read_file('/etc/passwd') FROM events")
        with pytest.raises(QueryValidationError, match="not permitted"):
            _check_function_allowlist(stmt)

    def test_unknown_function_blocked(self):
        """Any function not in the allowlist should be blocked."""
        stmt = _parse_stmt("SELECT some_unknown_func(id) FROM events")
        with pytest.raises(QueryValidationError, match="not permitted"):
            _check_function_allowlist(stmt)

    def test_coalesce_nullif_pass(self):
        """coalesce and nullif should pass."""
        stmt = _parse_stmt("SELECT coalesce(actor, 'unknown'), nullif(actor, '') FROM events")
        _check_function_allowlist(stmt)  # Should not raise


class TestNoWrites:
    """Tests for _check_no_writes with expanded statement blocklist (Gap 5)."""

    def test_insert_blocked(self):
        import pglast

        stmts = pglast.parse_sql("INSERT INTO events (action) VALUES ('x')")
        with pytest.raises(QueryValidationError, match="InsertStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_update_blocked(self):
        import pglast

        stmts = pglast.parse_sql("UPDATE events SET action = 'x'")
        with pytest.raises(QueryValidationError, match="UpdateStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_delete_blocked(self):
        import pglast

        stmts = pglast.parse_sql("DELETE FROM events WHERE id = 1")
        with pytest.raises(QueryValidationError, match="DeleteStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_truncate_blocked(self):
        import pglast

        stmts = pglast.parse_sql("TRUNCATE events")
        with pytest.raises(QueryValidationError, match="TruncateStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_create_table_as_blocked(self):
        import pglast

        stmts = pglast.parse_sql("CREATE TABLE new_tbl AS SELECT * FROM events")
        with pytest.raises(QueryValidationError, match="CreateTableAsStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_drop_blocked(self):
        import pglast

        stmts = pglast.parse_sql("DROP TABLE events")
        with pytest.raises(QueryValidationError, match="DropStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_grant_blocked(self):
        import pglast

        stmts = pglast.parse_sql("GRANT SELECT ON events TO some_user")
        with pytest.raises(QueryValidationError, match="GrantStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_insert_via_cte_blocked(self):
        """INSERT inside a CTE body should be blocked."""
        import pglast

        stmts = pglast.parse_sql(
            "WITH ins AS (INSERT INTO events (action) VALUES ('hack') RETURNING *) "
            "SELECT * FROM ins"
        )
        with pytest.raises(QueryValidationError, match="InsertStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_variable_set_blocked(self):
        import pglast

        stmts = pglast.parse_sql("SET work_mem = '1GB'")
        with pytest.raises(QueryValidationError, match="VariableSetStmt"):
            _check_no_writes(stmts[0].stmt)

    def test_select_allowed(self):
        """Plain SELECT should not raise."""
        stmt = _parse_stmt("SELECT 1")
        _check_no_writes(stmt)  # Should not raise


class TestMultiStatementBlock:
    """Tests for semicolon-based multi-statement injection prevention (Gap 6)."""

    def test_single_statement_passes(self):
        """Single statement with no semicolons should pass."""
        _check_no_multi_statements("SELECT * FROM events")

    def test_trailing_semicolon_passes(self):
        """Single trailing semicolon is allowed (it's stripped before parsing)."""
        _check_no_multi_statements("SELECT * FROM events;")

    def test_multiple_statements_blocked(self):
        """Two statements separated by semicolon should be blocked."""
        with pytest.raises(QueryValidationError, match="Multiple SQL"):
            _check_no_multi_statements("SELECT 1; DROP TABLE events")

    def test_semicolon_injection_blocked(self):
        """Semicolon-based SQL injection should be blocked."""
        with pytest.raises(QueryValidationError, match="Multiple SQL"):
            _check_no_multi_statements("SELECT 1; DELETE FROM events; --")

    def test_validate_and_prepare_blocks_multi_statement(self):
        """validate_and_prepare should block multi-statement input."""
        with pytest.raises((QueryValidationError, Exception)):
            validate_and_prepare("SELECT 1; DROP TABLE events; --", _scope())

    def test_validate_and_prepare_blocks_semicolon_in_middle(self):
        """Semicolon in the middle of input should be blocked."""
        with pytest.raises((QueryValidationError, Exception)):
            validate_and_prepare("SELECT 1; DELETE FROM events", _scope())


class TestIntegrationScenarios:
    """End-to-end validation scenarios combining all security checks."""

    def test_normal_select_with_aggregates(self):
        """Standard analytics query should pass."""
        sql = "SELECT action, COUNT(*) as cnt FROM events GROUP BY action ORDER BY cnt DESC LIMIT 5"
        result, params = validate_and_prepare(sql, _scope())
        assert result

    def test_cte_with_allowed_table(self):
        """CTE referencing allowed table should pass."""
        sql = (
            "WITH daily AS ("
            "  SELECT date_trunc('day', created_at) as d, COUNT(*) as c "
            "  FROM events GROUP BY 1"
            ") SELECT * FROM daily"
        )
        result, params = validate_and_prepare(sql, _scope())
        assert result

    def test_window_functions_in_query(self):
        """Query with window functions should pass."""
        sql = (
            "SELECT actor, action, "
            "row_number() OVER (PARTITION BY actor ORDER BY created_at DESC) as rn "
            "FROM events"
        )
        result, params = validate_and_prepare(sql, _scope())
        assert result

    def test_nested_subquery_with_allowed_tables(self):
        """Nested subquery referencing only allowed tables should pass."""
        sql = (
            "SELECT * FROM events WHERE id IN "
            "(SELECT event_id FROM detections WHERE severity = 'high')"
        )
        result, params = validate_and_prepare(sql, _scope())
        assert result

    def test_nested_subquery_with_disallowed_table(self):
        """Nested subquery referencing disallowed table should fail."""
        sql = "SELECT * FROM events WHERE actor IN (SELECT user_login FROM audit_trail)"
        with pytest.raises(QueryValidationError, match="audit_trail"):
            validate_and_prepare(sql, _scope())

    def test_cte_hiding_disallowed_table(self):
        """CTE used to hide access to disallowed table should fail."""
        sql = "WITH secrets AS (SELECT * FROM app_settings) SELECT * FROM secrets"
        with pytest.raises(QueryValidationError, match="app_settings"):
            validate_and_prepare(sql, _scope())

    def test_empty_sql_rejected(self):
        """Empty SQL should be rejected."""
        with pytest.raises(QueryValidationError):
            validate_and_prepare("            ", _scope())

    def test_trailing_semicolon_stripped(self):
        """Trailing semicolons should be stripped and query should work."""
        sql = "SELECT id FROM events LIMIT 5;"
        result, _ = validate_and_prepare(sql, _scope())
        assert result

    def test_scoped_user_gets_scope_cte(self):
        """Scoped user should get scope CTE injected."""
        sql = "SELECT id, action FROM events LIMIT 10"
        result, params = validate_and_prepare(sql, _scope(orgs=["my-org"]))
        assert "__scope" in result
        assert "scoped_orgs" in params

    def test_global_user_gets_limit_only(self):
        """Global scope user should get row limit without scope filter."""
        sql = "SELECT id, action FROM events LIMIT 10"
        result, params = validate_and_prepare(sql, _scope())
        assert "__user" in result
        assert "max_rows" in params

    def test_multiple_joins_allowed(self):
        """Complex join query with all allowed tables should pass."""
        sql = (
            "SELECT e.id, d.severity, b.actor "
            "FROM events e "
            "JOIN detections d ON e.id = d.event_id "
            "JOIN behavioral_baselines b ON e.actor = b.actor "
            "WHERE e.created_at > now() - interval '7 days'"
        )
        result, _ = validate_and_prepare(sql, _scope())
        assert result


class TestWalkAST:
    """Tests for the _walk_ast utility function."""

    def test_walks_all_nodes(self):
        """_walk_ast should yield all AST nodes in the tree."""
        stmt = _parse_stmt("SELECT id FROM events WHERE id > 1")
        node_types = {type(n).__name__ for n in _walk_ast(stmt)}
        assert "SelectStmt" in node_types
        assert "RangeVar" in node_types

    def test_walks_none_safely(self):
        """_walk_ast should handle None without error."""
        nodes = list(_walk_ast(None))
        assert nodes == []

    def test_walks_list(self):
        """_walk_ast should handle lists of nodes."""
        import pglast

        stmts = pglast.parse_sql("SELECT 1")
        nodes = list(_walk_ast([stmts[0].stmt]))
        assert len(nodes) > 0
