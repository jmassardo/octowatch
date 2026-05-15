"""Tests for the UserClassification model."""

from __future__ import annotations

from app.models.user_classification import UserClassification


class TestUserClassificationModel:
    """Validate ORM model metadata."""

    def test_tablename(self) -> None:
        assert UserClassification.__tablename__ == "user_classifications"

    def test_columns_present(self) -> None:
        column_names = {c.name for c in UserClassification.__table__.columns}
        expected = {
            "id",
            "user_login",
            "org",
            "persona",
            "confidence_score",
            "event_count",
            "surfaces",
            "analysis_window_days",
            "classified_at",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(column_names)

    def test_primary_key(self) -> None:
        pk_cols = [c.name for c in UserClassification.__table__.primary_key.columns]
        assert pk_cols == ["id"]

    def test_indexes_exist(self) -> None:
        index_names = {idx.name for idx in UserClassification.__table__.indexes}
        assert "idx_user_classifications_login_org" in index_names
        assert "idx_user_classifications_persona" in index_names
        assert "idx_user_classifications_classified_at" in index_names

    def test_persona_column_length(self) -> None:
        persona_col = UserClassification.__table__.columns["persona"]
        assert persona_col.type.length == 30

    def test_confidence_score_is_float(self) -> None:
        col = UserClassification.__table__.columns["confidence_score"]
        assert not col.nullable
