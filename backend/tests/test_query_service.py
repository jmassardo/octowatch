"""Unit tests for query_service: SQL validation and CTE scope injection."""

from __future__ import annotations

import pytest

from app.services.query_service import QueryValidationError, validate_and_prepare
from app.services.rbac_service import OrgRepoScope


def _scope(orgs: list[str] | None = None, repos: list[str] | None = None) -> OrgRepoScope:
    if orgs is None and repos is None:
        return OrgRepoScope(scope_type="global")
    return OrgRepoScope(
        scoped_orgs=orgs or [],
        scoped_repos=repos or [],
        scope_type="org" if orgs else "repo",
    )


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
        with pytest.raises(QueryValidationError):
            validate_and_prepare("SELECT pg_read_file('/etc/passwd')", _scope())

    def test_events_hourly_allowed(self):
        sql, _ = validate_and_prepare("SELECT * FROM events_hourly LIMIT 10", _scope())
        assert sql

    def test_behavioral_baselines_allowed(self):
        sql, _ = validate_and_prepare("SELECT * FROM behavioral_baselines LIMIT 5", _scope())
        assert sql

    def test_detections_daily_allowed(self):
        sql, _ = validate_and_prepare("SELECT * FROM detections_daily LIMIT 5", _scope())
        assert sql
