"""Tests for _create_version_snapshot in rule_service.

Verifies that rule creation correctly writes a version snapshot to the
rule_versions table using the correct column names (logic_config,
changed_by, change_summary) — regression test for a bug where mismatched
kwargs (logic_config_snapshot, created_by, comment) caused a 500 error.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.audit_event import Base
from app.models.detection import Detection, DetectionSuppression, RuleDefinition, RuleVersion
from app.services.rule_service import _create_version_snapshot

# ---------------------------------------------------------------------------
# SQLite type-compiler overrides (mirrored from test_integration.py)
# ---------------------------------------------------------------------------
if not hasattr(SQLiteTypeCompiler, "visit_INET"):
    SQLiteTypeCompiler.visit_INET = lambda self, type_, **kw: "VARCHAR(45)"  # type: ignore[attr-defined]
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"  # type: ignore[attr-defined]
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]

# Override BIGINT → INTEGER so autoincrement PKs work on SQLite.
SQLiteTypeCompiler.visit_BIGINT = lambda self, type_, **kw: "INTEGER"  # type: ignore[method-assign]

_SQLITE_TABLES = [
    RuleDefinition.__table__,
    RuleVersion.__table__,
    DetectionSuppression.__table__,
    Detection.__table__,
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """In-memory SQLite engine with schema pre-created."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng.sync_engine, "connect")
    def _sqlite_setup(dbapi_conn: Any, _rec: Any) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys = ON")
        dbapi_conn.create_function("NOW", 0, lambda: datetime.now(UTC).isoformat())

    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=_SQLITE_TABLES)
        )

    yield eng

    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=_SQLITE_TABLES)
        )
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a real async database session backed by in-memory SQLite."""
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()


def _make_rule(**overrides: Any) -> RuleDefinition:
    """Create a RuleDefinition with sensible defaults."""
    defaults: dict[str, Any] = {
        "name": "Test Rule",
        "slug": "test-rule",
        "description": "A test rule for snapshot verification",
        "category": "other",
        "default_severity": "medium",
        "default_confidence": "medium",
        "logic_type": "threshold",
        "logic_config": {"action_filters": ["repos.create"], "threshold": 5},
        "enabled": True,
        "status": "draft",
        "version": 1,
        "created_by": "testuser",
    }
    defaults.update(overrides)
    return RuleDefinition(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateVersionSnapshot:
    """Verify _create_version_snapshot writes correct data to rule_versions."""

    async def test_snapshot_is_persisted(self, session: AsyncSession) -> None:
        """Creating a version snapshot should persist a RuleVersion row."""
        rule = _make_rule()
        session.add(rule)
        await session.flush()

        snapshot = await _create_version_snapshot(
            session, rule, actor="testuser", comment="Initial version"
        )
        await session.commit()

        assert snapshot.id is not None
        assert snapshot.rule_id == rule.id

    async def test_snapshot_stores_logic_config(self, session: AsyncSession) -> None:
        """The snapshot should store the rule's logic_config correctly."""
        logic = {"action_filters": ["org.update"], "threshold": 10, "window_minutes": 30}
        rule = _make_rule(logic_config=logic, slug="logic-config-test")
        session.add(rule)
        await session.flush()

        snapshot = await _create_version_snapshot(session, rule, actor="author")
        await session.commit()

        fetched = (
            await session.execute(select(RuleVersion).where(RuleVersion.id == snapshot.id))
        ).scalar_one()
        assert fetched.logic_config == logic

    async def test_snapshot_stores_changed_by(self, session: AsyncSession) -> None:
        """The snapshot should record the actor as changed_by."""
        rule = _make_rule(slug="changed-by-test")
        session.add(rule)
        await session.flush()

        snapshot = await _create_version_snapshot(session, rule, actor="rule-editor")
        await session.commit()

        fetched = (
            await session.execute(select(RuleVersion).where(RuleVersion.id == snapshot.id))
        ).scalar_one()
        assert fetched.changed_by == "rule-editor"

    async def test_snapshot_stores_change_summary(self, session: AsyncSession) -> None:
        """The comment parameter should be stored as change_summary."""
        rule = _make_rule(slug="change-summary-test")
        session.add(rule)
        await session.flush()

        snapshot = await _create_version_snapshot(
            session, rule, actor="author", comment="Fixed threshold"
        )
        await session.commit()

        fetched = (
            await session.execute(select(RuleVersion).where(RuleVersion.id == snapshot.id))
        ).scalar_one()
        assert fetched.change_summary == "Fixed threshold"

    async def test_snapshot_with_none_comment(self, session: AsyncSession) -> None:
        """When comment is None, change_summary should be None."""
        rule = _make_rule(slug="none-comment-test")
        session.add(rule)
        await session.flush()

        snapshot = await _create_version_snapshot(session, rule, actor="author")
        await session.commit()

        fetched = (
            await session.execute(select(RuleVersion).where(RuleVersion.id == snapshot.id))
        ).scalar_one()
        assert fetched.change_summary is None

    async def test_snapshot_version_matches_rule(self, session: AsyncSession) -> None:
        """The snapshot version should match the rule's current version."""
        rule = _make_rule(slug="version-match-test", version=3)
        session.add(rule)
        await session.flush()

        snapshot = await _create_version_snapshot(session, rule, actor="author")
        await session.commit()

        fetched = (
            await session.execute(select(RuleVersion).where(RuleVersion.id == snapshot.id))
        ).scalar_one()
        assert fetched.version == 3

    async def test_snapshot_linked_to_rule_via_relationship(self, session: AsyncSession) -> None:
        """The snapshot should be accessible via rule.versions relationship."""
        rule = _make_rule(slug="relationship-test")
        session.add(rule)
        await session.flush()

        await _create_version_snapshot(session, rule, actor="author", comment="Initial version")
        await session.commit()

        await session.refresh(rule, ["versions"])
        assert len(rule.versions) == 1
        assert rule.versions[0].changed_by == "author"
        assert rule.versions[0].change_summary == "Initial version"
