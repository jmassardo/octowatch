"""SQLAlchemy ORM model for in-app user notifications."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class Notification(Base):
    """In-app notification delivered to a specific user."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="info")
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="system")
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class NotificationPreference(Base):
    """Per-user notification delivery preferences."""

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    slack_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    severity_filter: Mapped[str] = mapped_column(
        Text, nullable=False, default="info"
    )  # minimum severity: info, warning, critical
    detection_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sync_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    system_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )
