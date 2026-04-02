"""SQLAlchemy ORM models for integrations (ticketing, notifications, IdP enrichments)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.detection import Detection

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.audit_event import Base


class TicketingConfig(Base):
    """Admin-configured ticketing integration (Jira or GitHub Issues)."""

    __tablename__ = "ticketing_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    project_key: Mapped[str | None] = mapped_column(Text)
    default_issue_type: Mapped[str] = mapped_column(Text, nullable=False, default="Bug")
    severity_priority_map: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    auto_create: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_create_severities: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    credential_env_var: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )

    tickets: Mapped[list[Ticket]] = relationship("Ticket", back_populates="config")


class Ticket(Base):
    """External ticket linked to a detection."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticketing_config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ticketing_configs.id"), nullable=False
    )
    detection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("detections.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    external_url: Mapped[str] = mapped_column(Text, nullable=False)
    external_status: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    config: Mapped[TicketingConfig] = relationship("TicketingConfig", back_populates="tickets")
    detection: Mapped[Detection] = relationship("Detection", back_populates="tickets")  # type: ignore[name-defined]


class NotificationConfig(Base):
    """Admin-configured notification channel (Slack or SMTP email)."""

    __tablename__ = "notification_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_type: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    credential_env_var: Mapped[str | None] = mapped_column(Text)
    notify_severities: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )


class IdpActorEnrichment(Base):
    """Actor metadata synchronized from IdP providers (Okta, Entra, Google)."""

    __tablename__ = "idp_actor_enrichments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    idp_provider: Mapped[str] = mapped_column(Text, nullable=False)
    idp_user_id: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    employment_status: Mapped[str | None] = mapped_column(Text)
    manager_login: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str | None] = mapped_column(Text)
    raw_attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    sync_error: Mapped[str | None] = mapped_column(Text)
