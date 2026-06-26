"""Supply chain security router: posture, risks, rules, and workflow analysis.

Every endpoint enforces RBAC by resolving scoped_orgs from the database
(via ``rbac_service.get_scoped_orgs``) and returning HTTP 403 when the
user has no org access.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.services import rbac_service
from app.services import supply_chain_service as svc

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/supply-chain", tags=["supply-chain"])


# ── RBAC helper ──────────────────────────────────────────────────────────────


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty."""
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs and current_user.scope_type != "global":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


# ── Request / Response schemas ───────────────────────────────────────────────


class AnalyzeWorkflowRequest(BaseModel):
    """Request body for workflow analysis."""

    content: str = Field(..., min_length=1, max_length=500_000, description="Workflow YAML content")


class FindingResponse(BaseModel):
    """A single supply-chain finding."""

    rule_slug: str
    title: str
    severity: str
    confidence: str
    line: int | None
    detail: str
    recommendation: str


class AnalyzeWorkflowResponse(BaseModel):
    """Response for workflow analysis."""

    findings: list[FindingResponse]
    total_findings: int
    risk_level: str  # critical, high, medium, low, none


class PostureResponse(BaseModel):
    """Supply chain posture summary."""

    score: int
    unpinned_actions: int
    dependency_alerts: int
    risky_workflows: int
    rules_active: int
    total_detections: int
    critical_detections: int
    recent_risks: list[dict[str, Any]]


class RiskSummaryResponse(BaseModel):
    """Dependency risk summary."""

    total_risks: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    top_repos: list[dict[str, Any]]


class SupplyChainRuleResponse(BaseModel):
    """A supply-chain detection rule with detection count."""

    id: int
    name: str
    slug: str
    description: str | None
    severity: str
    confidence: str
    logic_type: str
    enabled: bool
    detection_count: int


class RulesListResponse(BaseModel):
    """List of supply-chain rules."""

    rules: list[SupplyChainRuleResponse]
    total: int


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/posture",
    response_model=PostureResponse,
    summary="Supply chain posture",
    description="Overall supply chain security posture summary.",
)
async def get_posture(
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> PostureResponse:
    """Return the aggregate supply chain security posture."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    try:
        posture = await svc.get_supply_chain_posture(db, scoped_orgs)
    except Exception:
        logger.warning("supply_chain.posture_query_failed", exc_info=True)
        posture = svc.SupplyChainPosture(
            score=100,
            unpinned_actions=0,
            dependency_alerts=0,
            risky_workflows=0,
            rules_active=0,
            total_detections=0,
            critical_detections=0,
        )
    return PostureResponse(
        score=posture.score,
        unpinned_actions=posture.unpinned_actions,
        dependency_alerts=posture.dependency_alerts,
        risky_workflows=posture.risky_workflows,
        rules_active=posture.rules_active,
        total_detections=posture.total_detections,
        critical_detections=posture.critical_detections,
        recent_risks=posture.recent_risks,
    )


@router.get(
    "/risks",
    response_model=RiskSummaryResponse,
    summary="Dependency risks",
    description="Summary of dependency-related risks across orgs.",
)
async def get_risks(
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> RiskSummaryResponse:
    """Return the dependency risk summary."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    try:
        summary = await svc.get_dependency_risk_summary(db, scoped_orgs)
    except Exception:
        logger.warning("supply_chain.risks_query_failed", exc_info=True)
        summary = svc.DependencyRiskSummary(total_risks=0)
    return RiskSummaryResponse(
        total_risks=summary.total_risks,
        by_severity=summary.by_severity,
        by_type=summary.by_type,
        top_repos=summary.top_repos,
    )


@router.get(
    "/rules",
    response_model=RulesListResponse,
    summary="Supply chain rules",
    description="Supply chain detection rules with detection counts.",
)
async def list_rules(
    current_user: AuthenticatedUser = Depends(require_permission("rules", "view")),
    db: AsyncSession = Depends(get_db),
) -> RulesListResponse:
    """Return supply chain detection rules with detection counts."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            "SELECT r.id, r.name, r.slug, r.description, "
            "r.default_severity, r.default_confidence, r.logic_type, r.enabled, "
            "COALESCE(dc.cnt, 0) as detection_count "
            "FROM rule_definitions r "
            "LEFT JOIN ("
            "  SELECT rule_id, count(*) as cnt FROM detections GROUP BY rule_id"
            ") dc ON dc.rule_id = r.id "
            "WHERE r.category = 'supply_chain' "
            "ORDER BY r.name"
        )
    )
    rows = result.fetchall()

    rules = [
        SupplyChainRuleResponse(
            id=row.id,
            name=row.name,
            slug=row.slug,
            description=row.description,
            severity=row.default_severity,
            confidence=row.default_confidence,
            logic_type=row.logic_type,
            enabled=row.enabled,
            detection_count=row.detection_count,
        )
        for row in rows
    ]

    return RulesListResponse(rules=rules, total=len(rules))


@router.post(
    "/analyze-workflow",
    response_model=AnalyzeWorkflowResponse,
    summary="Analyse workflow",
    description="Analyse a GitHub Actions workflow file for supply chain risks.",
    dependencies=[Depends(verify_csrf)],
)
async def analyze_workflow(
    body: AnalyzeWorkflowRequest,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
) -> AnalyzeWorkflowResponse:
    """Analyse workflow YAML content and return findings."""
    findings = await svc.analyze_workflow_file(body.content)

    # Determine overall risk level
    severities = [f.severity for f in findings]
    if "critical" in severities:
        risk_level = "critical"
    elif "high" in severities:
        risk_level = "high"
    elif "medium" in severities:
        risk_level = "medium"
    elif "low" in severities:
        risk_level = "low"
    else:
        risk_level = "none"

    return AnalyzeWorkflowResponse(
        findings=[
            FindingResponse(
                rule_slug=f.rule_slug,
                title=f.title,
                severity=f.severity,
                confidence=f.confidence,
                line=f.line,
                detail=f.detail,
                recommendation=f.recommendation,
            )
            for f in findings
        ],
        total_findings=len(findings),
        risk_level=risk_level,
    )
