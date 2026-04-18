"""Copilot governance policy router.

CRUD for governance policies and violation listing.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.models.copilot_policy import CopilotPolicy
from app.services.copilot_governance_service import CopilotGovernanceService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/copilot/governance", tags=["copilot"])

_service = CopilotGovernanceService()


# ── Request / Response schemas ───────────────────────────────────────────────


class PolicyCreateRequest(BaseModel):
    """Create a new governance policy."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    policy_type: str = Field(
        ...,
        pattern=r"^(acceptance_threshold|seat_classification|usage_frequency)$",
    )
    config: dict[str, Any] = Field(default_factory=dict)
    severity: str = Field(default="medium", pattern=r"^(critical|high|medium|low|info)$")


class PolicyUpdateRequest(BaseModel):
    """Update an existing governance policy."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    severity: str | None = Field(None, pattern=r"^(critical|high|medium|low|info)$")


class PolicyResponse(BaseModel):
    """Serialised governance policy."""

    id: int
    name: str
    description: str | None = None
    policy_type: str
    config: dict[str, Any]
    enabled: bool
    severity: str
    created_by: str
    created_at: str
    updated_at: str


class ViolationResponse(BaseModel):
    """Serialised policy violation."""

    id: int
    policy_id: int
    policy_name: str = ""
    severity: str = "medium"
    actor: str | None = None
    org: str | None = None
    description: str = ""
    context_data: dict[str, Any] = {}
    detected_at: str
    status: str = "open"
    detection_id: int | None = None


class ViolationsListResponse(BaseModel):
    """Wrapped violation list with total count."""

    violations: list[ViolationResponse]
    total: int


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/policies", response_model=list[PolicyResponse])
async def list_policies(
    enabled_only: bool = Query(default=False),
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> list[PolicyResponse]:
    """List all Copilot governance policies."""
    policies = await _service.list_policies(db, enabled_only=enabled_only)
    return [
        PolicyResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            policy_type=p.policy_type,
            config=p.config,
            enabled=p.enabled,
            severity=p.severity,
            created_by=p.created_by,
            created_at=str(p.created_at),
            updated_at=str(p.updated_at),
        )
        for p in policies
    ]


@router.post(
    "/policies",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_policy(
    payload: PolicyCreateRequest,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    """Create a new Copilot governance policy."""
    policy = await _service.create_policy(
        db,
        name=payload.name,
        description=payload.description,
        policy_type=payload.policy_type,
        config=payload.config,
        severity=payload.severity,
        created_by=current_user.github_login,
    )
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        policy_type=policy.policy_type,
        config=policy.config,
        enabled=policy.enabled,
        severity=policy.severity,
        created_by=policy.created_by,
        created_at=str(policy.created_at),
        updated_at=str(policy.updated_at),
    )


@router.patch(
    "/policies/{policy_id}",
    response_model=PolicyResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_policy(
    policy_id: int,
    payload: PolicyUpdateRequest,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    """Update a Copilot governance policy."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    policy = await _service.update_policy(db, policy_id, updates=updates)
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return PolicyResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        policy_type=policy.policy_type,
        config=policy.config,
        enabled=policy.enabled,
        severity=policy.severity,
        created_by=policy.created_by,
        created_at=str(policy.created_at),
        updated_at=str(policy.updated_at),
    )


@router.delete("/policies/{policy_id}", dependencies=[Depends(verify_csrf)])
async def delete_policy(
    policy_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Delete a Copilot governance policy."""
    deleted = await _service.delete_policy(db, policy_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return {"deleted": True}


@router.get("/violations", response_model=ViolationsListResponse)
async def list_violations(
    policy_id: int | None = None,
    severity: str | None = Query(default=None, pattern=r"^(critical|high|medium|low|info)$"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> ViolationsListResponse:
    """List Copilot governance policy violations."""
    violations = await _service.list_violations(db, policy_id=policy_id, limit=limit)

    # Build policy lookup for names and severity
    policy_ids = {v.policy_id for v in violations}
    policy_lookup: dict[int, CopilotPolicy] = {}
    if policy_ids:
        policies = await _service.list_policies(db)
        policy_lookup = {p.id: p for p in policies if p.id in policy_ids}

    items = []
    for v in violations:
        policy = policy_lookup.get(v.policy_id)
        details = v.violation_details or {}
        items.append(
            ViolationResponse(
                id=v.id,
                policy_id=v.policy_id,
                policy_name=policy.name if policy else "",
                severity=policy.severity if policy else "medium",
                actor=v.actor_login,
                org=details.get("org"),
                description=details.get("description", ""),
                context_data=details,
                detected_at=str(v.created_at),
                status=details.get("status", "open"),
                detection_id=v.detection_id,
            )
        )
    if severity:
        items = [v for v in items if v.severity == severity]
    return ViolationsListResponse(violations=items, total=len(items))
