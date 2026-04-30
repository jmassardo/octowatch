"""SQLAlchemy ORM models for teams and team-based RBAC."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.audit_event import Base
from app.models.user import RbacRole


class Team(Base):
    """Internal application team for grouping users and assigning shared roles.

    Teams can optionally be linked to a GitHub organization team for automatic
    membership sync (when ``auto_sync`` is enabled).
    """

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    github_org: Mapped[str | None] = mapped_column(Text)
    github_team_slug: Mapped[str | None] = mapped_column(Text)
    auto_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[TeamMembership]] = relationship(
        "TeamMembership",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    role_assignments: Mapped[list[TeamRoleAssignment]] = relationship(
        "TeamRoleAssignment",
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamMembership(Base):
    """Membership link between a user (by GitHub login) and a team."""

    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("team_id", "user_login", name="uq_team_memberships_team_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    user_login: Mapped[str] = mapped_column(Text, nullable=False)
    added_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    team: Mapped[Team] = relationship("Team", back_populates="memberships")


class TeamRoleAssignment(Base):
    """Role binding for a team, with optional org/repo scope."""

    __tablename__ = "team_role_assignments"
    __table_args__ = (
        UniqueConstraint("team_id", "role_id", name="uq_team_role_assignments_team_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rbac_roles.id", ondelete="CASCADE"), nullable=False
    )
    org_slug: Mapped[str | None] = mapped_column(Text)
    repo_slugs: Mapped[list[str] | None] = mapped_column(JSONB)
    assigned_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    team: Mapped[Team] = relationship("Team", back_populates="role_assignments")
    role: Mapped[RbacRole] = relationship("RbacRole")
