"""Compliance Center router: summary, framework controls, policy checks, GDPR."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.schemas.compliance import (
    ComplianceSummary,
    FrameworkDetail,
    GDPRSummary,
    PolicyCheckResults,
)
from app.services.compliance_service import (
    get_compliance_summary,
    get_framework_controls,
    get_gdpr_summary,
    get_policy_check_results,
    run_policy_checks,
)

router = APIRouter(prefix="/compliance", tags=["compliance"])
logger = structlog.get_logger(__name__)


@router.get(
    "/summary",
    response_model=ComplianceSummary,
    summary="Overall compliance scores across frameworks",
)
async def compliance_summary(
    org: str | None = Query(None, max_length=255),
    db: AsyncSession = Depends(get_db),
    _user: AuthenticatedUser = Depends(require_permission("reports", "view")),
) -> dict[str, Any]:
    """Return aggregate compliance posture across SOC 2, ISO 27001, NIST CSF, and GDPR."""
    return await get_compliance_summary(db, org=org)


@router.get(
    "/framework/{name}",
    response_model=FrameworkDetail,
    summary="Specific framework controls and status",
)
async def framework_detail(
    name: str,
    org: str | None = Query(None, max_length=255),
    db: AsyncSession = Depends(get_db),
    _user: AuthenticatedUser = Depends(require_permission("reports", "view")),
) -> dict[str, Any]:
    """Return detailed control status for a specific compliance framework."""
    valid_frameworks = {"soc2", "iso27001", "nist_csf", "gdpr"}
    if name not in valid_frameworks:
        valid = ", ".join(sorted(valid_frameworks))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown framework: {name}. Valid: {valid}",
        )
    return await get_framework_controls(db, name, org=org)


@router.get(
    "/policy-checks",
    response_model=PolicyCheckResults,
    summary="Automated policy check results",
)
async def policy_checks(
    org: str | None = Query(None, max_length=255),
    db: AsyncSession = Depends(get_db),
    _user: AuthenticatedUser = Depends(require_permission("reports", "view")),
) -> dict[str, Any]:
    """Return latest automated policy check results."""
    return await get_policy_check_results(db, org=org)


@router.post(
    "/policy-checks/run",
    response_model=PolicyCheckResults,
    summary="Trigger policy checks",
)
async def run_checks(
    org: str | None = Query(None, max_length=255),
    db: AsyncSession = Depends(get_db),
    _user: AuthenticatedUser = Depends(require_permission("reports", "create")),
    _csrf: None = Depends(verify_csrf),
) -> dict[str, Any]:
    """Execute all automated policy checks and return fresh results."""
    return await run_policy_checks(db, org=org)


@router.get(
    "/gdpr/summary",
    response_model=GDPRSummary,
    summary="GDPR compliance summary",
)
async def gdpr_summary(
    org: str | None = Query(None, max_length=255),
    db: AsyncSession = Depends(get_db),
    _user: AuthenticatedUser = Depends(require_permission("reports", "view")),
) -> dict[str, Any]:
    """Return GDPR compliance dashboard data."""
    return await get_gdpr_summary(db, org=org)
