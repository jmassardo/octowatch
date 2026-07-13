"""Health signals router: Org Health tab API endpoints.

Every endpoint enforces RBAC by resolving scoped_orgs from the database
(via ``rbac_service.get_scoped_orgs``) and returning HTTP 403 when the
user has no org access.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, require_permission, verify_csrf
from app.services import health_signal_service, rbac_service

router = APIRouter(prefix="/health-signals", tags=["health-signals"])


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty.

    Global (sys_admin) users with no orgs yet get an empty list (no data)
    rather than 403, since it means no events/orgs have been synced yet.
    """
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs and current_user.scope_type != "global":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


@router.get("/summary", response_model=dict[str, Any])
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


@router.get("/pat-health", response_model=dict[str, Any])
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


@router.get("/bypass-offenders", response_model=dict[str, Any])
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


@router.get("/repo-health", response_model=dict[str, Any])
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


@router.get("/external-collaborators", response_model=dict[str, Any])
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


@router.get("/dormant-collaborators", response_model=dict[str, Any])
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


@router.get("/security-posture", response_model=dict[str, Any])
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


@router.get("/secret-scanning", response_model=dict[str, Any])
async def secret_scanning(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Secret scanning MTTR and unresolved alert counts — aggregated flat object."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    rows = await health_signal_service.get_secret_scanning_alert_health(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    # Aggregate per-org rows into a single flat object matching SecretScanningResponse
    unresolved_total = sum(r.get("unresolved_total", 0) for r in rows)
    resolved_count = sum(r.get("resolved_count", 0) for r in rows)
    total_count = sum(r.get("total_count", 0) for r in rows)
    push_bypassed = sum(r.get("push_protection_bypassed_count", 0) for r in rows)
    unresolved_gt_7d = sum(r.get("unresolved_gt_7d", 0) for r in rows)
    unresolved_gt_30d = sum(r.get("unresolved_gt_30d", 0) for r in rows)
    # MTTR: weighted average across orgs (weight by resolved_count)
    total_weighted_hours = sum(
        (r.get("avg_hours_to_resolve") or 0) * r.get("resolved_count", 0) for r in rows
    )
    total_resolved_for_avg = sum(r.get("resolved_count", 0) for r in rows)
    mttr_hours = (total_weighted_hours / total_resolved_for_avg) if total_resolved_for_avg else 0
    resolution_rate_pct = round(resolved_count / total_count * 100, 1) if total_count else 0.0
    return {
        "alerts": rows,
        "unresolved_total": unresolved_total,
        "publicly_leaked": 0,  # not tracked in schema; reserved for future
        "push_protection_bypassed_count": push_bypassed,
        "open_gt_7d": unresolved_gt_7d,
        "open_gt_30d": unresolved_gt_30d,
        "mttr_hours": mttr_hours,
        "avg_hours_to_resolve": mttr_hours if total_resolved_for_avg else None,
        "unresolved_gt_7d": unresolved_gt_7d,
        "unresolved_gt_30d": unresolved_gt_30d,
        "resolved_count": resolved_count,
        "total_count": total_count,
        "resolution_rate_pct": resolution_rate_pct,
    }


@router.get("/sso", response_model=dict[str, Any])
async def sso_health(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """SSO enable/disable state per org."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    sso = await health_signal_service.get_sso_health(db, scoped_orgs=scoped_orgs, limit=limit)
    return {"sso": sso}


@router.get("/ip-allowlist", response_model=dict[str, Any])
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


@router.get("/privilege-changes", response_model=dict[str, Any])
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


@router.get("/code-scanning", response_model=dict[str, Any])
async def code_scanning(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Code scanning MTTR and dismissal rates — aggregated flat object."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    rows = await health_signal_service.get_code_scanning_health(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    # Aggregate per-repo rows into a single flat object matching CodeScanningResponse
    total_alerts = sum(r.get("total_alerts", 0) for r in rows)
    open_count = sum(r.get("open_count", 0) for r in rows)
    fixed_count = sum(r.get("fixed_count", 0) for r in rows)
    dismissed_count = sum(r.get("dismissed_count", 0) for r in rows)
    critical_count = sum(r.get("critical_count", 0) for r in rows)
    high_count = sum(r.get("high_count", 0) for r in rows)
    medium_count = sum(r.get("medium_count", 0) for r in rows)
    low_count = sum(r.get("low_count", 0) for r in rows)
    # Weighted average hours-to-close (weight by closed alert count)
    closed_count = fixed_count + dismissed_count
    total_weighted_close = sum(
        (r.get("avg_hours_to_close") or 0) * (r.get("fixed_count", 0) + r.get("dismissed_count", 0))
        for r in rows
    )
    avg_hours_to_close = (total_weighted_close / closed_count) if closed_count else 0
    return {
        "alerts": rows,
        "total_alerts": total_alerts,
        "open_count": open_count,
        "fixed_count": fixed_count,
        "dismissed_count": dismissed_count,
        "critical_count": critical_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "avg_hours_to_close": avg_hours_to_close,
        "reappeared_count": 0,  # not tracked in schema; reserved for future
    }


@router.get("/vulnerabilities", response_model=dict[str, Any])
async def vulnerabilities(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dependabot vulnerability aging summary — aggregated flat object."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    rows = await health_signal_service.get_vulnerability_aging(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    # Aggregate per-org rows into a single flat object matching VulnerabilitiesResponse
    total_open = sum(r.get("total_open", 0) for r in rows)
    # Weighted average for avg_open_days
    total_weighted_days = sum((r.get("avg_open_days") or 0) * r.get("total_open", 0) for r in rows)
    avg_open_days = (total_weighted_days / total_open) if total_open else 0
    return {
        "aging": rows,
        "total_open": total_open,
        "critical_open": sum(r.get("open_critical", 0) for r in rows),
        "high_open": sum(r.get("open_high", 0) for r in rows),
        "open_gt_30d": sum(r.get("open_gt_30d", 0) for r in rows),
        "critical_open_gt_14d": sum(r.get("critical_open_gt_14d", 0) for r in rows),
        "avg_open_days": avg_open_days,
        "open_medium": sum(r.get("open_medium", 0) for r in rows),
        "open_low": sum(r.get("open_low", 0) for r in rows),
        "age_0_30d": sum(r.get("age_0_30d", 0) for r in rows),
        "age_30_60d": sum(r.get("age_30_60d", 0) for r in rows),
        "age_60_90d": sum(r.get("age_60_90d", 0) for r in rows),
        "age_gt_90d": sum(r.get("age_gt_90d", 0) for r in rows),
        "critical_aging_gt_90d": sum(r.get("critical_aging_gt_90d", 0) for r in rows),
    }


@router.get("/app-governance", response_model=dict[str, Any])
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


@router.get("/workflows", response_model=dict[str, Any])
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


@router.get("/copilot-governance", response_model=dict[str, Any])
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


@router.get("/codespaces", response_model=dict[str, Any])
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


@router.get("/runners", response_model=dict[str, Any])
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


@router.get("/branch-protection", response_model=dict[str, Any])
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


@router.get("/system", response_model=dict[str, Any])
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


@router.get("/settings", response_model=dict[str, Any])
async def get_health_settings(
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return persisted health settings, merged with defaults."""
    result = await db.execute(
        text("""
            SELECT detail FROM system_health_events
            WHERE signal_type = 'health_settings'
            ORDER BY occurred_at DESC LIMIT 1
        """)
    )
    row = result.fetchone()
    defaults: dict[str, Any] = {
        "staleRepoDays": 90,
        "stalePrDays": 30,
        "unreviewedDependabotDays": 60,
        "ciSkippedConsecutive": 10,
        "dormantMemberDays": 90,
        "patNoExpiryFlag": True,
        "patStaleDays": 90,
        "outsideCollabFlag": True,
        "licenseUtilizationPct": 80,
        "ghostMemberCost": 19,
        "escalateCriticalDays": 60,
        "escalateStaleReposDays": 180,
        "escalateDormantDays": 180,
        "escalationDestination": "Detection queue (internal)",
    }
    if row:
        saved = row[0] if isinstance(row[0], dict) else {}
        defaults.update(saved)
    return defaults


@router.put("/settings", response_model=dict[str, Any], dependencies=[Depends(verify_csrf)])
async def update_health_settings(
    body: dict[str, Any],
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Persist health settings."""
    from app.models.audit_trail import AuditTrail

    await db.execute(
        text("""
            INSERT INTO system_health_events
                (signal_type, severity, detail, org)
            VALUES
                ('health_settings', 'info', CAST(:detail AS JSONB), NULL)
        """),
        {"detail": json.dumps(body)},
    )
    db.add(
        AuditTrail(
            user_login=current_user.github_login,
            action_type="health_settings.update",
            resource_type="health_settings",
            resource_id="global",
            outcome="success",
        )
    )
    await db.commit()
    return body


@router.get("/ghost-members", response_model=dict[str, Any])
async def ghost_members(
    dormancy_days: int = Query(default=90, ge=30, le=365),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ghost members with no activity beyond dormancy threshold."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    members = await health_signal_service.get_ghost_members(
        db, scoped_orgs=scoped_orgs, dormancy_days=dormancy_days, limit=limit
    )
    return {"ghost_members": members}


@router.get("/stale-prs", response_model=dict[str, Any])
async def stale_prs(
    stale_days: int = Query(default=30, ge=7, le=365),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """PRs open longer than the stale threshold."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    prs = await health_signal_service.get_stale_prs(
        db, scoped_orgs=scoped_orgs, stale_days=stale_days, limit=limit
    )
    return {"stale_prs": prs}


@router.get("/unhealthy-hooks", response_model=dict[str, Any])
async def unhealthy_hooks(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Unhealthy webhooks and apps."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    hooks = await health_signal_service.get_unhealthy_webhooks(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"unhealthy_hooks": hooks}


@router.get("/skipped-workflows", response_model=dict[str, Any])
async def skipped_workflows(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Disabled or consistently skipped workflows."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    wfs = await health_signal_service.get_skipped_workflows(
        db, scoped_orgs=scoped_orgs, limit=limit
    )
    return {"skipped_workflows": wfs}


@router.get("/waf-findings", response_model=dict[str, Any])
async def waf_findings(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Well-Architected Framework alignment findings."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    findings = await health_signal_service.get_waf_findings(db, scoped_orgs=scoped_orgs)
    return {"findings": findings}


@router.get("/teams", response_model=dict[str, Any])
async def list_teams(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return team memberships from enterprise sync data (org_teams + org_team_members)."""
    from sqlalchemy import text as sa_text

    scoped_orgs = await _resolve_orgs(db, current_user)

    result = await db.execute(
        sa_text("""
            SELECT t.org, t.team_slug, t.name AS team_name,
                   ARRAY_AGG(DISTINCT tm.github_login) AS members
            FROM org_teams t
            JOIN org_team_members tm ON tm.org = t.org AND tm.team_slug = t.team_slug
            WHERE t.org = ANY(:scoped_orgs)
            GROUP BY t.org, t.team_slug, t.name
            ORDER BY t.name
        """),
        {"scoped_orgs": scoped_orgs},
    )
    teams = [dict(row._mapping) for row in result.fetchall()]

    return {"teams": teams}


# ── License consumption (from GHEC enterprise sync) ──────────────────────────


@router.get("/license-consumption", response_model=dict[str, Any])
async def license_consumption(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return GHEC license seat data from the enterprise sync.

    Returns the most recent ``EnterpriseLicenseConsumption`` row which is
    populated by the ``license_consumption`` sync entity type.
    """
    from sqlalchemy import text as sa_text

    result = await db.execute(
        sa_text("""
            SELECT enterprise_slug,
                   total_seats_purchased,
                   total_seats_consumed,
                   synced_at
            FROM enterprise_license_consumption
            ORDER BY synced_at DESC
            LIMIT 1
        """)
    )
    row = result.fetchone()
    if row is None:
        return {
            "enterprise_slug": None,
            "total_seats_purchased": 0,
            "total_seats_consumed": 0,
            "seats_available": 0,
            "utilization_pct": 0,
            "synced_at": None,
        }
    m = dict(row._mapping)
    purchased = m["total_seats_purchased"]
    consumed = m["total_seats_consumed"]
    return {
        "enterprise_slug": m["enterprise_slug"],
        "total_seats_purchased": purchased,
        "total_seats_consumed": consumed,
        "seats_available": max(0, purchased - consumed),
        "utilization_pct": round(consumed / purchased * 100, 1) if purchased else 0,
        "synced_at": m["synced_at"].isoformat() if m["synced_at"] else None,
    }


# ── Outside collaborators (from enterprise sync) ────────────────────────────


@router.get("/outside-collaborators-sync", response_model=dict[str, Any])
async def outside_collaborators_sync(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return outside collaborators from the enterprise sync data."""
    from sqlalchemy import text as sa_text

    scoped_orgs = await _resolve_orgs(db, current_user)

    result = await db.execute(
        sa_text("""
            SELECT org, login, github_id, avatar_url, site_admin, synced_at
            FROM org_outside_collaborators
            WHERE org = ANY(:scoped_orgs)
            ORDER BY org, login
        """),
        {"scoped_orgs": scoped_orgs},
    )
    collaborators = [dict(row._mapping) for row in result.fetchall()]
    return {"collaborators": collaborators, "total": len(collaborators)}


# ── Security alerts summary (from enterprise sync) ──────────────────────────


@router.get("/security-alerts-summary", response_model=dict[str, Any])
async def security_alerts_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return aggregated secret-scanning and Dependabot alert summaries."""
    from sqlalchemy import text as sa_text

    scoped_orgs = await _resolve_orgs(db, current_user)

    ss_result = await db.execute(
        sa_text("""
            SELECT org, open_count, resolved_count, total_count, synced_at
            FROM org_secret_scanning_alert_summaries
            WHERE org = ANY(:scoped_orgs)
            ORDER BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    secret_scanning = [dict(row._mapping) for row in ss_result.fetchall()]

    dep_result = await db.execute(
        sa_text("""
            SELECT org, open_count, fixed_count, dismissed_count, total_count,
                   critical_count, high_count, medium_count, low_count, synced_at
            FROM org_dependabot_alert_summaries
            WHERE org = ANY(:scoped_orgs)
            ORDER BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    dependabot = [dict(row._mapping) for row in dep_result.fetchall()]

    return {
        "secret_scanning": secret_scanning,
        "dependabot": dependabot,
    }


# ── GHAS Individual Alert Endpoints (Epic 5) ────────────────────────────────


@router.get("/unified-security", response_model=dict[str, Any])
async def unified_security(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Unified security dashboard: all GHAS alert types + active detections."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_unified_security_summary(db, scoped_orgs=scoped_orgs)


@router.get("/secret-scanning/alerts", response_model=dict[str, Any])
async def secret_scanning_alerts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    state: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Paginated list of individual secret scanning alerts."""
    from sqlalchemy import ColumnElement, func, select

    from app.models.github_sync import SecretScanningAlert

    scoped_orgs = await _resolve_orgs(db, current_user)

    filters: list[ColumnElement[bool]] = [SecretScanningAlert.org_slug.in_(scoped_orgs)]
    if state:
        filters.append(SecretScanningAlert.state == state)

    count_q = select(func.count()).select_from(SecretScanningAlert).where(*filters)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    data_q = (
        select(SecretScanningAlert)
        .where(*filters)
        .order_by(SecretScanningAlert.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(data_q)
    rows = result.scalars().all()
    alerts = [
        {
            "id": r.id,
            "org_slug": r.org_slug,
            "alert_number": r.alert_number,
            "repo_full_name": r.repo_full_name,
            "secret_type": r.secret_type,
            "secret_type_display": r.secret_type_display,
            "file_path": r.file_path,
            "commit_sha": r.commit_sha,
            "state": r.state,
            "resolution": r.resolution,
            "push_protection_bypassed": r.push_protection_bypassed,
            "push_protection_bypassed_by": r.push_protection_bypassed_by,
            "created_at": r.created_at,
            "resolved_at": r.resolved_at,
            "synced_at": r.synced_at,
        }
        for r in rows
    ]

    return {"alerts": alerts, "total": total}


@router.get("/code-scanning/alerts", response_model=dict[str, Any])
async def code_scanning_alerts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    state: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Paginated list of individual code scanning alerts."""
    from sqlalchemy import ColumnElement, func, select
    from sqlalchemy.sql.functions import coalesce

    from app.models.github_sync import CodeScanningAlert

    scoped_orgs = await _resolve_orgs(db, current_user)

    filters: list[ColumnElement[bool]] = [CodeScanningAlert.org_slug.in_(scoped_orgs)]
    if state:
        filters.append(CodeScanningAlert.state == state)
    if severity:
        filters.append(
            coalesce(
                CodeScanningAlert.security_severity,
                CodeScanningAlert.severity,
            )
            == severity
        )

    count_q = select(func.count()).select_from(CodeScanningAlert).where(*filters)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    data_q = (
        select(CodeScanningAlert)
        .where(*filters)
        .order_by(CodeScanningAlert.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(data_q)
    rows = result.scalars().all()
    alerts = [
        {
            "id": r.id,
            "org_slug": r.org_slug,
            "alert_number": r.alert_number,
            "repo_full_name": r.repo_full_name,
            "rule_id": r.rule_id,
            "rule_description": r.rule_description,
            "severity": r.severity,
            "security_severity": r.security_severity,
            "cwe_ids": r.cwe_ids,
            "tool_name": r.tool_name,
            "file_path": r.file_path,
            "start_line": r.start_line,
            "state": r.state,
            "dismissed_by": r.dismissed_by,
            "dismissed_reason": r.dismissed_reason,
            "dismissed_at": r.dismissed_at,
            "created_at": r.created_at,
            "fixed_at": r.fixed_at,
            "synced_at": r.synced_at,
        }
        for r in rows
    ]

    return {"alerts": alerts, "total": total}


@router.get("/vulnerabilities/alerts", response_model=dict[str, Any])
async def dependabot_alerts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    state: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Paginated list of individual Dependabot alerts."""
    from sqlalchemy import ColumnElement, func, select

    from app.models.github_sync import DependabotAlert

    scoped_orgs = await _resolve_orgs(db, current_user)

    filters: list[ColumnElement[bool]] = [DependabotAlert.org_slug.in_(scoped_orgs)]
    if state:
        filters.append(DependabotAlert.state == state)
    if severity:
        filters.append(DependabotAlert.severity == severity)

    count_q = select(func.count()).select_from(DependabotAlert).where(*filters)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    data_q = (
        select(DependabotAlert)
        .where(*filters)
        .order_by(DependabotAlert.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(data_q)
    rows = result.scalars().all()
    alerts = [
        {
            "id": r.id,
            "org_slug": r.org_slug,
            "alert_number": r.alert_number,
            "repo_full_name": r.repo_full_name,
            "package_name": r.package_name,
            "package_ecosystem": r.package_ecosystem,
            "severity": r.severity,
            "cvss_score": r.cvss_score,
            "cve_id": r.cve_id,
            "cwe_ids": r.cwe_ids,
            "vulnerable_version_range": r.vulnerable_version_range,
            "patched_version": r.patched_version,
            "state": r.state,
            "dismissed_by": r.dismissed_by,
            "dismissed_reason": r.dismissed_reason,
            "created_at": r.created_at,
            "fixed_at": r.fixed_at,
            "auto_dismissed_at": r.auto_dismissed_at,
            "synced_at": r.synced_at,
        }
        for r in rows
    ]

    return {"alerts": alerts, "total": total}


@router.get("/api-abuse", response_model=dict[str, Any])
async def api_abuse_signals(
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """API abuse detection signals."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    signals = await health_signal_service.get_api_abuse_signals(
        db, scoped_orgs=scoped_orgs, hours=hours, limit=limit
    )
    return {"signals": signals}


@router.get("/dormant-users", response_model=dict[str, Any])
async def dormant_users(
    days_inactive: int = Query(default=90, ge=30, le=365),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Dormant users with cost estimates."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    users = await health_signal_service.get_dormant_users(
        db, scoped_orgs=scoped_orgs, days_inactive=days_inactive, limit=limit
    )
    summary = {
        "total_dormant": len(users),
        "estimated_monthly_waste": sum(u.get("estimated_monthly_cost", 0) for u in users),
    }
    return {"users": users, "summary": summary}


@router.get("/platform-security", response_model=dict[str, Any])
async def platform_security(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Platform security configuration inventory."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    orgs = await health_signal_service.get_platform_security(db, scoped_orgs=scoped_orgs)
    avg_score = sum(o.get("compliance_score", 0) for o in orgs) / max(len(orgs), 1)
    return {"orgs": orgs, "overall_compliance_score": round(avg_score, 1)}


@router.get("/maintenance-signals", response_model=dict[str, Any])
async def maintenance_signals(
    stale_threshold_days: int = Query(default=180, ge=30, le=730),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Comprehensive maintenance signals."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_maintenance_signals(
        db, scoped_orgs=scoped_orgs, stale_threshold_days=stale_threshold_days, limit=limit
    )


@router.get("/score", response_model=dict[str, Any])
async def health_score(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Overall org health score."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_health_score(db, scoped_orgs=scoped_orgs)


@router.get("/strategic/mttr-trends", response_model=dict[str, Any])
async def mttr_trends(
    period: str = Query(default="30d", pattern="^(7d|30d|90d)$"),
    severity: str | None = Query(default=None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_mttr_trends(
        db,
        scoped_orgs=scoped_orgs,
        period=period,
        severity=severity,
    )


@router.get("/strategic/coverage-growth", response_model=dict[str, Any])
async def coverage_growth(
    period: str = Query(default="90d", pattern="^(30d|90d|180d)$"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_coverage_growth(
        db,
        scoped_orgs=scoped_orgs,
        period=period,
    )


@router.get("/strategic/alert-aging", response_model=dict[str, Any])
async def alert_aging(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_alert_aging(
        db,
        scoped_orgs=scoped_orgs,
    )


@router.get("/strategic/security-score", response_model=dict[str, Any])
async def security_score(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_security_score(
        db,
        scoped_orgs=scoped_orgs,
    )


# ── GHAS Active Committers (from org billing sync) ───────────────────────────


@router.get("/ghas-active-committers", response_model=dict[str, Any])
async def ghas_active_committers(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Active committer counts for GHAS billing."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    return await health_signal_service.get_ghas_active_committers(db, scoped_orgs=scoped_orgs)
