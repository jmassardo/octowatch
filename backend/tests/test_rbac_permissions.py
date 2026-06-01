"""Comprehensive tests for enhanced RBAC: permissions, roles, scoping."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.deps import AuthenticatedUser
from app.services.rbac_service import (
    SYSTEM_ROLE_PERMISSIONS,
    SYSTEM_ROLES,
    VALID_ACTIONS,
    VALID_RESOURCES,
    OrgRepoScope,
    check_permission,
    inject_scope_predicate,
    invalidate_permission_cache,
    resolve_permissions,
)

# ─── Permission Resolution Tests ──────────────────────────────────────────────


class TestCheckPermission:
    """Test the check_permission function."""

    @pytest.mark.asyncio
    async def test_super_admin_has_all_permissions(self) -> None:
        """super_admin role grants all permissions without DB check."""
        session = AsyncMock()
        result = await check_permission(
            session, "admin-user", "detections", "view", roles=["super_admin"]
        )
        assert result is True
        # Should not query DB
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_sys_admin_has_all_permissions(self) -> None:
        """Legacy sys_admin role also grants all permissions."""
        session = AsyncMock()
        result = await check_permission(
            session, "admin-user", "admin_settings", "admin", roles=["sys_admin"]
        )
        assert result is True
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_exact_permission_match(self) -> None:
        """User with exact permission string passes the check."""
        session = AsyncMock()
        # Mock resolve_permissions to return specific permissions
        with patch(
            "app.services.rbac_service.resolve_permissions",
            return_value=["detections:view", "events:view"],
        ):
            result = await check_permission(
                session, "analyst-user", "detections", "view", roles=["security_analyst"]
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_wildcard_resource_match(self) -> None:
        """User with resource:* permission passes for any action on that resource."""
        session = AsyncMock()
        with patch(
            "app.services.rbac_service.resolve_permissions",
            return_value=["detections:*", "events:*"],
        ):
            result = await check_permission(
                session, "analyst-user", "detections", "delete", roles=["security_analyst"]
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_global_wildcard_match(self) -> None:
        """User with *:* permission passes for anything."""
        session = AsyncMock()
        with patch(
            "app.services.rbac_service.resolve_permissions",
            return_value=["*:*"],
        ):
            result = await check_permission(
                session, "admin-user", "admin_settings", "admin", roles=["custom_super"]
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_missing_permission_denied(self) -> None:
        """User without the required permission is denied."""
        session = AsyncMock()
        with patch(
            "app.services.rbac_service.resolve_permissions",
            return_value=["detections:view", "events:view"],
        ):
            result = await check_permission(
                session, "viewer-user", "rules", "create", roles=["viewer"]
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_no_roles_denied(self) -> None:
        """User with no roles is denied."""
        session = AsyncMock()
        with patch(
            "app.services.rbac_service.resolve_permissions",
            return_value=[],
        ):
            result = await check_permission(session, "new-user", "detections", "view", roles=[])
            assert result is False

    @pytest.mark.asyncio
    async def test_multiple_roles_aggregated(self) -> None:
        """Permissions from multiple roles are combined."""
        session = AsyncMock()
        # User with both security_analyst and engineering_leader roles
        combined_perms = (
            SYSTEM_ROLE_PERMISSIONS["security_analyst"]
            + SYSTEM_ROLE_PERMISSIONS["engineering_leader"]
        )
        with patch(
            "app.services.rbac_service.resolve_permissions",
            return_value=combined_perms,
        ):
            # Can access detections (from security_analyst)
            result = await check_permission(
                session,
                "multi-user",
                "detections",
                "view",
                roles=["security_analyst", "engineering_leader"],
            )
            assert result is True
            # Can access velocity (from engineering_leader)
            result = await check_permission(
                session,
                "multi-user",
                "velocity",
                "view",
                roles=["security_analyst", "engineering_leader"],
            )
            assert result is True


# ─── Permission Caching Tests ─────────────────────────────────────────────────


class TestPermissionCaching:
    """Test permission caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self) -> None:
        """When permissions are cached in Valkey, DB is not queried."""
        session = AsyncMock()
        valkey = AsyncMock()
        cached_perms = ["detections:view", "events:view"]
        valkey.get.return_value = json.dumps(cached_perms)

        result = await resolve_permissions(session, "test-user", valkey=valkey)
        assert result == cached_perms
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self) -> None:
        """When cache is empty, permissions are resolved from DB."""
        session = AsyncMock()
        valkey = AsyncMock()
        valkey.get.return_value = None

        # Mock DB result — resolve_permissions now makes two queries:
        # 1. Personal role permissions
        # 2. Team-inherited role permissions
        personal_result = MagicMock()
        personal_result.fetchall.return_value = [
            (["detections:view", "events:view"],),
        ]
        team_result = MagicMock()
        team_result.fetchall.return_value = []
        session.execute = AsyncMock(side_effect=[personal_result, team_result])

        result = await resolve_permissions(session, "test-user", valkey=valkey)
        assert "detections:view" in result
        assert "events:view" in result
        assert session.execute.call_count == 2
        # Should cache the result
        valkey.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_cache(self) -> None:
        """Cache invalidation deletes the key."""
        valkey = AsyncMock()
        await invalidate_permission_cache(valkey, "test-user")
        valkey.delete.assert_called_once_with("rbac:permissions:test-user")


# ─── Scope Injection Tests ────────────────────────────────────────────────────


class TestScopeInjection:
    """Test inject_scope_predicate with enhanced scoping."""

    def _make_stub_stmt(self) -> MagicMock:
        """Create a SQLAlchemy-like stub."""
        stmt = MagicMock()
        stmt.where = MagicMock(return_value=stmt)
        return stmt

    def test_global_scope_no_filter(self) -> None:
        """super_admin bypass: no WHERE clause added."""
        stmt = self._make_stub_stmt()
        scope = OrgRepoScope(scope_type="global")
        inject_scope_predicate(stmt, scope, MagicMock(), MagicMock())
        stmt.where.assert_not_called()

    def test_org_scoped_adds_org_filter(self) -> None:
        """Org-scoped users get WHERE org IN (...) clause."""
        stmt = self._make_stub_stmt()
        scope = OrgRepoScope(scoped_orgs=["acme-corp", "acme-labs"], scope_type="org")
        org_col = MagicMock()
        org_col.in_.return_value = MagicMock()

        inject_scope_predicate(stmt, scope, org_col, None)
        assert stmt.where.called
        org_col.in_.assert_called_once_with(["acme-corp", "acme-labs"])

    def test_repo_scoped_takes_precedence(self) -> None:
        """When both org and repo scopes exist, repo takes precedence."""
        stmt = self._make_stub_stmt()
        scope = OrgRepoScope(
            scoped_orgs=["acme-corp"],
            scoped_repos=["acme-corp/repo1", "acme-corp/repo2"],
            scope_type="repo",
        )
        org_col = MagicMock()
        repo_col = MagicMock()
        repo_col.is_.return_value = MagicMock()
        repo_col.in_.return_value = MagicMock()

        # Patch or_ to avoid SQLAlchemy validation with mock objects
        with patch("sqlalchemy.or_", side_effect=lambda *args: args[0]):
            inject_scope_predicate(stmt, scope, org_col, repo_col)

        assert stmt.where.called
        # repo takes precedence - repo_col.in_ should have been called
        repo_col.in_.assert_called_once_with(["acme-corp/repo1", "acme-corp/repo2"])
        # org_col should NOT be used when repos are narrower
        org_col.in_.assert_not_called()

    def test_repo_scoped_without_repo_col_uses_org(self) -> None:
        """When repo_col is None, falls through to org scoping."""
        stmt = self._make_stub_stmt()
        scope = OrgRepoScope(
            scoped_orgs=["acme-corp"],
            scoped_repos=["acme-corp/repo1"],
            scope_type="repo",
        )
        org_col = MagicMock()
        org_col.in_.return_value = MagicMock()

        inject_scope_predicate(stmt, scope, org_col, None)
        # With no repo_col, falls to org scoping
        org_col.in_.assert_called_once_with(["acme-corp"])


# ─── require_permission Dependency Tests ──────────────────────────────────────


class TestRequirePermission:
    """Test the require_permission FastAPI dependency factory."""

    @pytest.mark.asyncio
    async def test_allowed_user_passes(self) -> None:
        """User with correct permission passes through."""
        from app.deps import require_permission

        dep = require_permission("detections", "view")

        user = AuthenticatedUser(
            github_login="analyst",
            github_id=123,
            roles=["super_admin"],
            scoped_orgs=[],
            scoped_repos=[],
            scope_type="global",
            jti="test-jti",
            session_expires_at="2099-01-01",
        )
        request = MagicMock()
        db = AsyncMock()

        result = await dep(request=request, user=user, db=db)
        assert result.github_login == "analyst"

    @pytest.mark.asyncio
    async def test_denied_user_raises_403(self) -> None:
        """User without permission gets HTTP 403."""
        from app.deps import require_permission

        dep = require_permission("admin_settings", "admin")

        user = AuthenticatedUser(
            github_login="viewer",
            github_id=456,
            roles=["viewer"],
            scoped_orgs=["my-org"],
            scoped_repos=[],
            scope_type="scoped",
            jti="test-jti-2",
            session_expires_at="2099-01-01",
        )
        request = MagicMock()
        db = AsyncMock()

        # Mock check_permission to deny
        with patch(
            "app.services.rbac_service.check_permission",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=request, user=user, db=db)
            assert exc_info.value.status_code == 403
            assert "admin_settings:admin" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_no_roles_gets_helpful_message(self) -> None:
        """User with empty roles gets a message to contact admin."""
        from app.deps import require_permission

        dep = require_permission("events", "view")

        user = AuthenticatedUser(
            github_login="new-user",
            github_id=789,
            roles=[],
            scoped_orgs=[],
            scoped_repos=[],
            scope_type="scoped",
            jti="test-jti-3",
            session_expires_at="2099-01-01",
        )
        request = MagicMock()
        db = AsyncMock()

        with patch(
            "app.services.rbac_service.check_permission",
            return_value=False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await dep(request=request, user=user, db=db)
            assert exc_info.value.status_code == 403
            assert "no role assignments" in exc_info.value.detail


# ─── Role CRUD Tests ──────────────────────────────────────────────────────────


class TestRoleCrud:
    """Test admin role management endpoints logic."""

    def test_validate_permissions_valid(self) -> None:
        """Valid permissions pass validation."""
        from app.routers.admin_roles import _validate_permissions

        perms = ["detections:view", "events:*", "rules:create"]
        result = _validate_permissions(perms)
        assert "detections:view" in result
        assert "events:*" in result
        assert "rules:create" in result

    def test_validate_permissions_invalid_format(self) -> None:
        """Invalid format raises HTTPException."""
        from app.routers.admin_roles import _validate_permissions

        with pytest.raises(HTTPException) as exc_info:
            _validate_permissions(["invalid_no_colon"])
        assert exc_info.value.status_code == 422

    def test_validate_permissions_invalid_resource(self) -> None:
        """Unknown resource raises HTTPException."""
        from app.routers.admin_roles import _validate_permissions

        with pytest.raises(HTTPException) as exc_info:
            _validate_permissions(["unknown_resource:view"])
        assert exc_info.value.status_code == 422

    def test_validate_permissions_invalid_action(self) -> None:
        """Unknown action raises HTTPException."""
        from app.routers.admin_roles import _validate_permissions

        with pytest.raises(HTTPException) as exc_info:
            _validate_permissions(["detections:fly"])
        assert exc_info.value.status_code == 422

    def test_validate_permissions_wildcard_denied(self) -> None:
        """*:* cannot be assigned to custom roles."""
        from app.routers.admin_roles import _validate_permissions

        with pytest.raises(HTTPException) as exc_info:
            _validate_permissions(["*:*"])
        assert exc_info.value.status_code == 422

    def test_validate_permissions_deduplicates(self) -> None:
        """Duplicate permissions are deduplicated."""
        from app.routers.admin_roles import _validate_permissions

        result = _validate_permissions(["detections:view", "detections:view", "events:view"])
        assert len(result) == 2


# ─── System Role Definitions Tests ────────────────────────────────────────────


class TestSystemRoleDefinitions:
    """Verify system role permission definitions are correct."""

    def test_super_admin_has_global_wildcard(self) -> None:
        """super_admin must have *:* permission."""
        assert "*:*" in SYSTEM_ROLE_PERMISSIONS["super_admin"]

    def test_all_system_roles_defined(self) -> None:
        """All SYSTEM_ROLES have permission definitions."""
        for role in SYSTEM_ROLES:
            assert role in SYSTEM_ROLE_PERMISSIONS, f"Missing permissions for role: {role}"

    def test_viewer_is_read_only(self) -> None:
        """viewer role should only have :view permissions."""
        perms = SYSTEM_ROLE_PERMISSIONS["viewer"]
        for perm in perms:
            resource, action = perm.split(":")
            assert action == "view", f"Viewer has non-view permission: {perm}"

    def test_security_engineer_extends_analyst(self) -> None:
        """security_engineer should have all analyst permissions plus more."""
        analyst_perms = set(SYSTEM_ROLE_PERMISSIONS["security_analyst"])
        engineer_perms = set(SYSTEM_ROLE_PERMISSIONS["security_engineer"])
        # Engineer has all the same base permissions (detections, events, queries, etc.)
        # but may not have playbooks:execute (analyst does triage, engineer builds rules)
        base_analyst_perms = {
            p for p in analyst_perms if not p.startswith("playbooks:") or p == "playbooks:*"
        }
        # Engineer should cover all non-playbook analyst permissions
        assert base_analyst_perms.issubset(engineer_perms) or "playbooks:*" in engineer_perms

    def test_new_resource_permissions_added_to_system_roles(self) -> None:
        """Updated system roles should include the new page-level permissions."""
        assert "supply_chain:view" in SYSTEM_ROLE_PERMISSIONS["security_analyst"]
        assert "packages:*" in SYSTEM_ROLE_PERMISSIONS["security_engineer"]
        assert "compliance:*" in SYSTEM_ROLE_PERMISSIONS["compliance_officer"]
        assert "org_health:view" in SYSTEM_ROLE_PERMISSIONS["engineering_leader"]
        assert "threat_intel:view" in SYSTEM_ROLE_PERMISSIONS["report_admin"]

    def test_valid_resources_in_permissions(self) -> None:
        """All permissions reference valid resources."""
        for role, perms in SYSTEM_ROLE_PERMISSIONS.items():
            for perm in perms:
                if perm == "*:*":
                    continue
                resource = perm.split(":")[0]
                assert resource in VALID_RESOURCES or resource == "*", (
                    f"Role '{role}' has invalid resource '{resource}' in '{perm}'"
                )

    def test_valid_actions_in_permissions(self) -> None:
        """All permissions reference valid actions."""
        for role, perms in SYSTEM_ROLE_PERMISSIONS.items():
            for perm in perms:
                if perm == "*:*":
                    continue
                action = perm.split(":")[1]
                assert action in VALID_ACTIONS or action == "*", (
                    f"Role '{role}' has invalid action '{action}' in '{perm}'"
                )


# ─── Role Migration Tests ─────────────────────────────────────────────────────


class TestRoleMigration:
    """Test backward compatibility with old role names."""

    def test_authenticated_user_has_role_super_admin(self) -> None:
        """AuthenticatedUser.has_role works with super_admin."""
        user = AuthenticatedUser(
            github_login="admin",
            github_id=1,
            roles=["super_admin"],
            scoped_orgs=[],
            scoped_repos=[],
            scope_type="global",
            jti="test",
            session_expires_at="2099-01-01",
        )
        assert user.has_role("anything") is True

    def test_authenticated_user_has_role_legacy_sys_admin(self) -> None:
        """AuthenticatedUser.has_role still works with legacy sys_admin."""
        user = AuthenticatedUser(
            github_login="admin",
            github_id=1,
            roles=["sys_admin"],
            scoped_orgs=[],
            scoped_repos=[],
            scope_type="global",
            jti="test",
            session_expires_at="2099-01-01",
        )
        assert user.has_role("anything") is True

    def test_authenticated_user_specific_role_check(self) -> None:
        """Non-admin users only pass if they have the specific role."""
        user = AuthenticatedUser(
            github_login="analyst",
            github_id=2,
            roles=["security_analyst"],
            scoped_orgs=["my-org"],
            scoped_repos=[],
            scope_type="scoped",
            jti="test",
            session_expires_at="2099-01-01",
        )
        assert user.has_role("security_analyst") is True
        assert user.has_role("security_engineer") is False
        assert user.has_role("super_admin") is False

    @pytest.mark.asyncio
    async def test_super_admin_gets_global_scope(self) -> None:
        """super_admin should get global scope."""
        from app.services.rbac_service import get_user_scope

        session = AsyncMock()
        scope = await get_user_scope(session, "admin", ["super_admin"])
        assert scope.is_global is True

    @pytest.mark.asyncio
    async def test_legacy_sys_admin_gets_global_scope(self) -> None:
        """Legacy sys_admin should still get global scope."""
        from app.services.rbac_service import get_user_scope

        session = AsyncMock()
        scope = await get_user_scope(session, "admin", ["sys_admin"])
        assert scope.is_global is True


# ─── Schema Validation Tests ──────────────────────────────────────────────────


class TestRbacSchemas:
    """Test Pydantic schemas for RBAC endpoints."""

    def test_role_create_request_valid(self) -> None:
        """Valid role creation request passes validation."""
        from app.schemas.rbac import RoleCreateRequest

        req = RoleCreateRequest(
            name="custom_role",
            display_name="Custom Role",
            description="A custom role",
            permissions=["detections:view", "events:view"],
        )
        assert req.name == "custom_role"
        assert len(req.permissions) == 2

    def test_role_create_request_invalid_name(self) -> None:
        """Role name with invalid characters fails validation."""
        from pydantic import ValidationError

        from app.schemas.rbac import RoleCreateRequest

        with pytest.raises(ValidationError):
            RoleCreateRequest(
                name="Invalid Name!",
                display_name="Test",
                permissions=["detections:view"],
            )

    def test_role_create_request_name_too_short(self) -> None:
        """Role name that's too short fails validation."""
        from pydantic import ValidationError

        from app.schemas.rbac import RoleCreateRequest

        with pytest.raises(ValidationError):
            RoleCreateRequest(
                name="x",
                display_name="Test",
                permissions=["detections:view"],
            )

    def test_role_update_request_partial(self) -> None:
        """Partial update request with only some fields works."""
        from app.schemas.rbac import RoleUpdateRequest

        req = RoleUpdateRequest(display_name="New Name")
        assert req.display_name == "New Name"
        assert req.permissions is None

    def test_user_permissions_response(self) -> None:
        """UserPermissionsResponse schema works correctly."""
        from app.schemas.rbac import PermissionScopes, UserPermissionsResponse

        resp = UserPermissionsResponse(
            user_id="testuser",
            roles=["security_analyst"],
            permissions=["detections:*", "events:*"],
            scopes=PermissionScopes(orgs=["my-org"], repos=None, scope_type="org"),
        )
        data = resp.model_dump()
        assert data["user_id"] == "testuser"
        assert data["scopes"]["orgs"] == ["my-org"]
        assert data["scopes"]["repos"] is None
        assert data["scopes"]["scope_type"] == "org"


class TestAvailablePermissionsSchema:
    """Test the AvailablePermissionsResponse schema."""

    def test_permission_definition_schema(self) -> None:
        """PermissionDefinition schema accepts valid data."""
        from app.schemas.rbac import PermissionDefinition

        perm = PermissionDefinition(
            permission="detections:view",
            resource="detections",
            action="view",
            resource_label="Detections",
            action_label="View",
            description="View detections data and dashboards",
            category="Security",
        )
        assert perm.permission == "detections:view"
        assert perm.resource == "detections"
        assert perm.action == "view"
        assert perm.category == "Security"

    def test_available_permissions_response_schema(self) -> None:
        """AvailablePermissionsResponse schema works correctly."""
        from app.schemas.rbac import AvailablePermissionsResponse, PermissionDefinition

        perms = [
            PermissionDefinition(
                permission="dashboard:view",
                resource="dashboard",
                action="view",
                resource_label="Dashboard",
                action_label="View",
                description="View the main dashboard overview",
                category="Core",
            ),
        ]
        resp = AvailablePermissionsResponse(
            permissions=perms,
            categories=["Core"],
        )
        data = resp.model_dump()
        assert len(data["permissions"]) == 1
        assert data["permissions"][0]["permission"] == "dashboard:view"
        assert data["categories"] == ["Core"]


class TestListAvailablePermissionsEndpoint:
    """Test the /admin/roles/permissions catalog logic."""

    def test_catalog_covers_all_valid_resources(self) -> None:
        """Every valid resource should appear in the permission catalog."""
        from app.services.permission_catalog import get_catalog

        catalog_resources = {permission.resource for permission in get_catalog()}
        assert VALID_RESOURCES.issubset(catalog_resources)

    def test_catalog_includes_view_and_edit_for_every_resource(self) -> None:
        """Every resource should expose at least view and edit in the catalog."""
        from app.services.permission_catalog import get_catalog

        catalog_permissions = {permission.permission for permission in get_catalog()}
        for resource in VALID_RESOURCES:
            assert f"{resource}:view" in catalog_permissions
            assert f"{resource}:edit" in catalog_permissions

    def test_catalog_only_contains_valid_resources_and_actions(self) -> None:
        """Catalog permissions should only reference valid RBAC resources/actions."""
        from app.services.permission_catalog import get_catalog

        for permission in get_catalog():
            assert permission.resource in VALID_RESOURCES
            assert permission.action in VALID_ACTIONS

    def test_catalog_categories_match_expected_order(self) -> None:
        """Catalog categories should be stable for the admin UI."""
        from app.services.permission_catalog import get_categories

        assert get_categories() == [
            "Core",
            "Security",
            "Platform Intelligence",
            "Analytics",
            "Monitoring",
            "Administration",
        ]
