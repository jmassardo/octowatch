"""SQLAlchemy ORM models for users and RBAC."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.audit_event import Base


class RbacRole(Base):
    """Application role definitions with canonical permission sets."""

    __tablename__ = "rbac_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    assignments: Mapped[list[UserRoleAssignment]] = relationship(
        "UserRoleAssignment", back_populates="role"
    )


class UserRoleAssignment(Base):
    """User or team to role binding with org/repo scope."""

    __tablename__ = "user_role_assignments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    github_login: Mapped[str] = mapped_column(Text, nullable=False)
    github_team_id: Mapped[int | None] = mapped_column(BigInteger)
    github_team_slug: Mapped[str | None] = mapped_column(Text)
    saml_subject: Mapped[str | None] = mapped_column(Text)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("rbac_roles.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_value: Mapped[str | None] = mapped_column(Text)
    granted_by: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    role: Mapped[RbacRole] = relationship("RbacRole", back_populates="assignments")
