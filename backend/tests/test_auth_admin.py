"""Tests for admin auth configuration (schemas, models, migration, service)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.admin_auth import (
    AuthMethodRead,
    AuthMethodUpdate,
    SAMLTestResult,
    SessionPolicyRead,
    SessionPolicyUpdate,
)

# ──────── Schema validation tests ────────


class TestAuthMethodSchemas:
    """Validate AuthMethodRead / AuthMethodUpdate schemas."""

    def test_auth_method_read_from_dict(self) -> None:
        data = {
            "id": 1,
            "method_name": "github_oauth",
            "display_name": "GitHub OAuth",
            "enabled": True,
            "config_json": {"client_id": "abc"},
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        m = AuthMethodRead.model_validate(data)
        assert m.method_name == "github_oauth"
        assert m.enabled is True
        assert m.config_json == {"client_id": "abc"}

    def test_auth_method_update_partial(self) -> None:
        u = AuthMethodUpdate(enabled=False)
        assert u.enabled is False
        assert u.config_json is None

    def test_auth_method_update_with_config(self) -> None:
        u = AuthMethodUpdate(config_json={"idp_sso_url": "https://example.com"})
        assert u.config_json is not None
        assert u.config_json["idp_sso_url"] == "https://example.com"


class TestSAMLTestResultSchema:
    """Validate SAMLTestResult schema."""

    def test_success_result(self) -> None:
        r = SAMLTestResult(success=True, message="OK")
        assert r.success is True

    def test_result_with_details(self) -> None:
        r = SAMLTestResult(success=False, message="Fail", details={"code": 500})
        assert r.details == {"code": 500}


class TestSessionPolicySchemas:
    """Validate SessionPolicyRead / SessionPolicyUpdate schemas."""

    def test_session_policy_read(self) -> None:
        data = {
            "id": 1,
            "policy_key": "max_session_duration",
            "policy_value": "86400",
            "description": "Max duration",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        p = SessionPolicyRead.model_validate(data)
        assert p.policy_key == "max_session_duration"

    def test_session_policy_update_valid(self) -> None:
        u = SessionPolicyUpdate(policy_value="7200")
        assert u.policy_value == "7200"
        assert u.description is None

    def test_session_policy_update_empty_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SessionPolicyUpdate(policy_value="")


# ──────── Model column existence ────────


class TestAuthMethodModel:
    """Verify AuthMethodConfig model has the expected columns."""

    def test_columns_exist(self) -> None:
        from app.models.auth_method import AuthMethodConfig

        mapper = AuthMethodConfig.__mapper__
        column_names = {c.key for c in mapper.column_attrs}
        expected = {
            "id",
            "method_name",
            "display_name",
            "enabled",
            "config_json",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(column_names)

    def test_table_name(self) -> None:
        from app.models.auth_method import AuthMethodConfig

        assert AuthMethodConfig.__tablename__ == "auth_method_configs"


class TestSessionPolicyModel:
    """Verify SessionPolicySetting model has the expected columns."""

    def test_columns_exist(self) -> None:
        from app.models.auth_method import SessionPolicySetting

        mapper = SessionPolicySetting.__mapper__
        column_names = {c.key for c in mapper.column_attrs}
        expected = {"id", "policy_key", "policy_value", "description", "created_at", "updated_at"}
        assert expected.issubset(column_names)


# ──────── Migration file validation ────────


class TestMigration0040:
    """Validate migration file can be loaded and has correct revision chain."""

    def test_migration_file_exists(self) -> None:
        migration_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "0040_auth_method_configs.py"
        )
        assert migration_path.exists(), f"Migration not found at {migration_path}"

    def test_migration_revision_chain(self) -> None:
        migration_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "0040_auth_method_configs.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0040", str(migration_path))
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.revision == "0040"
        assert mod.down_revision == "0039"

    def test_migration_has_upgrade_downgrade(self) -> None:
        migration_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "0040_auth_method_configs.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0040", str(migration_path))
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert callable(getattr(mod, "upgrade", None))
        assert callable(getattr(mod, "downgrade", None))


# ──────── Auth service helper ────────


class TestIsAuthMethodEnabled:
    """Test the is_auth_method_enabled service function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_table_missing(self, db_session: AsyncSession) -> None:
        """When auth_method_configs table doesn't exist (e.g. SQLite in tests),
        the function should gracefully return True (default enabled)."""
        from app.services.auth_service import is_auth_method_enabled

        result = await is_auth_method_enabled(db_session, "github_oauth")
        assert result is True
