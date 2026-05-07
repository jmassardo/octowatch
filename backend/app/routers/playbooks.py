"""Incident response playbook router.

Provides endpoints for managing playbook templates and executing playbooks
against detected threats.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.models.audit_trail import AuditTrail
from app.models.detection import Detection
from app.models.playbook import PlaybookExecution, PlaybookTemplate

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


# ── Request / Response schemas ───────────────────────────────────────────────


class PlaybookStepInput(BaseModel):
    """A single step in a playbook template."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    action_type: str = Field(default="manual", max_length=50)
    action_url: str | None = None
    required: bool = True


class CreateTemplateRequest(BaseModel):
    """Create a new playbook template."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    detection_categories: list[str] = Field(default_factory=list)
    steps: list[PlaybookStepInput] = Field(..., min_length=1)


class UpdateTemplateRequest(BaseModel):
    """Update an existing playbook template."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    detection_categories: list[str] | None = None
    steps: list[PlaybookStepInput] | None = None


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


class SkipStepRequest(BaseModel):
    """Skip a playbook step with a reason."""

    reason: str = Field(..., min_length=1, max_length=2000)


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


class PlaybookExecutionListResponse(BaseModel):
    """Paginated list of playbook executions."""

    items: list[PlaybookExecutionResponse]
    total: int


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/templates", response_model=list[PlaybookTemplateResponse])
async def list_templates(
    category: str | None = None,
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "view")),
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
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "view")),
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
    "/templates",
    response_model=PlaybookTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_template(
    payload: CreateTemplateRequest,
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "manage")),
    db: AsyncSession = Depends(get_db),
) -> PlaybookTemplateResponse:
    """Create a new playbook template (admin only)."""
    slug = _slugify(payload.name)

    # Check for slug conflicts
    existing = await db.execute(select(PlaybookTemplate).where(PlaybookTemplate.slug == slug))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template with slug '{slug}' already exists",
        )

    steps_data = [s.model_dump() for s in payload.steps]
    template = PlaybookTemplate(
        name=payload.name,
        slug=slug,
        description=payload.description,
        detection_categories=payload.detection_categories,
        steps=steps_data,
        created_by=current_user.github_login,
    )
    db.add(template)

    trail = AuditTrail(
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        action_type="playbook.template_created",
        resource_type="playbook_template",
        parameters={"template_name": payload.name, "slug": slug},
        outcome="success",
    )
    db.add(trail)

    await db.flush()
    await db.refresh(template)

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


@router.put(
    "/templates/{template_id}",
    response_model=PlaybookTemplateResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_template(
    template_id: int,
    payload: UpdateTemplateRequest,
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "manage")),
    db: AsyncSession = Depends(get_db),
) -> PlaybookTemplateResponse:
    """Update an existing playbook template."""
    result = await db.execute(select(PlaybookTemplate).where(PlaybookTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    if payload.name is not None:
        template.name = payload.name
        template.slug = _slugify(payload.name)
    if payload.description is not None:
        template.description = payload.description
    if payload.detection_categories is not None:
        template.detection_categories = payload.detection_categories
    if payload.steps is not None:
        template.steps = [s.model_dump() for s in payload.steps]

    trail = AuditTrail(
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        action_type="playbook.template_updated",
        resource_type="playbook_template",
        resource_id=str(template.id),
        parameters={"template_name": template.name},
        outcome="success",
    )
    db.add(trail)

    await db.flush()
    await db.refresh(template)

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


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_csrf)],
)
async def delete_template(
    template_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "manage")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a playbook template."""
    result = await db.execute(select(PlaybookTemplate).where(PlaybookTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    trail = AuditTrail(
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        action_type="playbook.template_deleted",
        resource_type="playbook_template",
        resource_id=str(template.id),
        parameters={"template_name": template.name},
        outcome="success",
    )
    db.add(trail)

    await db.delete(template)
    await db.flush()


@router.get("/executions", response_model=PlaybookExecutionListResponse)
async def list_executions(
    status_filter: str | None = Query(None, alias="status"),
    detection_id: int | None = None,
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "view")),
    db: AsyncSession = Depends(get_db),
) -> PlaybookExecutionListResponse:
    """List playbook executions with optional status/detection filters."""
    stmt = select(PlaybookExecution).order_by(PlaybookExecution.started_at.desc())
    count_stmt = select(func.count()).select_from(PlaybookExecution)

    if status_filter:
        stmt = stmt.where(PlaybookExecution.status == status_filter)
        count_stmt = count_stmt.where(PlaybookExecution.status == status_filter)
    if detection_id is not None:
        stmt = stmt.where(PlaybookExecution.detection_id == detection_id)
        count_stmt = count_stmt.where(PlaybookExecution.detection_id == detection_id)

    result = await db.execute(stmt)
    executions = result.scalars().all()

    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    return PlaybookExecutionListResponse(
        items=[
            PlaybookExecutionResponse(
                id=e.id,
                template_id=e.template_id,
                detection_id=e.detection_id,
                status=e.status,
                step_results=e.step_results,
                started_by=e.started_by,
                started_at=str(e.started_at),
                completed_at=str(e.completed_at) if e.completed_at else None,
            )
            for e in executions
        ],
        total=total,
    )


@router.post(
    "/execute",
    response_model=PlaybookExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def execute_playbook(
    payload: ExecutePlaybookRequest,
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "execute")),
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
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "view")),
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
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "execute")),
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
    "/executions/{execution_id}/skip-step",
    response_model=PlaybookExecutionResponse,
    dependencies=[Depends(verify_csrf)],
)
async def skip_step(
    execution_id: int,
    payload: SkipStepRequest,
    step_index: int = Query(..., ge=0),
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "execute")),
    db: AsyncSession = Depends(get_db),
) -> PlaybookExecutionResponse:
    """Skip a playbook step with a reason."""
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
        "completed": True,
        "skipped": True,
        "skip_reason": payload.reason,
        "completed_by": current_user.github_login,
        "completed_at": datetime.now(UTC).isoformat(),
    }

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
    current_user: AuthenticatedUser = Depends(require_permission("playbooks", "execute")),
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
