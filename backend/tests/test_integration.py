"""Database integration tests using real async SQLite.

These tests exercise genuine SQLAlchemy ORM operations against an in-memory
SQLite database — no mocks, no Docker, no PostgreSQL required.  They verify
that model definitions, relationships, and basic CRUD operations behave
correctly through the full ORM stack.

SQLite compatibility notes
--------------------------
* ``JSONB`` columns are stored as JSON text — SQLAlchemy's ``JSON`` base type
  handles serialisation transparently.
* ``INET`` columns are stored as plain ``TEXT`` — fine for string round-trips.
* ``ARRAY`` columns (used by the ``Detection`` model) are **not** supported by
  SQLite, so tables containing them are excluded from the schema creation.
* ``NOW()`` is not a built-in SQLite function; a custom scalar function is
  registered on every connection so that ``server_default=text("NOW()")``
  works.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.models.audit_event import Base
from app.models.audit_trail import AuditTrail
from app.models.detection import Detection, DetectionSuppression, RuleDefinition, RuleVersion
from app.models.query_template import QueryTemplate
from app.models.threat_intel import ThreatIntelCampaign
from app.models.user import RbacRole, UserRoleAssignment

# ---------------------------------------------------------------------------
# Teach the SQLite type compiler to render PostgreSQL-specific column types.
# INET and JSONB have no built-in SQLite visitor; mapping them to TEXT/JSON
# lets ``create_all()`` succeed while preserving round-trip correctness for
# the simple string / dict values used in tests.
#
# BigInteger is mapped to "INTEGER" because SQLite only auto-generates rowids
# for columns declared as exactly ``INTEGER PRIMARY KEY``; the default
# rendering "BIGINT" does not trigger that behaviour.
#
# ARRAY is mapped to "TEXT" so that tables with ARRAY columns (e.g.
# ``Detection.event_ids``) can be created — the column is never read/written
# in tests but the table must exist for relationship-loading during cascade
# deletes.
# ---------------------------------------------------------------------------
if not hasattr(SQLiteTypeCompiler, "visit_INET"):
    SQLiteTypeCompiler.visit_INET = lambda self, type_, **kw: "VARCHAR(45)"  # type: ignore[attr-defined]
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"  # type: ignore[attr-defined]
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"  # type: ignore[attr-defined]

# Override BIGINT → INTEGER so autoincrement PKs work on SQLite.
SQLiteTypeCompiler.visit_BIGINT = lambda self, type_, **kw: "INTEGER"  # type: ignore[method-assign]

# ---------------------------------------------------------------------------
# Tables to create on the in-memory SQLite database.
# NOTE: ``Model.__table__`` is ``Table`` at runtime but the SQLAlchemy mypy
# stubs type it as ``FromClause``.  We keep the list untyped to avoid an
# 8-line ``cast()`` wall; the two ``arg-type`` notes on ``create_all`` and
# ``drop_all`` are false positives from the stubs.
# ---------------------------------------------------------------------------
_SQLITE_TABLES = [
    QueryTemplate.__table__,
    AuditTrail.__table__,
    RbacRole.__table__,
    UserRoleAssignment.__table__,
    ThreatIntelCampaign.__table__,
    RuleDefinition.__table__,
    RuleVersion.__table__,
    # Detection/Suppression tables must exist so that cascade-delete on
    # RuleDefinition can load the ``detections`` relationship without error.
    DetectionSuppression.__table__,
    Detection.__table__,
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def integration_engine() -> AsyncGenerator[AsyncEngine, None]:
    """In-memory SQLite engine with schema pre-created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_setup(dbapi_conn: Any, _rec: Any) -> None:
        # Enable FK enforcement (disabled by default in SQLite).
        dbapi_conn.execute("PRAGMA foreign_keys = ON")
        # Register NOW() so server_default=text("NOW()") works.
        dbapi_conn.create_function("NOW", 0, lambda: datetime.now(UTC).isoformat())

    # SQLite does not support AUTOINCREMENT on composite primary keys.
    # Temporarily set autoincrement=False so the DDL compiler skips
    # the AUTOINCREMENT keyword while still generating valid DDL.
    overrides: list[tuple[Any, Any]] = []
    for table in _SQLITE_TABLES:
        pk_cols = [c for c in table.columns if c.primary_key]
        if len(pk_cols) > 1:
            for col in pk_cols:
                if col.autoincrement is True:
                    overrides.append((col, col.autoincrement))
                    col.autoincrement = False

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=_SQLITE_TABLES)
        )

    # Restore original autoincrement settings so production metadata is unaffected.
    for col, orig in overrides:
        col.autoincrement = orig

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=_SQLITE_TABLES)
        )
    await engine.dispose()


@pytest_asyncio.fixture
async def session(integration_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a real (not mocked) async database session."""
    factory = async_sessionmaker(bind=integration_engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()


# ===================================================================
# QueryTemplate CRUD lifecycle
# ===================================================================


class TestQueryTemplateCRUD:
    """Full create -> read -> update -> delete cycle for QueryTemplate."""

    async def test_create_and_persist(self, session: AsyncSession) -> None:
        tpl = QueryTemplate(
            name="Repo deletions",
            description="Find all repo.destroy events in the last 7 days",
            sql="SELECT * FROM events WHERE action = 'repo.destroy'",
            created_by="analyst@acme.com",
            org_slug="acme-corp",
        )
        session.add(tpl)
        await session.commit()

        assert tpl.id is not None
        assert tpl.id > 0

    async def test_list_templates(self, session: AsyncSession) -> None:
        session.add_all(
            [
                QueryTemplate(name="T1", sql="SELECT 1", org_slug="org-a"),
                QueryTemplate(name="T2", sql="SELECT 2", org_slug="org-b"),
            ]
        )
        await session.commit()

        rows = (await session.execute(select(QueryTemplate))).scalars().all()
        assert len(rows) == 2
        assert {r.name for r in rows} == {"T1", "T2"}

    async def test_get_by_id(self, session: AsyncSession) -> None:
        tpl = QueryTemplate(
            name="Member removals",
            description="Members removed from org",
            sql="SELECT * FROM events WHERE action = 'org.remove_member'",
            created_by="admin",
            org_slug="my-org",
        )
        session.add(tpl)
        await session.commit()

        fetched = await session.get(QueryTemplate, tpl.id)
        assert fetched is not None
        assert fetched.name == "Member removals"
        assert fetched.description == "Members removed from org"
        assert fetched.sql == "SELECT * FROM events WHERE action = 'org.remove_member'"
        assert fetched.created_by == "admin"
        assert fetched.org_slug == "my-org"

    async def test_update_template(self, session: AsyncSession) -> None:
        tpl = QueryTemplate(name="Draft", sql="SELECT 1")
        session.add(tpl)
        await session.commit()

        tpl.name = "Final"
        tpl.sql = "SELECT * FROM events LIMIT 100"
        await session.commit()

        refreshed = await session.get(QueryTemplate, tpl.id)
        assert refreshed is not None
        assert refreshed.name == "Final"
        assert refreshed.sql == "SELECT * FROM events LIMIT 100"

    async def test_delete_template(self, session: AsyncSession) -> None:
        tpl = QueryTemplate(name="Ephemeral", sql="SELECT 1")
        session.add(tpl)
        await session.commit()
        tpl_id = tpl.id

        await session.delete(tpl)
        await session.commit()

        assert await session.get(QueryTemplate, tpl_id) is None

    async def test_filter_by_org_slug(self, session: AsyncSession) -> None:
        session.add_all(
            [
                QueryTemplate(name="A", sql="SELECT 1", org_slug="alpha"),
                QueryTemplate(name="B", sql="SELECT 2", org_slug="beta"),
                QueryTemplate(name="C", sql="SELECT 3", org_slug="alpha"),
            ]
        )
        await session.commit()

        alpha = (
            (await session.execute(select(QueryTemplate).where(QueryTemplate.org_slug == "alpha")))
            .scalars()
            .all()
        )

        assert len(alpha) == 2
        assert {t.name for t in alpha} == {"A", "C"}

    async def test_nullable_fields_default_to_none(self, session: AsyncSession) -> None:
        tpl = QueryTemplate(name="Minimal", sql="SELECT 1")
        session.add(tpl)
        await session.commit()

        fetched = await session.get(QueryTemplate, tpl.id)
        assert fetched is not None
        assert fetched.description is None
        assert fetched.created_by is None
        assert fetched.org_slug is None


# ===================================================================
# AuditTrail persistence
# ===================================================================


class TestAuditTrailPersistence:
    """Verify audit trail records round-trip through the ORM."""

    @staticmethod
    def _make_trail(**overrides: Any) -> AuditTrail:
        """Build an AuditTrail with sensible defaults."""
        defaults = {
            "id": 1,
            "timestamp": datetime.now(UTC),
            "user_login": "octocat",
            "user_github_id": 583231,
            "ip_address": "10.0.0.1",
            "user_agent": "Mozilla/5.0",
            "action_type": "query_template.create",
            "resource_type": "query_template",
            "resource_id": "42",
            "parameters": {"name": "My Template"},
            "outcome": "success",
            "error_detail": None,
        }
        defaults.update(overrides)
        return AuditTrail(**defaults)

    async def test_insert_and_read_back(self, session: AsyncSession) -> None:
        now = datetime.now(UTC)
        trail = self._make_trail(id=1, timestamp=now)
        session.add(trail)
        await session.commit()

        rows = (await session.execute(select(AuditTrail))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.user_login == "octocat"
        assert row.user_github_id == 583231
        assert row.ip_address == "10.0.0.1"
        assert row.action_type == "query_template.create"
        assert row.resource_type == "query_template"
        assert row.resource_id == "42"
        assert row.outcome == "success"
        assert row.error_detail is None
        assert row.user_agent == "Mozilla/5.0"

    async def test_jsonb_parameters_round_trip(self, session: AsyncSession) -> None:
        params = {
            "sql": "SELECT 1",
            "org": "acme",
            "nested": {"key": [1, 2, 3]},
        }
        trail = self._make_trail(id=2, parameters=params)
        session.add(trail)
        await session.commit()

        row = (await session.execute(select(AuditTrail))).scalar_one()
        assert row.parameters == params
        assert row.parameters["nested"]["key"] == [1, 2, 3]

    async def test_date_range_filtering(self, session: AsyncSession) -> None:
        base = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        for i in range(5):
            session.add(
                self._make_trail(
                    id=10 + i,
                    timestamp=base + timedelta(days=i),
                    action_type=f"action_{i}",
                )
            )
        await session.commit()

        # Filter: Jan 16 00:00 → Jan 19 00:00 (3 days, 3 rows)
        start = datetime(2025, 1, 16, 0, 0, 0, tzinfo=UTC)
        end = datetime(2025, 1, 19, 0, 0, 0, tzinfo=UTC)
        rows = (
            (
                await session.execute(
                    select(AuditTrail).where(
                        AuditTrail.timestamp >= start,
                        AuditTrail.timestamp < end,
                    )
                )
            )
            .scalars()
            .all()
        )

        assert len(rows) == 3
        assert {r.action_type for r in rows} == {"action_1", "action_2", "action_3"}

    async def test_error_detail_persists(self, session: AsyncSession) -> None:
        trail = self._make_trail(
            id=20,
            outcome="failure",
            error_detail="Permission denied: missing admin role",
        )
        session.add(trail)
        await session.commit()

        row = (await session.execute(select(AuditTrail))).scalar_one()
        assert row.outcome == "failure"
        assert row.error_detail == "Permission denied: missing admin role"


# ===================================================================
# RBAC Role & UserRoleAssignment persistence
# ===================================================================


class TestRbacPersistence:
    """Verify role and user-role-assignment models persist correctly."""

    async def test_create_role_with_permissions(self, session: AsyncSession) -> None:
        role = RbacRole(
            name="analyst",
            display_name="Security Analyst",
            description="Read-only access to audit logs and detections",
            permissions=["events:read", "detections:read", "queries:execute"],
        )
        session.add(role)
        await session.commit()

        fetched = await session.get(RbacRole, role.id)
        assert fetched is not None
        assert fetched.name == "analyst"
        assert fetched.display_name == "Security Analyst"
        assert fetched.permissions == [
            "events:read",
            "detections:read",
            "queries:execute",
        ]

    async def test_create_assignment_with_fk(self, session: AsyncSession) -> None:
        role = RbacRole(
            name="admin",
            display_name="Administrator",
            permissions=["*"],
        )
        session.add(role)
        await session.commit()

        assignment = UserRoleAssignment(
            github_login="octocat",
            role_id=role.id,
            scope_type="global",
            scope_value=None,
            granted_by="system",
            active=True,
        )
        session.add(assignment)
        await session.commit()

        fetched = await session.get(UserRoleAssignment, assignment.id)
        assert fetched is not None
        assert fetched.github_login == "octocat"
        assert fetched.role_id == role.id
        assert fetched.scope_type == "global"
        assert fetched.active is True

    async def test_role_assignment_relationship(self, session: AsyncSession) -> None:
        role = RbacRole(
            name="viewer",
            display_name="Viewer",
            permissions=["events:read"],
        )
        session.add(role)
        await session.commit()

        for login in ("alice", "bob"):
            session.add(
                UserRoleAssignment(
                    github_login=login,
                    role_id=role.id,
                    scope_type="org",
                    scope_value="acme-corp",
                    granted_by="admin",
                    active=True,
                )
            )
        await session.commit()

        await session.refresh(role, ["assignments"])
        assert len(role.assignments) == 2
        assert {a.github_login for a in role.assignments} == {"alice", "bob"}

    async def test_unique_role_name_constraint(self, session: AsyncSession) -> None:
        session.add(RbacRole(name="dup", display_name="First", permissions=[]))
        await session.commit()

        session.add(RbacRole(name="dup", display_name="Second", permissions=[]))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_scoped_assignment_fields(self, session: AsyncSession) -> None:
        role = RbacRole(
            name="repo-admin",
            display_name="Repo Admin",
            permissions=["repos:*"],
        )
        session.add(role)
        await session.commit()

        assignment = UserRoleAssignment(
            github_login="charlie",
            github_team_id=9876,
            github_team_slug="security-team",
            role_id=role.id,
            scope_type="repo",
            scope_value="acme-corp/secret-repo",
            granted_by="admin",
            active=True,
        )
        session.add(assignment)
        await session.commit()

        fetched = await session.get(UserRoleAssignment, assignment.id)
        assert fetched is not None
        assert fetched.github_team_id == 9876
        assert fetched.github_team_slug == "security-team"
        assert fetched.scope_type == "repo"
        assert fetched.scope_value == "acme-corp/secret-repo"


# ===================================================================
# RuleDefinition & RuleVersion persistence
# ===================================================================


class TestRulePersistence:
    """Verify rule definitions, versioning, and cascade behaviour."""

    async def test_create_rule_default_version(self, session: AsyncSession) -> None:
        rule = RuleDefinition(
            name="Suspicious repo deletion",
            slug="suspicious-repo-deletion",
            description="Fires when a repo is deleted outside business hours",
            category="data_exfiltration",
            default_severity="high",
            default_confidence="medium",
            logic_type="threshold",
            logic_config={"threshold": 1, "window_minutes": 60},
            created_by="rule-author",
        )
        session.add(rule)
        await session.commit()

        fetched = await session.get(RuleDefinition, rule.id)
        assert fetched is not None
        assert fetched.version == 1
        assert fetched.enabled is True
        assert fetched.slug == "suspicious-repo-deletion"

    async def test_update_rule_increments_version(self, session: AsyncSession) -> None:
        rule = RuleDefinition(
            name="SSH key added",
            slug="ssh-key-added",
            category="credential_abuse",
            default_severity="medium",
            default_confidence="high",
            logic_type="simple",
            logic_config={"actions": ["org.add_ssh_key"]},
            created_by="author",
            version=1,
        )
        session.add(rule)
        await session.commit()

        rule.version = 2
        rule.logic_config = {"actions": ["org.add_ssh_key", "org.add_deploy_key"]}
        rule.updated_by = "editor"
        await session.commit()

        refreshed = await session.get(RuleDefinition, rule.id)
        assert refreshed is not None
        assert refreshed.version == 2
        assert "org.add_deploy_key" in refreshed.logic_config["actions"]
        assert refreshed.updated_by == "editor"

    async def test_rule_version_snapshot(self, session: AsyncSession) -> None:
        rule = RuleDefinition(
            name="Mass permission change",
            slug="mass-permission-change",
            category="privilege_escalation",
            default_severity="critical",
            default_confidence="high",
            logic_type="threshold",
            logic_config={"threshold": 5, "window_minutes": 10},
            created_by="author",
            version=1,
        )
        session.add(rule)
        await session.commit()

        snapshot = RuleVersion(
            rule_id=rule.id,
            version=1,
            logic_config=rule.logic_config,
            change_summary="Initial creation",
            changed_by="author",
        )
        session.add(snapshot)
        await session.commit()

        versions = (
            (await session.execute(select(RuleVersion).where(RuleVersion.rule_id == rule.id)))
            .scalars()
            .all()
        )
        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].change_summary == "Initial creation"
        assert versions[0].logic_config == {"threshold": 5, "window_minutes": 10}

    async def test_rule_version_relationship(self, session: AsyncSession) -> None:
        rule = RuleDefinition(
            name="Workflow abuse",
            slug="workflow-abuse",
            category="ci_cd",
            default_severity="medium",
            default_confidence="medium",
            logic_type="pattern",
            logic_config={"pattern": "workflow_run.*"},
            created_by="author",
            version=2,
        )
        session.add(rule)
        await session.commit()

        for v in (1, 2):
            session.add(
                RuleVersion(
                    rule_id=rule.id,
                    version=v,
                    logic_config={"pattern": f"v{v}"},
                    changed_by="author",
                    change_summary=f"Version {v}",
                )
            )
        await session.commit()

        await session.refresh(rule, ["versions"])
        assert len(rule.versions) == 2
        assert sorted(v.version for v in rule.versions) == [1, 2]

    async def test_unique_slug_constraint(self, session: AsyncSession) -> None:
        session.add(
            RuleDefinition(
                name="Rule A",
                slug="unique-slug",
                category="cat",
                default_severity="low",
                default_confidence="low",
                logic_type="simple",
                logic_config={},
                created_by="a",
            )
        )
        await session.commit()

        session.add(
            RuleDefinition(
                name="Rule B",
                slug="unique-slug",
                category="cat",
                default_severity="low",
                default_confidence="low",
                logic_type="simple",
                logic_config={},
                created_by="b",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async def test_jsonb_logic_config_round_trip(self, session: AsyncSession) -> None:
        complex_config = {
            "conditions": [
                {
                    "field": "action",
                    "op": "in",
                    "values": ["repo.destroy", "repo.rename"],
                },
                {"field": "actor_is_bot", "op": "eq", "value": False},
            ],
            "aggregation": {
                "group_by": ["actor", "org"],
                "having_count_gt": 3,
            },
            "window_minutes": 30,
        }
        rule = RuleDefinition(
            name="Complex rule",
            slug="complex-rule",
            category="anomaly",
            default_severity="high",
            default_confidence="high",
            logic_type="complex",
            logic_config=complex_config,
            created_by="author",
        )
        session.add(rule)
        await session.commit()

        fetched = await session.get(RuleDefinition, rule.id)
        assert fetched is not None
        assert fetched.logic_config == complex_config
        assert fetched.logic_config["conditions"][0]["values"] == [
            "repo.destroy",
            "repo.rename",
        ]
        assert fetched.logic_config["aggregation"]["having_count_gt"] == 3

    async def test_cascade_delete_versions(self, session: AsyncSession) -> None:
        rule = RuleDefinition(
            name="Cascade test",
            slug="cascade-test",
            category="test",
            default_severity="low",
            default_confidence="low",
            logic_type="simple",
            logic_config={},
            created_by="tester",
        )
        session.add(rule)
        await session.commit()

        session.add(
            RuleVersion(
                rule_id=rule.id,
                version=1,
                logic_config={},
                changed_by="tester",
            )
        )
        await session.commit()

        # Load the relationship so the ORM cascade can find children.
        await session.refresh(rule, ["versions"])
        await session.delete(rule)
        await session.commit()

        orphans = (await session.execute(select(RuleVersion))).scalars().all()
        assert len(orphans) == 0
