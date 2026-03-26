"""SQLAlchemy ORM model for ingestion cursors."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class IngestionCursor(Base):
    """Tracks last successfully-processed object prefix per source.

    Used for resumable polling (S3, Azure Blob) and status for MinIO push.
    Row-level locking via SELECT ... FOR UPDATE SKIP LOCKED ensures only one
    worker processes each source at a time.
    """

    __tablename__ = "ingestion_cursors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_region: Mapped[str | None] = mapped_column(Text)
    source_prefix: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_prefix: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_file: Mapped[str | None] = mapped_column(Text)
    last_event_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    error_message: Mapped[str | None] = mapped_column(Text)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    poll_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
