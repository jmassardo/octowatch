"""Tests for team CRUD, membership management, and team-based RBAC.

Tests cover:
- Team CRUD (create, list, get, update, delete)
- Membership management (add/remove members)
- Team role assignment and removal
- Permission resolution with team roles (union behavior)
- Scope inheritance from teams
- Slug generation
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.models.team import Team, TeamMembership, TeamRoleAssignment
from app.routers.admin_teams import _slugify

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "admin-user", jti: str = "team-test-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 99999,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(roles: list[str] | None = None) -> str:
    return json.dumps(
        {
            "github_login": "admin-user",
            "github_id": 99999,
            "roles": roles or ["super_admin"],
            "scoped_orgs": [],
            "scoped_repos": [],
            "scope_type": "global",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_viewer_session() -> str:
    return json.dumps(
        {
            "github_login": "viewer-user",
            "github_id": 88888,
            "roles": ["viewer"],
            "scoped_orgs": ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db() -> AsyncMock:
    """Create a mock async DB session."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.fetchall.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.all.return_value = []
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _setup_app(mock_db: AsyncMock, mock_valkey: AsyncMock) -> FastAPI:
    """Build a test FastAPI app with admin_teams router and overridden deps."""
    from app.main import create_app

    app = create_app()
    app.state.db_pool_ready = False  # Disable AuditTrailMiddleware DB writes
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_valkey] = lambda: mock_valkey
    return app


# ─── Slug generation tests ───────────────────────────────────────────────────


class TestSlugify:
    def test_simple_name(self) -> None:
        assert _slugify("Security Team") == "security-team"

    def test_special_characters(self) -> None:
        assert _slugify("My Team!! (Test)") == "my-team-test"

    def test_already_slug(self) -> None:
        assert _slugify("my-team") == "my-team"

    def test_uppercase(self) -> None:
        assert _slugify("UPPER") == "upper"

    def test_empty_after_strip(self) -> None:
        assert _slugify("!!!") == "team"

    def test_numbers(self) -> None:
        assert _slugify("Team 42") == "team-42"


# ─── Team CRUD tests ─────────────────────────────────────────────────────────


class TestTeamCreate:
    def test_create_team_success(self) -> None:
        """POST /api/v1/admin/teams creates a team and returns 201."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        # scalar_one_or_none returns None (no duplicate)
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None),
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
                fetchall=MagicMock(return_value=[]),
                all=MagicMock(return_value=[]),
            )
        )

        # Simulate autoincrement: refresh sets the id on the team object
        async def mock_refresh(obj: Any) -> None:
            if isinstance(obj, Team):
                obj.id = 1
                obj.created_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.post(
            "/api/v1/admin/teams",
            json={"name": "Security Team", "description": "The security squad"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Security Team"
        assert data["slug"] == "security-team"
        assert data["members"] == []
        assert data["roles"] == []

    def test_create_team_duplicate(self) -> None:
        """POST /api/v1/admin/teams returns 409 for duplicate name."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        existing_team = MagicMock(spec=Team)
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=existing_team),
            )
        )

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.post(
            "/api/v1/admin/teams",
            json={"name": "Existing Team"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 409


class TestTeamList:
    def test_list_teams_empty(self) -> None:
        """GET /api/v1/admin/teams returns empty list."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                all=MagicMock(return_value=[]),
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
                fetchall=MagicMock(return_value=[]),
            )
        )

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.get(
            "/api/v1/admin/teams",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestTeamGet:
    def test_get_team_not_found(self) -> None:
        """GET /api/v1/admin/teams/{id} returns 404 for missing team."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.get(
            "/api/v1/admin/teams/999",
            cookies={"access_token": token},
        )
        assert resp.status_code == 404


class TestTeamUpdate:
    def test_update_team_not_found(self) -> None:
        """PATCH /api/v1/admin/teams/{id} returns 404 for missing team."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.patch(
            "/api/v1/admin/teams/999",
            json={"description": "Updated"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404


class TestTeamDelete:
    def test_delete_team_not_found(self) -> None:
        """DELETE /api/v1/admin/teams/{id} returns 404 for missing team."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.delete(
            "/api/v1/admin/teams/999",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404


# ─── Membership tests ────────────────────────────────────────────────────────


class TestTeamMembership:
    def test_add_member_team_not_found(self) -> None:
        """POST .../members returns 404 when team does not exist."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.post(
            "/api/v1/admin/teams/999/members",
            json={"user_login": "octocat"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404

    def test_remove_member_not_found(self) -> None:
        """DELETE .../members/{login} returns 404 when not a member."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.delete(
            "/api/v1/admin/teams/999/members/octocat",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404


# ─── Team Role Assignment tests ──────────────────────────────────────────────


class TestTeamRoleAssignment:
    def test_assign_role_team_not_found(self) -> None:
        """POST .../roles returns 404 when team does not exist."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.post(
            "/api/v1/admin/teams/999/roles",
            json={"role_id": 1},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404

    def test_remove_role_not_found(self) -> None:
        """DELETE .../roles/{role_id} returns 404 when assignment missing."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.delete(
            "/api/v1/admin/teams/999/roles/1",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404


# ─── Permission resolution with team roles ───────────────────────────────────


class TestTeamPermissionResolution:
    """Test that resolve_roles and resolve_permissions include team-inherited data."""

    @pytest.mark.asyncio
    async def test_resolve_roles_includes_team_roles(self) -> None:
        """resolve_roles should return union of personal + team roles."""
        mock_session = AsyncMock()

        # First call: personal roles returns ["viewer"]
        # Second call: team roles returns ["security_analyst"]
        personal_result = MagicMock()
        personal_result.fetchall.return_value = [("viewer",)]

        team_result = MagicMock()
        team_result.fetchall.return_value = [("security_analyst",)]

        mock_session.execute = AsyncMock(side_effect=[personal_result, team_result])

        from app.services.rbac_service import resolve_roles

        roles = await resolve_roles(mock_session, "testuser")
        assert set(roles) == {"viewer", "security_analyst"}

    @pytest.mark.asyncio
    async def test_resolve_roles_deduplicates(self) -> None:
        """If the same role exists personally and via team, it appears once."""
        mock_session = AsyncMock()

        personal_result = MagicMock()
        personal_result.fetchall.return_value = [("viewer",)]

        team_result = MagicMock()
        team_result.fetchall.return_value = [("viewer",)]

        mock_session.execute = AsyncMock(side_effect=[personal_result, team_result])

        from app.services.rbac_service import resolve_roles

        roles = await resolve_roles(mock_session, "testuser")
        assert roles == ["viewer"]

    @pytest.mark.asyncio
    async def test_resolve_permissions_includes_team_permissions(self) -> None:
        """resolve_permissions should merge personal and team permissions."""
        mock_session = AsyncMock()

        # Personal: dashboard:view
        personal_result = MagicMock()
        personal_result.fetchall.return_value = [(["dashboard:view"],)]

        # Team: detections:view, events:view
        team_result = MagicMock()
        team_result.fetchall.return_value = [(["detections:view", "events:view"],)]

        mock_session.execute = AsyncMock(side_effect=[personal_result, team_result])

        from app.services.rbac_service import resolve_permissions

        perms = await resolve_permissions(mock_session, "testuser")
        assert set(perms) == {"dashboard:view", "detections:view", "events:view"}


# ─── Scope inheritance from teams ─────────────────────────────────────────────


class TestTeamScopeInheritance:
    @pytest.mark.asyncio
    async def test_get_user_scope_includes_team_scopes(self) -> None:
        """get_user_scope should include org/repo scopes from team assignments."""
        mock_session = AsyncMock()

        # Personal assignments: org-scoped to "org-a"
        personal_assignments = MagicMock()
        personal_result_data = MagicMock()
        personal_result_data.scope_type = "org"
        personal_result_data.scope_value = "org-a"
        personal_assignments.scalars.return_value.all.return_value = [personal_result_data]

        # Team scopes: org_slug="org-b", repo_slugs=["org-b/repo1"]
        team_scopes = MagicMock()
        team_scopes.fetchall.return_value = [("org-b", ["org-b/repo1"])]

        mock_session.execute = AsyncMock(side_effect=[personal_assignments, team_scopes])

        from app.services.rbac_service import get_user_scope

        scope = await get_user_scope(mock_session, "testuser", ["viewer"])

        assert "org-a" in scope.scoped_orgs
        assert "org-b" in scope.scoped_orgs
        assert "org-b/repo1" in scope.scoped_repos


# ─── RBAC enforcement tests ──────────────────────────────────────────────────


class TestTeamRBACEnforcement:
    def test_viewer_cannot_create_team(self) -> None:
        """A viewer role should be denied when trying to create a team."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_viewer_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        # First execute call: check_permission (viewer doesn't have admin_teams:create)
        # The permission check resolves roles from DB — mock returns viewer's DB roles
        call_count = 0
        viewer_result = MagicMock()
        viewer_result.fetchall.return_value = [
            (["dashboard:view", "events:view", "detections:view"],)
        ]

        team_perms_result = MagicMock()
        team_perms_result.fetchall.return_value = []

        def _side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # First two calls are for permission resolution (personal + team)
                if call_count == 1:
                    return viewer_result
                return team_perms_result
            # Remaining calls for audit logging
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
            result.fetchall.return_value = []
            return result

        mock_db.execute = AsyncMock(side_effect=_side_effect)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        viewer_jwt = pyjwt.encode(
            {
                "sub": "viewer-user",
                "github_id": 88888,
                "jti": "viewer-jti",
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "iat": datetime.now(UTC),
            },
            SECRET,
            algorithm="HS256",
        )
        resp = client.post(
            "/api/v1/admin/teams",
            json={"name": "Hacker Team"},
            cookies={"access_token": viewer_jwt, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403


# ─── Model tests ─────────────────────────────────────────────────────────────


class TestTeamModel:
    def test_team_model_attributes(self) -> None:
        """Team model should have all required attributes."""
        team = Team(
            name="Test Team",
            slug="test-team",
            description="A test team",
            github_org="my-org",
            github_team_slug="my-team",
            auto_sync=False,
            created_by="admin",
        )
        assert team.name == "Test Team"
        assert team.slug == "test-team"
        assert team.description == "A test team"
        assert team.github_org == "my-org"
        assert team.github_team_slug == "my-team"
        assert team.auto_sync is False
        assert team.created_by == "admin"

    def test_team_membership_model(self) -> None:
        """TeamMembership model should have required attributes."""
        membership = TeamMembership(
            team_id=1,
            user_login="octocat",
            added_by="admin",
        )
        assert membership.team_id == 1
        assert membership.user_login == "octocat"
        assert membership.added_by == "admin"

    def test_team_role_assignment_model(self) -> None:
        """TeamRoleAssignment model should have required attributes."""
        assignment = TeamRoleAssignment(
            team_id=1,
            role_id=2,
            org_slug="my-org",
            repo_slugs=["my-org/repo1"],
            assigned_by="admin",
        )
        assert assignment.team_id == 1
        assert assignment.role_id == 2
        assert assignment.org_slug == "my-org"
        assert assignment.repo_slugs == ["my-org/repo1"]
        assert assignment.assigned_by == "admin"


# ─── Schema tests ────────────────────────────────────────────────────────────


class TestTeamSchemas:
    def test_team_create_request_valid(self) -> None:
        """TeamCreateRequest should accept valid input."""
        from app.schemas.team import TeamCreateRequest

        req = TeamCreateRequest(name="My Team", description="Test")
        assert req.name == "My Team"
        assert req.description == "Test"
        assert req.auto_sync is False

    def test_team_create_request_name_too_short(self) -> None:
        """TeamCreateRequest should reject names shorter than 2 chars."""
        from pydantic import ValidationError

        from app.schemas.team import TeamCreateRequest

        with pytest.raises(ValidationError):
            TeamCreateRequest(name="X")

    def test_team_update_request_partial(self) -> None:
        """TeamUpdateRequest should accept partial updates."""
        from app.schemas.team import TeamUpdateRequest

        req = TeamUpdateRequest(description="New desc")
        assert req.description == "New desc"
        assert req.name is None
        assert req.auto_sync is None

    def test_team_member_add_request_valid(self) -> None:
        """TeamMemberAddRequest should accept valid login."""
        from app.schemas.team import TeamMemberAddRequest

        req = TeamMemberAddRequest(user_login="octocat")
        assert req.user_login == "octocat"

    def test_team_role_assign_request_valid(self) -> None:
        """TeamRoleAssignRequest should accept valid role_id."""
        from app.schemas.team import TeamRoleAssignRequest

        req = TeamRoleAssignRequest(role_id=1, org_slug="my-org")
        assert req.role_id == 1
        assert req.org_slug == "my-org"

    def test_audit_log_entry_response(self) -> None:
        """AuditLogEntryResponse should accept valid data."""
        from app.schemas.team import AuditLogEntryResponse

        entry = AuditLogEntryResponse(
            id=1,
            timestamp=datetime.now(UTC),
            actor="admin",
            action="team.create",
            outcome="success",
        )
        assert entry.id == 1
        assert entry.actor == "admin"

    def test_audit_log_list_response(self) -> None:
        """AuditLogListResponse should compute has_more correctly."""
        from app.schemas.team import AuditLogListResponse

        resp = AuditLogListResponse(items=[], total=0, page=1, page_size=50, has_more=False)
        assert resp.total == 0
        assert resp.has_more is False
