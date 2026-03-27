"""Unit tests for the ExternalCollaborator ORM model."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import inspect

from app.models.external_collaborator import ExternalCollaborator


class TestExternalCollaboratorTableMetadata:
    """Verify table name, columns, indexes, and constraints from SQLAlchemy metadata."""

    def test_tablename(self):
        assert ExternalCollaborator.__tablename__ == "external_collaborators"

    def test_all_expected_columns_present(self):
        mapper = inspect(ExternalCollaborator)
        column_names = {col.key for col in mapper.columns}
        expected = {
            "id",
            "org",
            "repo",
            "github_login",
            "github_id",
            "role",
            "granted_at",
            "granted_by",
            "is_active",
            "removed_at",
            "removed_by",
            "last_event_at",
            "source_event_id",
            "created_at",
            "updated_at",
        }
        assert column_names == expected

    def test_primary_key_is_id(self):
        mapper = inspect(ExternalCollaborator)
        pk_cols = [col.name for col in mapper.primary_key]
        assert pk_cols == ["id"]

    def test_non_nullable_columns(self):
        table = ExternalCollaborator.__table__
        non_nullable = {col.name for col in table.columns if not col.nullable}
        expected_non_nullable = {
            "id",
            "org",
            "github_login",
            "role",
            "granted_at",
            "is_active",
            "created_at",
            "updated_at",
        }
        assert expected_non_nullable.issubset(non_nullable)

    def test_nullable_columns(self):
        table = ExternalCollaborator.__table__
        nullable = {col.name for col in table.columns if col.nullable}
        expected_nullable = {
            "repo",
            "github_id",
            "granted_by",
            "removed_at",
            "removed_by",
            "last_event_at",
            "source_event_id",
        }
        assert expected_nullable.issubset(nullable)

    def test_indexes_exist(self):
        table = ExternalCollaborator.__table__
        index_names = {idx.name for idx in table.indexes}
        expected_indexes = {
            "idx_ext_collab_org",
            "idx_ext_collab_login",
        }
        assert expected_indexes.issubset(index_names)

    def test_index_org_includes_is_active(self):
        table = ExternalCollaborator.__table__
        for idx in table.indexes:
            if idx.name == "idx_ext_collab_org":
                col_names = [col.name for col in idx.columns]
                assert col_names == ["org", "is_active"]
                break
        else:
            raise AssertionError("idx_ext_collab_org index not found")

    def test_index_login_includes_is_active(self):
        table = ExternalCollaborator.__table__
        for idx in table.indexes:
            if idx.name == "idx_ext_collab_login":
                col_names = [col.name for col in idx.columns]
                assert col_names == ["github_login", "is_active"]
                break
        else:
            raise AssertionError("idx_ext_collab_login index not found")

    def test_unique_constraint_exists(self):
        table = ExternalCollaborator.__table__
        unique_constraints = {
            c.name for c in table.constraints if hasattr(c, "columns") and len(c.columns) > 1
        }
        assert "uq_ext_collab_scope" in unique_constraints

    def test_unique_constraint_columns(self):
        table = ExternalCollaborator.__table__
        for constraint in table.constraints:
            if getattr(constraint, "name", None) == "uq_ext_collab_scope":
                col_names = [col.name for col in constraint.columns]
                assert col_names == ["org", "repo", "github_login"]
                break
        else:
            raise AssertionError("uq_ext_collab_scope constraint not found")

    def test_check_constraint_on_role(self):
        table = ExternalCollaborator.__table__
        check_constraints = {
            c.name for c in table.constraints if c.__class__.__name__ == "CheckConstraint"
        }
        assert "external_collaborators_role_check" in check_constraints


class TestExternalCollaboratorInstantiation:
    """Verify ORM object construction and attribute access."""

    def test_create_instance_with_required_fields(self):
        now = datetime.now(tz=UTC)
        collab = ExternalCollaborator(
            org="my-org",
            github_login="octocat",
            role="write",
            granted_at=now,
        )
        assert collab.org == "my-org"
        assert collab.github_login == "octocat"
        assert collab.role == "write"
        assert collab.granted_at == now
        assert collab.repo is None
        assert collab.github_id is None
        assert collab.granted_by is None
        assert collab.removed_at is None
        assert collab.removed_by is None
        assert collab.last_event_at is None
        assert collab.source_event_id is None

    def test_create_instance_with_all_fields(self):
        now = datetime.now(tz=UTC)
        collab = ExternalCollaborator(
            org="acme-corp",
            repo="acme-corp/secret-repo",
            github_login="external-dev",
            github_id=999888,
            role="admin",
            granted_at=now,
            granted_by="admin-user",
            is_active=False,
            removed_at=now,
            removed_by="admin-user",
            last_event_at=now,
            source_event_id=42,
        )
        assert collab.org == "acme-corp"
        assert collab.repo == "acme-corp/secret-repo"
        assert collab.github_login == "external-dev"
        assert collab.github_id == 999888
        assert collab.role == "admin"
        assert collab.granted_at == now
        assert collab.granted_by == "admin-user"
        assert collab.is_active is False
        assert collab.removed_at == now
        assert collab.removed_by == "admin-user"
        assert collab.last_event_at == now
        assert collab.source_event_id == 42

    def test_repo_nullable_for_org_level(self):
        """repo=None means org-level external collaborator."""
        collab = ExternalCollaborator(
            org="my-org",
            github_login="ext-user",
            role="read",
            granted_at=datetime.now(tz=UTC),
        )
        assert collab.repo is None

    def test_all_valid_roles_accepted(self):
        """Ensure the model can be instantiated with every valid role value."""
        valid_roles = [
            "read",
            "triage",
            "write",
            "maintain",
            "admin",
            "outside_collaborator",
            "guest_collaborator",
        ]
        for role in valid_roles:
            collab = ExternalCollaborator(
                org="test-org",
                github_login="user",
                role=role,
                granted_at=datetime.now(tz=UTC),
            )
            assert collab.role == role


class TestExternalCollaboratorPackageExport:
    """Verify the model is properly exported from the models package."""

    def test_import_from_package(self):
        from app.models import ExternalCollaborator as EC

        assert EC is ExternalCollaborator

    def test_in_all_exports(self):
        import app.models

        assert "ExternalCollaborator" in app.models.__all__
