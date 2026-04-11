"""Incident response playbook router.

Provides endpoints for managing playbook templates and executing playbooks
against detected threats.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.models.audit_trail import AuditTrail
from app.models.detection import Detection
from app.models.playbook import PlaybookExecution, PlaybookTemplate

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


# ── Request / Response schemas ───────────────────────────────────────────────


class PlaybookTemplateResponse(BaseModel):
    """Serialised playbook template."""

    id: int
    name: str
    slug: str
    description: str | None = None
    detection_categories: list[str]
    steps: list[dict[str, Any]]
    created_by: str
    created_at: str
    updated_at: str


class ExecutePlaybookRequest(BaseModel):
    """Start a playbook execution."""

    template_id: int
    detection_id: int


class StepCompleteRequest(BaseModel):
    """Mark a playbook step as complete."""

    completed: bool = True
    notes: str = Field(default="", max_length=2000)


class PlaybookExecutionResponse(BaseModel):
    """Serialised playbook execution."""

    id: int
    template_id: int
    detection_id: int
    status: str
    step_results: list[dict[str, Any]]
    started_by: str
    started_at: str
    completed_at: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/templates", response_model=list[PlaybookTemplateResponse])
async def list_templates(
    category: str | None = None,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> list[PlaybookTemplateResponse]:
    """List playbook templates, optionally filtered by detection category."""
    stmt = select(PlaybookTemplate).order_by(PlaybookTemplate.name)
    if category:
        stmt = stmt.where(PlaybookTemplate.detection_categories.contains([category]))
    result = await db.execute(stmt)
    templates = result.scalars().all()
    return [
        PlaybookTemplateResponse(
            id=t.id,
            name=t.name,
            slug=t.slug,
            description=t.description,
            detection_categories=t.detection_categories,
            steps=t.steps,
            created_by=t.created_by,
            created_at=str(t.created_at),
            updated_at=str(t.updated_at),
        )
        for t in templates
    ]


@router.get("/templates/{template_id}", response_model=PlaybookTemplateResponse)
async def get_template(
    template_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> PlaybookTemplateResponse:
    """Get a single playbook template by ID."""
    result = await db.execute(select(PlaybookTemplate).where(PlaybookTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return PlaybookTemplateResponse(
        id=template.id,
        name=template.name,
        slug=template.slug,
        description=template.description,
        detection_categories=template.detection_categories,
        steps=template.steps,
        created_by=template.created_by,
        created_at=str(template.created_at),
        updated_at=str(template.updated_at),
    )


@router.post(
    "/execute",
    response_model=PlaybookExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def execute_playbook(
    payload: ExecutePlaybookRequest,
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> PlaybookExecutionResponse:
    """Start a playbook execution for a detection."""
    # Verify template exists
    template_result = await db.execute(
        select(PlaybookTemplate).where(PlaybookTemplate.id == payload.template_id)
    )
    template = template_result.scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Playbook template not found"
        )

    # Verify detection exists
    detection_result = await db.execute(
        select(Detection).where(Detection.id == payload.detection_id)
    )
    detection = detection_result.scalar_one_or_none()
    if detection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")

    # Initialise step results from template steps
    step_results = [
        {
            "step_index": i,
            "title": step.get("title", f"Step {i + 1}"),
            "completed": False,
            "notes": "",
        }
        for i, step in enumerate(template.steps)
    ]

    execution = PlaybookExecution(
        template_id=template.id,
        detection_id=detection.id,
        status="in_progress",
        step_results=step_results,
        started_by=current_user.github_login,
    )
    db.add(execution)

    # Update detection status to investigating
    if detection.status == "open":
        detection.status = "investigating"

    # Audit trail
    trail = AuditTrail(
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        action_type="playbook.started",
        resource_type="playbook_execution",
        parameters={
            "template_id": template.id,
            "template_name": template.name,
            "detection_id": detection.id,
        },
        outcome="success",
    )
    db.add(trail)

    await db.flush()
    await db.refresh(execution)

    return PlaybookExecutionResponse(
        id=execution.id,
        template_id=execution.template_id,
        detection_id=execution.detection_id,
        status=execution.status,
        step_results=execution.step_results,
        started_by=execution.started_by,
        started_at=str(execution.started_at),
        completed_at=str(execution.completed_at) if execution.completed_at else None,
    )


@router.get("/executions/{execution_id}", response_model=PlaybookExecutionResponse)
async def get_execution(
    execution_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> PlaybookExecutionResponse:
    """Get a playbook execution by ID."""
    result = await db.execute(select(PlaybookExecution).where(PlaybookExecution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return PlaybookExecutionResponse(
        id=execution.id,
        template_id=execution.template_id,
        detection_id=execution.detection_id,
        status=execution.status,
        step_results=execution.step_results,
        started_by=execution.started_by,
        started_at=str(execution.started_at),
        completed_at=str(execution.completed_at) if execution.completed_at else None,
    )


@router.patch(
    "/executions/{execution_id}/steps/{step_index}",
    response_model=PlaybookExecutionResponse,
    dependencies=[Depends(verify_csrf)],
)
async def complete_step(
    execution_id: int,
    step_index: int,
    payload: StepCompleteRequest,
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> PlaybookExecutionResponse:
    """Mark a playbook step as complete with optional notes."""
    result = await db.execute(select(PlaybookExecution).where(PlaybookExecution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    if execution.status not in ("pending", "in_progress"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify execution in '{execution.status}' state",
        )

    steps = list(execution.step_results)
    if step_index < 0 or step_index >= len(steps):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid step index {step_index}",
        )

    steps[step_index] = {
        **steps[step_index],
        "completed": payload.completed,
        "notes": payload.notes,
        "completed_by": current_user.github_login,
        "completed_at": datetime.now(UTC).isoformat(),
    }

    # Update via raw update to handle JSONB properly
    execution.step_results = steps
    await db.flush()
    await db.refresh(execution)

    return PlaybookExecutionResponse(
        id=execution.id,
        template_id=execution.template_id,
        detection_id=execution.detection_id,
        status=execution.status,
        step_results=execution.step_results,
        started_by=execution.started_by,
        started_at=str(execution.started_at),
        completed_at=str(execution.completed_at) if execution.completed_at else None,
    )


@router.post(
    "/executions/{execution_id}/complete",
    response_model=PlaybookExecutionResponse,
    dependencies=[Depends(verify_csrf)],
)
async def complete_execution(
    execution_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> PlaybookExecutionResponse:
    """Finalise a playbook execution and auto-resolve the associated detection."""
    result = await db.execute(select(PlaybookExecution).where(PlaybookExecution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    if execution.status in ("completed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Execution already in '{execution.status}' state",
        )

    now = datetime.now(UTC)
    execution.status = "completed"
    execution.completed_at = now

    # Auto-resolve the associated detection
    await db.execute(
        update(Detection)
        .where(Detection.id == execution.detection_id)
        .values(
            status="resolved",
            resolved_at=now,
            resolved_by=current_user.github_login,
            resolution_note=f"Resolved via playbook execution #{execution.id}",
        )
    )

    # Audit trail
    trail = AuditTrail(
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        action_type="playbook.completed",
        resource_type="playbook_execution",
        resource_id=str(execution.id),
        parameters={
            "execution_id": execution.id,
            "detection_id": execution.detection_id,
        },
        outcome="success",
    )
    db.add(trail)

    await db.flush()
    await db.refresh(execution)

    return PlaybookExecutionResponse(
        id=execution.id,
        template_id=execution.template_id,
        detection_id=execution.detection_id,
        status=execution.status,
        step_results=execution.step_results,
        started_by=execution.started_by,
        started_at=str(execution.started_at),
        completed_at=str(execution.completed_at) if execution.completed_at else None,
    )
