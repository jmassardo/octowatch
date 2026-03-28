"""Health signals router: Org Health tab API endpoints.

Every endpoint enforces RBAC by resolving scoped_orgs from the database
(via ``rbac_service.get_scoped_orgs``) and returning HTTP 403 when the
user has no org access.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.services import health_signal_service, rbac_service

router = APIRouter(prefix="/health-signals", tags=["health-signals"])


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty."""
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


@router.get("/summary")
async def health_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate counts across all health signal types."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    summary = await health_signal_service.get_health_summary(db, scoped_orgs=scoped_orgs)

    # Enrich with expanded health signal summaries
    secret_scanning = await health_signal_service.get_secret_scanning_alert_health(
        db, scoped_orgs=scoped_orgs
    )
    summary["secret_scanning_unresolved"] = sum(
        row.get("unresolved_total", 0) for row in secret_scanning
    )

    security_coverage = await health_signal_service.get_security_coverage(
        db, scoped_orgs=scoped_orgs
    )
    summary["security_features_disabled_7d"] = sum(
        row.get("any_feature_disabled", 0) for row in security_coverage
    )

    sso = await health_signal_service.get_sso_health(db, scoped_orgs=scoped_orgs)
    summary["sso_disabled_orgs"] = sum(1 for row in sso if row.get("sso_state") == "disabled")

    return summary


@router.get("/pat-health")
async def pat_health(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """PAT age and dormant token signals."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    summary = await health_signal_service.get_pat_health_summary(db, scoped_orgs=scoped_orgs)
    tokens = await health_signal_service.get_pat_token_age_signals(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    dormant = await health_signal_service.get_dormant_tokens(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"summary": summary, "tokens": tokens, "dormant": dormant}


@router.get("/bypass-offenders")
async def bypass_offenders(
    lookback_days: int = Query(default=90, ge=7, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Top bypass offenders."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    offenders = await health_signal_service.get_bypass_offenders(
        db, scoped_orgs=scoped_orgs, lookback_days=lookback_days, limit=limit
    )
    return {"offenders": offenders}


@router.get("/repo-health")
async def repo_health(
    stale_threshold_days: int = Query(default=90, ge=7, le=365),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Stale, archived, and abandoned fork repositories."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    stale = await health_signal_service.get_stale_repositories(
        db, scoped_orgs=scoped_orgs, stale_threshold_days=stale_threshold_days, limit=limit
    )
    archived = await health_signal_service.get_archived_repositories(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    forks = await health_signal_service.get_abandoned_forks(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"stale": stale, "archived": archived, "abandoned_forks": forks}


@router.get("/external-collaborators")
async def external_collaborators(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Active external collaborators and summary."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    summary = await health_signal_service.get_external_collaborator_summary(
        db, scoped_orgs=scoped_orgs
    )
    collaborators = await health_signal_service.get_external_collaborators(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"summary": summary, "collaborators": collaborators}


@router.get("/dormant-collaborators")
async def dormant_collaborators(
    dormancy_days: int = Query(default=60, ge=7, le=365),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """External collaborators with no activity beyond dormancy threshold."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    dormant = await health_signal_service.get_dormant_collaborators(
        db, scoped_orgs=scoped_orgs, dormancy_days=dormancy_days, limit=limit
    )
    return {"dormant": dormant}


@router.get("/security-posture")
async def security_posture(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Security feature coverage per org."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    coverage = await health_signal_service.get_security_coverage(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"coverage": coverage}


@router.get("/secret-scanning")
async def secret_scanning(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Secret scanning MTTR and unresolved alert counts."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    alerts = await health_signal_service.get_secret_scanning_alert_health(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"alerts": alerts}


@router.get("/sso")
async def sso_health(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """SSO enable/disable state per org."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    sso = await health_signal_service.get_sso_health(db, scoped_orgs=scoped_orgs, limit=limit)
    return {"sso": sso}


@router.get("/ip-allowlist")
async def ip_allowlist(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """IP allowlist / audit stream status per org."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    stream_status = await health_signal_service.get_audit_stream_status(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"stream_status": stream_status}


@router.get("/privilege-changes")
async def privilege_changes(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Admin promotions, integration manager grants, custom role changes."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    changes = await health_signal_service.get_privilege_change_summary(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"changes": changes}


@router.get("/code-scanning")
async def code_scanning(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Code scanning MTTR and dismissal rates."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    alerts = await health_signal_service.get_code_scanning_health(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"alerts": alerts}


@router.get("/vulnerabilities")
async def vulnerabilities(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dependabot vulnerability aging summary."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    aging = await health_signal_service.get_vulnerability_aging(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"aging": aging}


@router.get("/app-governance")
async def app_governance(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """OAuth and GitHub App governance summary."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    governance = await health_signal_service.get_app_governance_summary(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"governance": governance}


@router.get("/workflows")
async def workflows(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Workflow failure rates and health."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    workflow_health = await health_signal_service.get_workflow_health(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"workflows": workflow_health}


@router.get("/copilot-governance")
async def copilot_governance(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Copilot seat utilization and governance."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    seats = await health_signal_service.get_copilot_seat_health(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"seats": seats}


@router.get("/codespaces")
async def codespaces(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Codespace cost and activity signals."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    cost_signals = await health_signal_service.get_codespace_cost_signals(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"codespaces": cost_signals}


@router.get("/runners")
async def runners(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Self-hosted runner fleet health."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    fleet = await health_signal_service.get_runner_fleet_health(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"runners": fleet}


@router.get("/branch-protection")
async def branch_protection(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Branch protection change summary."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    protection = await health_signal_service.get_branch_protection_health(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"protection": protection}


@router.get("/system")
async def system_health(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """System health: ingestion gaps, health events, and audit stream status."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    ingestion_gaps = await health_signal_service.get_ingestion_gap_status(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    health_events = await health_signal_service.get_system_health_events(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    stream_status = await health_signal_service.get_audit_stream_status(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {
        "ingestion_gaps": ingestion_gaps,
        "health_events": health_events,
        "stream_status": stream_status,
    }
