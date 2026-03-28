"""Unit tests for the app_settings models."""

from __future__ import annotations

from app.models.app_settings import AppSetting, AppSettingAudit, SetupState


class TestAppSettingModel:
    """Tests for the AppSetting ORM model."""

    def test_tablename(self) -> None:
        assert AppSetting.__tablename__ == "app_settings"

    def test_has_required_columns(self) -> None:
        columns = {c.name for c in AppSetting.__table__.columns}
        expected = {
            "id",
            "key",
            "encrypted_value",
            "category",
            "sensitivity",
            "description",
            "updated_by",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)

    def test_key_column_is_unique(self) -> None:
        key_col = AppSetting.__table__.c.key
        assert key_col.unique is True

    def test_key_column_is_indexed(self) -> None:
        key_col = AppSetting.__table__.c.key
        assert key_col.index is True


class TestAppSettingAuditModel:
    """Tests for the AppSettingAudit ORM model."""

    def test_tablename(self) -> None:
        assert AppSettingAudit.__tablename__ == "app_settings_audit"

    def test_has_required_columns(self) -> None:
        columns = {c.name for c in AppSettingAudit.__table__.columns}
        expected = {
            "id",
            "setting_key",
            "action",
            "changed_by",
            "old_value_masked",
            "new_value_masked",
            "created_at",
        }
        assert expected.issubset(columns)

    def test_setting_key_is_indexed(self) -> None:
        key_col = AppSettingAudit.__table__.c.setting_key
        assert key_col.index is True


class TestSetupStateModel:
    """Tests for the SetupState ORM model."""

    def test_tablename(self) -> None:
        assert SetupState.__tablename__ == "setup_state"

    def test_has_required_columns(self) -> None:
        columns = {c.name for c in SetupState.__table__.columns}
        expected = {
            "id",
            "is_complete",
            "completed_by",
            "completed_at",
            "setup_token_hash",
            "created_at",
        }
        assert expected.issubset(columns)
