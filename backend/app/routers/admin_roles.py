"""Admin roles router: CRUD for RBAC role definitions.

Provides endpoints for managing custom roles (create, read, update, delete).
System roles are read-only and cannot be modified or deleted.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.models.user import RbacRole, UserRoleAssignment
from app.schemas.rbac import (
    AvailablePermissionsResponse,
    RoleCreateRequest,
    RoleDetailResponse,
    RolePermissionSummary,
    RoleUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.permission_catalog import get_catalog, get_categories
from app.services.rbac_service import SYSTEM_ROLES, VALID_ACTIONS, VALID_RESOURCES
from app.utils.client_ip import get_client_ip

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/roles", tags=["admin-roles"])


@router.get("/permissions", response_model=AvailablePermissionsResponse)
@router.get("/permissions/catalog", response_model=AvailablePermissionsResponse)
async def list_available_permissions(
    current_user: AuthenticatedUser = Depends(require_permission("admin_roles", "view")),
) -> AvailablePermissionsResponse:
    """List the full permission catalog for role creation and editing."""
    return AvailablePermissionsResponse(
        permissions=get_catalog(),
        categories=get_categories(),
    )


def _validate_permissions(permissions: list[str]) -> list[str]:
    """Validate permission strings and return normalized list.

    Raises HTTPException if any permission is invalid.
    """
    errors: list[str] = []
    normalized: list[str] = []
    for perm in permissions:
        if perm == "*:*":
            errors.append("Cannot assign wildcard *:* to custom roles")
            continue
        parts = perm.split(":")
        if len(parts) != 2:
            errors.append(f"Invalid format: '{perm}' (must be resource:action)")
            continue
        resource, action = parts
        if resource != "*" and resource not in VALID_RESOURCES:
            errors.append(f"Invalid resource: '{resource}' in '{perm}'")
            continue
        if action != "*" and action not in VALID_ACTIONS:
            errors.append(f"Invalid action: '{action}' in '{perm}'")
            continue
        normalized.append(perm)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"errors": errors},
        )
    return sorted(set(normalized))


@router.get("", response_model=list[RolePermissionSummary])
async def list_roles(
    current_user: AuthenticatedUser = Depends(require_permission("admin_roles", "view")),
    db: AsyncSession = Depends(get_db),
) -> list[RolePermissionSummary]:
    """List all available RBAC roles with permission summaries."""
    result = await db.execute(select(RbacRole).order_by(RbacRole.is_system.desc(), RbacRole.name))
    roles = result.scalars().all()
    return [
        RolePermissionSummary(
            id=r.id,
            name=r.name,
            display_name=r.display_name,
            description=r.description,
            permission_count=len(r.permissions) if r.permissions else 0,
            is_system=r.is_system,
            is_custom=r.is_custom,
            created_at=r.created_at,
        )
        for r in roles
    ]


@router.get("/{role_id}", response_model=RoleDetailResponse)
async def get_role(
    role_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("admin_roles", "view")),
    db: AsyncSession = Depends(get_db),
) -> RoleDetailResponse:
    """Get detailed information about a specific role."""
    result = await db.execute(select(RbacRole).where(RbacRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Count assignments
    count_result = await db.execute(
        select(func.count())
        .select_from(UserRoleAssignment)
        .where(
            UserRoleAssignment.role_id == role_id,
            UserRoleAssignment.active.is_(True),
        )
    )
    assignment_count = count_result.scalar() or 0

    return RoleDetailResponse(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        permissions=role.permissions or [],
        is_system=role.is_system,
        is_custom=role.is_custom,
        created_at=role.created_at,
        updated_at=role.updated_at,
        assignment_count=assignment_count,
    )


@router.post(
    "",
    response_model=RoleDetailResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_role(
    payload: RoleCreateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_roles", "create")),
    db: AsyncSession = Depends(get_db),
) -> RoleDetailResponse:
    """Create a new custom role. Only super_admin can create roles."""
    # Validate role name doesn't conflict with system roles
    if payload.name in SYSTEM_ROLES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role name '{payload.name}' is reserved for system roles",
        )

    # Check for duplicate name
    existing = await db.execute(select(RbacRole).where(RbacRole.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role with name '{payload.name}' already exists",
        )

    # Validate permissions
    validated_perms = _validate_permissions(payload.permissions)

    role = RbacRole(
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        permissions=validated_perms,
        is_system=False,
        is_custom=True,
        created_at=datetime.now(UTC),
    )
    db.add(role)
    await db.flush()
    await db.refresh(role)

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="role.create",
        resource_type="rbac_role",
        resource_id=str(role.id),
        parameters={"name": role.name, "permissions": validated_perms},
    )

    return RoleDetailResponse(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        permissions=role.permissions or [],
        is_system=role.is_system,
        is_custom=role.is_custom,
        created_at=role.created_at,
        updated_at=role.updated_at,
        assignment_count=0,
    )


@router.patch(
    "/{role_id}",
    response_model=RoleDetailResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_role(
    role_id: int,
    payload: RoleUpdateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_roles", "edit")),
    db: AsyncSession = Depends(get_db),
) -> RoleDetailResponse:
    """Update a custom role's display name, description, or permissions."""
    result = await db.execute(select(RbacRole).where(RbacRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be modified",
        )

    if payload.display_name is not None:
        role.display_name = payload.display_name
    if payload.description is not None:
        role.description = payload.description
    if payload.permissions is not None:
        role.permissions = _validate_permissions(payload.permissions)
    role.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(role)

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="role.update",
        resource_type="rbac_role",
        resource_id=str(role_id),
        parameters={"name": role.name},
    )

    count_result = await db.execute(
        select(func.count())
        .select_from(UserRoleAssignment)
        .where(
            UserRoleAssignment.role_id == role_id,
            UserRoleAssignment.active.is_(True),
        )
    )
    assignment_count = count_result.scalar() or 0

    return RoleDetailResponse(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        permissions=role.permissions or [],
        is_system=role.is_system,
        is_custom=role.is_custom,
        created_at=role.created_at,
        updated_at=role.updated_at,
        assignment_count=assignment_count,
    )


@router.delete("/{role_id}", dependencies=[Depends(verify_csrf)])
async def delete_role(
    role_id: int,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_roles", "delete")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a custom role. Revokes all assignments first.

    System roles cannot be deleted.
    """
    result = await db.execute(select(RbacRole).where(RbacRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be deleted",
        )

    # Deactivate all assignments for this role
    assignments_result = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.role_id == role_id,
            UserRoleAssignment.active.is_(True),
        )
    )
    assignments = assignments_result.scalars().all()
    for assignment in assignments:
        assignment.active = False

    # Delete the role
    await db.delete(role)
    await db.flush()

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="role.delete",
        resource_type="rbac_role",
        resource_id=str(role_id),
        parameters={"name": role.name, "revoked_assignments": len(assignments)},
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
