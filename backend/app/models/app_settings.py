"""SQLAlchemy models for the internal secrets/settings store."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class AppSetting(Base):
    """Encrypted key-value store for application secrets and configuration.

    Each row holds a single configuration key and its AES-256-GCM encrypted
    value.  The ``category`` groups related settings (e.g. ``github_oauth``,
    ``saml``).  The ``sensitivity`` controls how the value is masked in API
    responses: ``critical`` values are never shown, ``sensitive`` values are
    partially masked, and ``config`` values are shown as plaintext.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False, default="config")
    sensitivity: Mapped[str] = mapped_column(Text, nullable=False, default="config")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(Text, nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class AppSettingAudit(Base):
    """Audit trail for setting changes.

    Every create / update / delete to :class:`AppSetting` is recorded here
    with masked old and new values so that sensitive data is not logged.
    """

    __tablename__ = "app_settings_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    setting_key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[str] = mapped_column(Text, nullable=False)
    old_value_masked: Mapped[str | None] = mapped_column(Text)
    new_value_masked: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class SetupState(Base):
    """Tracks whether initial setup has been completed.

    Only one row (``id=1``) should ever exist.  The ``setup_token_hash``
    stores a bcrypt hash of the one-time setup token that is printed to the
    container log on first boot.
    """

    __tablename__ = "setup_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_by: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    setup_token_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
