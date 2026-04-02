"""SQLAlchemy ORM model for external collaborators."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class ExternalCollaborator(Base):
    """Tracks external (outside / guest) collaborators granted access to an org or repo.

    This is a regular PostgreSQL table (not a TimescaleDB hypertable).
    """

    __tablename__ = "external_collaborators"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    repo: Mapped[str | None] = mapped_column(Text)
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    github_id: Mapped[int | None] = mapped_column(BigInteger)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granted_by: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[str | None] = mapped_column(Text)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_event_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()"),
        onupdate=text("NOW()")
    )
    data_source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'audit_event'")
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_run_id: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "role IN ('read', 'triage', 'write', 'maintain', 'admin',"
            " 'outside_collaborator', 'guest_collaborator')",
            name="external_collaborators_role_check",
        ),
        UniqueConstraint("org", "repo", "github_login", name="uq_ext_collab_scope"),
        Index("idx_ext_collab_org", "org", "is_active"),
        Index("idx_ext_collab_login", "github_login", "is_active"),
    )
