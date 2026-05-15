"""SQLAlchemy ORM model for user behavior classifications."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class UserClassification(Base):
    """Stores per-user behavioral persona classification results."""

    __tablename__ = "user_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_login: Mapped[str] = mapped_column(Text, nullable=False)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    persona: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    surfaces: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    analysis_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("idx_user_classifications_login_org", "user_login", "org"),
        Index("idx_user_classifications_persona", "persona"),
        Index("idx_user_classifications_classified_at", "classified_at"),
    )
