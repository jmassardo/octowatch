"""Unit tests for RBAC service: scope injection, role resolution helpers."""

from __future__ import annotations

from typing import Any

from app.services.rbac_service import OrgRepoScope


class TestOrgRepoScope:
    def test_global_scope_allows_all(self) -> None:
        scope = OrgRepoScope(scope_type="global")
        assert scope.is_global is True

    def test_empty_org_list_is_not_global(self) -> None:
        scope = OrgRepoScope(scoped_orgs=[], scoped_repos=[], scope_type="org")
        assert scope.is_global is False

    def test_org_scoped(self) -> None:
        scope = OrgRepoScope(scoped_orgs=["my-org"], scope_type="org")
        assert scope.is_global is False
        assert "my-org" in scope.scoped_orgs

    def test_repo_scoped(self) -> None:
        scope = OrgRepoScope(
            scoped_orgs=["my-org"], scoped_repos=["my-org/repo1"], scope_type="repo"
        )
        assert "my-org/repo1" in scope.scoped_repos


class TestInjectScopePredicate:
    """Tests for the SQL scope injection function using basic column mock."""

    def _make_stub_stmt(self) -> Any:
        """Create a simple SQLAlchemy-like stub for testing."""
        from unittest.mock import MagicMock

        stmt = MagicMock()
        stmt.where = MagicMock(return_value=stmt)
        return stmt

    def test_global_scope_no_filter_added(self) -> None:
        from app.services.rbac_service import inject_scope_predicate

        stmt = self._make_stub_stmt()
        scope = OrgRepoScope(scope_type="global")
        _ = inject_scope_predicate(stmt, scope, "org", "repo")
        # No .where() should be called for global scope
        stmt.where.assert_not_called()

    def test_scoped_adds_org_filter(self) -> None:
        from unittest.mock import MagicMock

        from app.services.rbac_service import inject_scope_predicate

        stmt = self._make_stub_stmt()
        scope = OrgRepoScope(scoped_orgs=["org1", "org2"], scope_type="org")

        # Create a mock column object that supports .in_()
        org_col = MagicMock()
        org_col.in_.return_value = MagicMock()

        _ = inject_scope_predicate(stmt, scope, org_col, None)
        assert stmt.where.called
