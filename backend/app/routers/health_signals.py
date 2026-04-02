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


@router.get("/settings")
async def get_health_settings(
    current_user: AuthenticatedUser = Depends(get_current_user),
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


@router.put("/settings")
async def update_health_settings(
    body: dict[str, Any],
    current_user: AuthenticatedUser = Depends(get_current_user),
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


@router.get("/ghost-members")
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


@router.get("/stale-prs")
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


@router.get("/unhealthy-hooks")
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


@router.get("/skipped-workflows")
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


@router.get("/waf-findings")
async def waf_findings(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Well-Architected Framework alignment findings."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    findings = await health_signal_service.get_waf_findings(db, scoped_orgs=scoped_orgs)
    return {"findings": findings}


@router.get("/teams")
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


@router.get("/license-consumption")
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


@router.get("/outside-collaborators-sync")
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


@router.get("/security-alerts-summary")
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
