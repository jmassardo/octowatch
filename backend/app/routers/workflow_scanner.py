"""Workflow security scanner router.

Provides endpoints for scanning GitHub Actions workflow files, listing
findings, and retrieving suggested remediations.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.models.workflow_finding import WorkflowFinding
from app.services.workflow_scanner_service import WorkflowScannerService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])

_scanner = WorkflowScannerService()


# ── Request / Response schemas ───────────────────────────────────────────────


class ScanRequest(BaseModel):
    """Manual scan request."""

    yaml_content: str = Field(..., min_length=1, max_length=500_000)
    workflow_path: str = Field(default=".github/workflows/unknown.yml", max_length=500)
    repo: str = Field(default="", max_length=500)
    org: str = Field(default="", max_length=255)


class FindingResponse(BaseModel):
    """Serialised workflow finding."""

    id: int
    repo: str
    org: str
    workflow_path: str
    rule_id: str
    severity: str
    title: str
    description: str
    details: dict[str, Any]
    suggested_fix: str | None = None
    scanned_at: str


class ScanResultResponse(BaseModel):
    """Result of a manual workflow scan."""

    workflow_path: str
    score: int
    findings: list[dict[str, Any]]


class RepoScoreResponse(BaseModel):
    """Aggregated workflow security score for a repository."""

    repo: str
    org: str
    score: int
    finding_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/findings", response_model=list[FindingResponse])
async def list_findings(
    org: str | None = None,
    repo: str | None = None,
    severity: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> list[FindingResponse]:
    """List workflow security findings, optionally filtered by org/repo/severity."""
    stmt = select(WorkflowFinding).order_by(WorkflowFinding.scanned_at.desc()).limit(limit)
    if org:
        stmt = stmt.where(WorkflowFinding.org == org)
    if repo:
        stmt = stmt.where(WorkflowFinding.repo == repo)
    if severity:
        stmt = stmt.where(WorkflowFinding.severity == severity)

    result = await db.execute(stmt)
    findings = result.scalars().all()
    return [
        FindingResponse(
            id=f.id,
            repo=f.repo,
            org=f.org,
            workflow_path=f.workflow_path,
            rule_id=f.rule_id,
            severity=f.severity,
            title=f.title,
            description=f.description,
            details=f.details,
            suggested_fix=f.suggested_fix,
            scanned_at=str(f.scanned_at),
        )
        for f in findings
    ]


@router.get("/findings/{finding_id}/fix")
async def get_finding_fix(
    finding_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the suggested fix for a specific finding."""
    result = await db.execute(select(WorkflowFinding).where(WorkflowFinding.id == finding_id))
    finding = result.scalar_one_or_none()
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")

    return {
        "finding_id": finding.id,
        "rule_id": finding.rule_id,
        "suggested_fix": finding.suggested_fix or f"# No automatic fix for {finding.rule_id}",
    }


@router.post("/scan", response_model=ScanResultResponse, dependencies=[Depends(verify_csrf)])
async def manual_scan(
    payload: ScanRequest,
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ScanResultResponse:
    """Manually scan a workflow YAML for security issues.

    Findings are stored in the database and returned in the response.
    """
    scan_result = _scanner.scan_workflow(
        yaml_content=payload.yaml_content,
        workflow_path=payload.workflow_path,
        repo=payload.repo,
    )

    # Persist findings
    for finding in scan_result.findings:
        db_finding = WorkflowFinding(
            repo=payload.repo or "manual-scan",
            org=payload.org or "unknown",
            workflow_path=finding.workflow_path,
            rule_id=finding.rule_id,
            severity=finding.severity,
            title=finding.title,
            description=finding.description,
            details=finding.details,
            suggested_fix=finding.suggested_fix,
        )
        db.add(db_finding)

    await db.flush()

    return ScanResultResponse(
        workflow_path=scan_result.workflow_path,
        score=scan_result.score,
        findings=[
            {
                "rule_id": f.rule_id,
                "severity": f.severity,
                "title": f.title,
                "description": f.description,
                "suggested_fix": f.suggested_fix,
            }
            for f in scan_result.findings
        ],
    )


@router.get("/scores", response_model=list[RepoScoreResponse])
async def list_repo_scores(
    org: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> list[RepoScoreResponse]:
    """List repositories with their workflow security scores."""
    # Aggregate findings per repo
    stmt = (
        select(
            WorkflowFinding.repo,
            WorkflowFinding.org,
            func.count().label("finding_count"),
            func.count().filter(WorkflowFinding.severity == "critical").label("critical_count"),
            func.count().filter(WorkflowFinding.severity == "high").label("high_count"),
            func.count().filter(WorkflowFinding.severity == "medium").label("medium_count"),
            func.count().filter(WorkflowFinding.severity == "low").label("low_count"),
        )
        .group_by(WorkflowFinding.repo, WorkflowFinding.org)
        .order_by(func.count().desc())
        .limit(limit)
    )
    if org:
        stmt = stmt.where(WorkflowFinding.org == org)

    result = await db.execute(stmt)
    rows = result.fetchall()

    scores = []
    for r in rows:
        # Calculate score: 100 - weighted deductions
        deduction = (
            r.critical_count * 25 + r.high_count * 15 + r.medium_count * 10 + r.low_count * 5
        )
        score = max(0, 100 - deduction)
        scores.append(
            RepoScoreResponse(
                repo=r.repo,
                org=r.org,
                score=score,
                finding_count=r.finding_count,
                critical_count=r.critical_count,
                high_count=r.high_count,
                medium_count=r.medium_count,
                low_count=r.low_count,
            )
        )

    return scores
