"""Workflow security scanner router.

Provides endpoints for scanning GitHub Actions workflow files, listing
findings, retrieving suggested remediations, and viewing scanner activity.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.models.workflow_finding import WorkflowFinding
from app.models.workflow_scan_activity import WorkflowScanActivity
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
    recommendation: str | None = None
    snippet: str | None = None
    first_seen: str
    last_seen: str
    status: str = "open"


class FindingsListResponse(BaseModel):
    """Paginated list of findings."""

    findings: list[FindingResponse]
    total: int


class ScanStatusResponse(BaseModel):
    """Status of the automated workflow security scanner."""

    last_scan_at: datetime | None = None
    last_scan_status: str | None = None
    total_scans: int = 0
    total_findings: int = 0
    repos_scanned: int = 0
    next_scheduled_scan: str = "Runs every 6 hours and on new audit-log events"
    is_automated: bool = True


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


@router.get("/findings", response_model=FindingsListResponse)
async def list_findings(
    org: str | None = None,
    repo: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(require_permission("workflow_security", "view")),
    db: AsyncSession = Depends(get_db),
) -> FindingsListResponse:
    """List workflow security findings, optionally filtered by org/repo/severity."""
    offset = (page - 1) * page_size
    stmt = (
        select(WorkflowFinding)
        .order_by(WorkflowFinding.scanned_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if org:
        stmt = stmt.where(WorkflowFinding.org == org)
    if repo:
        stmt = stmt.where(WorkflowFinding.repo == repo)
    if severity:
        stmt = stmt.where(WorkflowFinding.severity == severity)

    result = await db.execute(stmt)
    findings = result.scalars().all()

    # Build count query for total (same filters, no limit)
    count_stmt = select(func.count()).select_from(WorkflowFinding)
    if org:
        count_stmt = count_stmt.where(WorkflowFinding.org == org)
    if repo:
        count_stmt = count_stmt.where(WorkflowFinding.repo == repo)
    if severity:
        count_stmt = count_stmt.where(WorkflowFinding.severity == severity)
    total = (await db.execute(count_stmt)).scalar() or 0

    return FindingsListResponse(
        findings=[
            FindingResponse(
                id=f.id,
                repo=f.repo,
                org=f.org,
                workflow_path=f.workflow_path,
                rule_id=f.rule_id,
                severity=f.severity,
                title=f.title,
                description=f.description,
                recommendation=f.suggested_fix,
                snippet=f.details.get("snippet") if isinstance(f.details, dict) else None,
                first_seen=str(f.scanned_at),
                last_seen=str(f.scanned_at),
                status="open",
            )
            for f in findings
        ],
        total=total,
    )


@router.get("/scan-status", response_model=ScanStatusResponse)
async def get_scan_status(
    current_user: AuthenticatedUser = Depends(require_permission("workflow_security", "view")),
    db: AsyncSession = Depends(get_db),
) -> ScanStatusResponse:
    """Return the current status of the automated workflow scanner.

    Reports the most recent scan time, total scan count, total findings, and
    the number of distinct repositories with findings.  No GitHub API calls are
    made — all data comes from the database.
    """
    # Latest activity record
    latest_stmt = (
        select(WorkflowScanActivity).order_by(WorkflowScanActivity.started_at.desc()).limit(1)
    )
    latest = (await db.execute(latest_stmt)).scalar_one_or_none()

    # Total scans
    total_scans = (
        await db.execute(select(func.count()).select_from(WorkflowScanActivity))
    ).scalar() or 0

    # Total open findings
    total_findings = (
        await db.execute(select(func.count()).select_from(WorkflowFinding))
    ).scalar() or 0

    # Distinct repos with findings
    repos_scanned = (
        await db.execute(select(func.count(func.distinct(WorkflowFinding.repo))))
    ).scalar() or 0

    return ScanStatusResponse(
        last_scan_at=latest.started_at if latest else None,
        last_scan_status=latest.status if latest else None,
        total_scans=total_scans,
        total_findings=total_findings,
        repos_scanned=repos_scanned,
    )


@router.get("/findings/{finding_id}/fix")
async def get_finding_fix(
    finding_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("workflow_security", "view")),
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
    current_user: AuthenticatedUser = Depends(require_permission("workflow_security", "view")),
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
    current_user: AuthenticatedUser = Depends(require_permission("workflow_security", "view")),
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


@router.post("/scan-repos", dependencies=[Depends(verify_csrf)])
async def trigger_repo_scan(
    current_user: AuthenticatedUser = Depends(require_permission("workflow_security", "view")),
) -> dict[str, str]:
    """Queue analysis of workflow audit-log events for security issues.

    No GitHub API calls are made — analyses events already in the database.
    """
    from app.celery_app import celery_app

    result = celery_app.send_task(
        "app.workers.workflow_scan_worker.scan_all_workflows",
        queue="baseline",
    )
    return {"task_id": result.id, "status": "queued"}


# ── Scanner Activity schemas and endpoint ────────────────────────────────────


class ScanActivityResponse(BaseModel):
    """Single scan activity record."""

    id: int
    trigger_event_ids: list[int]
    org: str
    repo: str
    workflow_path: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    checks_performed: list[str]
    findings_count: int
    data_sources: list[str]
    duration_ms: int | None = None


class ScanActivityListResponse(BaseModel):
    """Paginated list of scan activity records."""

    items: list[ScanActivityResponse]
    total: int


@router.get("/activity", response_model=ScanActivityListResponse)
async def list_scan_activity(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("workflow_scanner", "view")),
) -> ScanActivityListResponse:
    """List recent scanner activity with provenance."""
    offset = (page - 1) * page_size

    count_stmt = select(func.count()).select_from(WorkflowScanActivity)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(WorkflowScanActivity)
        .order_by(WorkflowScanActivity.started_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    activities = result.scalars().all()

    return ScanActivityListResponse(
        items=[
            ScanActivityResponse(
                id=a.id,
                trigger_event_ids=a.trigger_event_ids or [],
                org=a.org,
                repo=a.repo,
                workflow_path=a.workflow_path,
                started_at=a.started_at,
                completed_at=a.completed_at,
                status=a.status,
                checks_performed=a.checks_performed or [],
                findings_count=a.findings_count,
                data_sources=a.data_sources or [],
                duration_ms=a.duration_ms,
            )
            for a in activities
        ],
        total=total,
    )
