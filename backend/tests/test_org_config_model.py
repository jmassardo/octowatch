"""Unit tests for the OrgConfig model."""

from __future__ import annotations

from app.models.org_config import OrgConfig


class TestOrgConfigModel:
    """Tests for the OrgConfig ORM model."""

    def test_tablename(self) -> None:
        assert OrgConfig.__tablename__ == "org_config"

    def test_has_required_columns(self) -> None:
        columns = {c.name for c in OrgConfig.__table__.columns}
        expected = {
            "id",
            "org_slug",
            "copilot_cost_per_seat",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)

    def test_org_slug_column_is_unique(self) -> None:
        key_col = OrgConfig.__table__.c.org_slug
        assert key_col.unique is True

    def test_org_slug_column_is_indexed(self) -> None:
        key_col = OrgConfig.__table__.c.org_slug
        assert key_col.index is True

    def test_copilot_cost_per_seat_is_nullable(self) -> None:
        col = OrgConfig.__table__.c.copilot_cost_per_seat
        assert col.nullable is True
