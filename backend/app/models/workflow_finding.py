"""SQLAlchemy ORM models for GitHub Actions workflow security findings."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class WorkflowFinding(Base):
    """Security finding from GitHub Actions workflow analysis."""

    __tablename__ = "workflow_findings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    repo: Mapped[str] = mapped_column(Text, nullable=False)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_path: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    suggested_fix: Mapped[str | None] = mapped_column(Text)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("idx_workflow_findings_repo", "repo", "scanned_at"),
        Index("idx_workflow_findings_org", "org"),
        Index("idx_workflow_findings_severity", "severity"),
    )
