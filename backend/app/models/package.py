"""SQLAlchemy ORM models for GitHub Packages monitoring."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class Package(Base):
    """A GitHub Package tracked for security and operations monitoring."""

    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    repo: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    package_type: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'private'"))
    owner: Mapped[str | None] = mapped_column(Text)
    versions_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    latest_version: Mapped[str | None] = mapped_column(Text)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    published_outside_actions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    published_by_external: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    __table_args__ = (
        Index("idx_packages_org", "org"),
        Index("idx_packages_visibility", "visibility"),
        Index("idx_packages_type", "package_type"),
        Index("idx_packages_org_name", "org", "name", unique=True),
    )


class PackageAlert(Base):
    """A security alert generated from package monitoring analysis."""

    __tablename__ = "package_alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("packages.id", ondelete="CASCADE"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))

    __table_args__ = (
        Index("idx_package_alerts_package_id", "package_id"),
        Index("idx_package_alerts_status", "status"),
        Index("idx_package_alerts_severity", "severity"),
        Index("idx_package_alerts_type", "alert_type"),
    )
