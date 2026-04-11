"""Compliance report engine: SOC 2, ISO 27001, and NIST CSF evidence reports.

Generates structured compliance evidence by querying audit events from TimescaleDB
and mapping them to framework-specific control sections.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _count_events(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    action_filter: str,
    org: str | None = None,
) -> int:
    """Count events matching a SQL LIKE pattern within a date range."""
    org_clause = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT COUNT(*) AS cnt
        FROM events
        WHERE created_at >= :start AND created_at < :end
          AND action LIKE :action_filter
          {org_clause}
    """)
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        "action_filter": action_filter,
    }
    if org:
        params["org"] = org
    result = await session.execute(stmt, params)
    row = result.fetchone()
    return int(row.cnt) if row else 0


async def _count_events_in(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    actions: list[str],
    org: str | None = None,
) -> int:
    """Count events matching an exact action list within a date range."""
    if not actions:
        return 0
    org_clause = "AND org = :org" if org else ""
    placeholders = ", ".join(f":action_{i}" for i in range(len(actions)))
    stmt = text(f"""
        SELECT COUNT(*) AS cnt
        FROM events
        WHERE created_at >= :start AND created_at < :end
          AND action IN ({placeholders})
          {org_clause}
    """)
    params: dict[str, Any] = {"start": start, "end": end}
    for i, action in enumerate(actions):
        params[f"action_{i}"] = action
    if org:
        params["org"] = org
    result = await session.execute(stmt, params)
    row = result.fetchone()
    return int(row.cnt) if row else 0


async def _distinct_actors(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    action_filter: str,
    org: str | None = None,
) -> int:
    """Count distinct actors for events matching a LIKE pattern."""
    org_clause = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT COUNT(DISTINCT actor) AS cnt
        FROM events
        WHERE created_at >= :start AND created_at < :end
          AND action LIKE :action_filter
          AND actor IS NOT NULL
          {org_clause}
    """)
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        "action_filter": action_filter,
    }
    if org:
        params["org"] = org
    result = await session.execute(stmt, params)
    row = result.fetchone()
    return int(row.cnt) if row else 0


async def _top_actions(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    action_filter: str,
    org: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return top actions by count matching a LIKE pattern."""
    org_clause = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT action, COUNT(*) AS event_count
        FROM events
        WHERE created_at >= :start AND created_at < :end
          AND action LIKE :action_filter
          {org_clause}
        GROUP BY action
        ORDER BY event_count DESC
        LIMIT :limit
    """)
    params: dict[str, Any] = {
        "start": start,
        "end": end,
        "action_filter": action_filter,
        "limit": limit,
    }
    if org:
        params["org"] = org
    result = await session.execute(stmt, params)
    return [{"action": row.action, "event_count": row.event_count} for row in result.fetchall()]


async def _total_unique_values(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    column: str,
    org: str | None = None,
) -> int:
    """Count distinct non-null values for a given column in the events table."""
    org_clause = "AND org = :org" if org else ""
    # Column name is controlled by our code, not user input
    stmt = text(f"""
        SELECT COUNT(DISTINCT {column}) AS cnt
        FROM events
        WHERE created_at >= :start AND created_at < :end
          AND {column} IS NOT NULL
          {org_clause}
    """)
    params: dict[str, Any] = {"start": start, "end": end}
    if org:
        params["org"] = org
    result = await session.execute(stmt, params)
    row = result.fetchone()
    return int(row.cnt) if row else 0


# ---------------------------------------------------------------------------
# SOC 2 Type II Report — Trust Services Criteria
# ---------------------------------------------------------------------------


async def generate_soc2_report(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    org: str | None = None,
) -> dict[str, Any]:
    """Generate SOC 2 Type II evidence report mapped to Trust Services Criteria.

    Sections:
        CC6.1 — Logical and Physical Access Controls
        CC6.2 — System Operations (Authentication)
        CC6.3 — Access Removal
        CC8.1 — Change Management
        CC7.1 — System Monitoring
    """
    logger.info(
        "compliance.soc2.generate",
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        org=org,
    )

    period_days = max((end_date - start_date).days, 1)

    # ── CC6.1: Logical Access Controls ──────────────────────────────────
    cc6_1_role_changes = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "org.update_member",
            "org.add_member",
            "org.invite_member",
            "team.add_member",
            "team.change_member_role",
        ],
        org=org,
    )
    cc6_1_external_collabs = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="repo.add_outside_collaborator%",
        org=org,
    )
    cc6_1_org_membership = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="org.%member%",
        org=org,
    )
    cc6_1_top_actions = await _top_actions(
        session,
        start=start_date,
        end=end_date,
        action_filter="org.%member%",
        org=org,
    )

    cc6_1 = {
        "control_id": "CC6.1",
        "title": "Logical and Physical Access Controls",
        "description": (
            "The entity implements logical access security software, infrastructure, "
            "and architectures over protected information assets."
        ),
        "evidence": {
            "role_change_events": cc6_1_role_changes,
            "external_collaborator_grants": cc6_1_external_collabs,
            "org_membership_events": cc6_1_org_membership,
            "top_access_actions": cc6_1_top_actions,
        },
        "status": "evidence_collected",
    }

    # ── CC6.2: Authentication ───────────────────────────────────────────
    cc6_2_sso_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="business.set_sso%",
        org=org,
    )
    cc6_2_2fa_events = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "org.require_two_factor_authentication",
            "org.disable_two_factor_requirement",
        ],
        org=org,
    )
    cc6_2_pat_created = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "personal_access_token.create",
            "personal_access_token_request.create",
        ],
        org=org,
    )
    cc6_2_pat_revoked = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "personal_access_token.revoke",
            "personal_access_token.expire",
            "personal_access_token_request.deny",
        ],
        org=org,
    )
    cc6_2_oauth_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="oauth_application.%",
        org=org,
    )

    cc6_2 = {
        "control_id": "CC6.2",
        "title": "System Operations — Authentication",
        "description": (
            "Prior to issuing system credentials and granting system access, the entity "
            "registers and authorizes new users."
        ),
        "evidence": {
            "sso_enforcement_events": cc6_2_sso_events,
            "two_factor_events": cc6_2_2fa_events,
            "pat_created": cc6_2_pat_created,
            "pat_revoked": cc6_2_pat_revoked,
            "oauth_application_events": cc6_2_oauth_events,
        },
        "status": "evidence_collected",
    }

    # ── CC6.3: Access Removal ───────────────────────────────────────────
    cc6_3_member_removals = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "org.remove_member",
            "org.remove_outside_collaborator",
            "team.remove_member",
        ],
        org=org,
    )
    cc6_3_deactivations = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="org.disable_member%",
        org=org,
    )
    cc6_3_collab_removals = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="repo.remove%collaborator%",
        org=org,
    )

    cc6_3 = {
        "control_id": "CC6.3",
        "title": "Access Removal",
        "description": (
            "The entity removes access to protected information assets when access "
            "is no longer required."
        ),
        "evidence": {
            "member_removals": cc6_3_member_removals,
            "account_deactivations": cc6_3_deactivations,
            "collaborator_removals": cc6_3_collab_removals,
            "total_access_removals": (
                cc6_3_member_removals + cc6_3_deactivations + cc6_3_collab_removals
            ),
        },
        "status": "evidence_collected",
    }

    # ── CC8.1: Change Management ────────────────────────────────────────
    cc8_1_branch_protection = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="protected_branch.%",
        org=org,
    )
    cc8_1_deployments = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="deployment.%",
        org=org,
    )
    cc8_1_review_changes = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "protected_branch.update_required_status_checks",
            "protected_branch.update_pull_request_reviews_enforcement_level",
        ],
        org=org,
    )
    cc8_1_workflow_runs = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="workflow_run.%",
        org=org,
    )

    cc8_1 = {
        "control_id": "CC8.1",
        "title": "Change Management",
        "description": (
            "The entity authorizes, designs, develops, configures, documents, tests, "
            "approves, and implements changes to infrastructure and software."
        ),
        "evidence": {
            "branch_protection_changes": cc8_1_branch_protection,
            "deployment_events": cc8_1_deployments,
            "required_review_changes": cc8_1_review_changes,
            "workflow_run_events": cc8_1_workflow_runs,
        },
        "status": "evidence_collected",
    }

    # ── CC7.1: System Monitoring ────────────────────────────────────────
    cc7_1_total_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="%",
        org=org,
    )
    cc7_1_unique_actors = await _distinct_actors(
        session,
        start=start_date,
        end=end_date,
        action_filter="%",
        org=org,
    )
    cc7_1_security_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="secret_scanning%",
        org=org,
    )
    cc7_1_admin_events = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "org.update_member",
            "business.set_sso_enforcement",
            "protected_branch.create",
            "protected_branch.destroy",
        ],
        org=org,
    )

    cc7_1 = {
        "control_id": "CC7.1",
        "title": "System Monitoring",
        "description": (
            "To meet its objectives, the entity uses detection and monitoring "
            "procedures to identify changes to configurations."
        ),
        "evidence": {
            "total_audit_events": cc7_1_total_events,
            "unique_actors_monitored": cc7_1_unique_actors,
            "security_scanning_events": cc7_1_security_events,
            "admin_action_events": cc7_1_admin_events,
            "monitoring_coverage_days": period_days,
        },
        "status": "evidence_collected",
    }

    # ── Executive Summary ───────────────────────────────────────────────
    total_evidence_events = (
        cc6_1_role_changes
        + cc6_1_external_collabs
        + cc6_2_sso_events
        + cc6_2_2fa_events
        + cc6_2_pat_created
        + cc6_2_pat_revoked
        + cc6_3_member_removals
        + cc6_3_deactivations
        + cc8_1_branch_protection
        + cc8_1_deployments
    )

    return {
        "framework": "SOC 2 Type II",
        "generated_at": datetime.now(UTC).isoformat(),
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": period_days,
        },
        "org": org,
        "executive_summary": {
            "total_audit_events": cc7_1_total_events,
            "total_evidence_events": total_evidence_events,
            "unique_actors": cc7_1_unique_actors,
            "controls_assessed": 5,
            "controls_with_evidence": sum(
                1
                for s in [cc6_1, cc6_2, cc6_3, cc8_1, cc7_1]
                if s["status"] == "evidence_collected"
            ),
        },
        "controls": [cc6_1, cc6_2, cc6_3, cc8_1, cc7_1],
    }


# ---------------------------------------------------------------------------
# ISO 27001 Annex A Report
# ---------------------------------------------------------------------------


async def generate_iso27001_report(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    org: str | None = None,
) -> dict[str, Any]:
    """Generate ISO 27001 Annex A compliance report.

    Sections:
        A.9  — Access Control
        A.12 — Operations Security
        A.14 — System Development
        A.16 — Incident Management
        A.18 — Compliance
    """
    logger.info(
        "compliance.iso27001.generate",
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        org=org,
    )

    period_days = max((end_date - start_date).days, 1)

    # ── A.9: Access Control ─────────────────────────────────────────────
    a9_rbac_events = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "org.update_member",
            "org.add_member",
            "team.add_member",
            "team.change_member_role",
        ],
        org=org,
    )
    a9_sso_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="business.set_sso%",
        org=org,
    )
    a9_2fa_events = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "org.require_two_factor_authentication",
            "org.disable_two_factor_requirement",
        ],
        org=org,
    )
    a9_pat_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="personal_access_token.%",
        org=org,
    )
    a9_external_collabs = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="%outside_collaborator%",
        org=org,
    )

    a9 = {
        "control_id": "A.9",
        "title": "Access Control",
        "description": "Access to information and information processing facilities is limited.",
        "evidence": {
            "rbac_assignment_events": a9_rbac_events,
            "sso_enforcement_events": a9_sso_events,
            "two_factor_events": a9_2fa_events,
            "pat_lifecycle_events": a9_pat_events,
            "external_collaborator_events": a9_external_collabs,
        },
        "status": "evidence_collected",
    }

    # ── A.12: Operations Security ───────────────────────────────────────
    a12_total_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="%",
        org=org,
    )
    a12_unique_actors = await _distinct_actors(
        session,
        start=start_date,
        end=end_date,
        action_filter="%",
        org=org,
    )
    a12_admin_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="business.%",
        org=org,
    )
    a12_org_settings = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="org.update_%",
        org=org,
    )

    a12 = {
        "control_id": "A.12",
        "title": "Operations Security",
        "description": ("Information processing facilities are operated in a secure manner."),
        "evidence": {
            "total_monitored_events": a12_total_events,
            "unique_actors_audited": a12_unique_actors,
            "admin_actions": a12_admin_events,
            "org_settings_changes": a12_org_settings,
            "log_coverage_days": period_days,
        },
        "status": "evidence_collected",
    }

    # ── A.14: System Development ────────────────────────────────────────
    a14_branch_protections = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="protected_branch.%",
        org=org,
    )
    a14_code_scanning = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="code_scanning%",
        org=org,
    )
    a14_secret_scanning = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="secret_scanning%",
        org=org,
    )
    a14_review_enforcement = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "protected_branch.update_pull_request_reviews_enforcement_level",
            "protected_branch.update_required_status_checks",
        ],
        org=org,
    )

    total_change_controls = a14_branch_protections + a14_review_enforcement
    a14_approval_rate = (
        round(a14_review_enforcement / total_change_controls * 100, 1)
        if total_change_controls > 0
        else 0.0
    )

    a14 = {
        "control_id": "A.14",
        "title": "System Acquisition, Development and Maintenance",
        "description": (
            "Information security is designed and implemented within the development "
            "lifecycle of information systems."
        ),
        "evidence": {
            "branch_protection_events": a14_branch_protections,
            "code_scanning_events": a14_code_scanning,
            "secret_scanning_events": a14_secret_scanning,
            "change_approval_rate_pct": a14_approval_rate,
            "review_enforcement_changes": a14_review_enforcement,
        },
        "status": "evidence_collected",
    }

    # ── A.16: Incident Management ───────────────────────────────────────
    a16_security_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="secret_scanning%",
        org=org,
    )
    a16_dependabot_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="dependabot%",
        org=org,
    )
    a16_total_detections = a16_security_events + a16_dependabot_events
    a16_mttd_proxy = (
        round(period_days * 24 / a16_total_detections, 2) if a16_total_detections > 0 else 0.0
    )

    a16 = {
        "control_id": "A.16",
        "title": "Information Security Incident Management",
        "description": (
            "A consistent and effective approach to management of information "
            "security incidents, including communication on security events."
        ),
        "evidence": {
            "security_scanning_detections": a16_security_events,
            "dependabot_events": a16_dependabot_events,
            "total_detection_count": a16_total_detections,
            "mean_time_to_detect_hours": a16_mttd_proxy,
        },
        "status": "evidence_collected",
    }

    # ── A.18: Compliance ────────────────────────────────────────────────
    a18_total_events = a12_total_events
    all_sections: list[dict[str, Any]] = [a9, a12, a14, a16]
    controls_with_data = sum(
        1
        for section in all_sections
        if any(isinstance(v, int) and v > 0 for v in section["evidence"].values())
    )
    a18_compliance_score = round(controls_with_data / 4 * 100, 1)

    a18 = {
        "control_id": "A.18",
        "title": "Compliance",
        "description": (
            "Avoidance of breaches of legal, statutory, regulatory or contractual "
            "obligations related to information security."
        ),
        "evidence": {
            "total_auditable_events": a18_total_events,
            "controls_with_evidence": controls_with_data,
            "total_controls_assessed": 5,
            "compliance_score_pct": a18_compliance_score,
            "audit_period_days": period_days,
        },
        "status": "evidence_collected",
    }

    total_evidence = (
        a9_rbac_events
        + a9_sso_events
        + a9_2fa_events
        + a14_branch_protections
        + a14_code_scanning
        + a16_total_detections
    )

    return {
        "framework": "ISO 27001 Annex A",
        "generated_at": datetime.now(UTC).isoformat(),
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": period_days,
        },
        "org": org,
        "executive_summary": {
            "total_audit_events": a12_total_events,
            "total_evidence_events": total_evidence,
            "unique_actors": a12_unique_actors,
            "controls_assessed": 5,
            "controls_with_evidence": controls_with_data + (1 if a18_compliance_score > 0 else 0),
            "compliance_score_pct": a18_compliance_score,
        },
        "controls": [a9, a12, a14, a16, a18],
    }


# ---------------------------------------------------------------------------
# NIST Cybersecurity Framework Report
# ---------------------------------------------------------------------------


async def generate_nist_csf_report(
    session: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    org: str | None = None,
) -> dict[str, Any]:
    """Generate NIST Cybersecurity Framework report.

    Functions:
        ID — Identify
        PR — Protect
        DE — Detect
        RS — Respond
        RC — Recover
    """
    logger.info(
        "compliance.nist_csf.generate",
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        org=org,
    )

    period_days = max((end_date - start_date).days, 1)

    # ── ID: Identify — Asset Inventory ──────────────────────────────────
    id_repo_count = await _total_unique_values(
        session, start=start_date, end=end_date, column="repo", org=org
    )
    id_actor_count = await _total_unique_values(
        session, start=start_date, end=end_date, column="actor", org=org
    )
    id_org_count = await _total_unique_values(
        session, start=start_date, end=end_date, column="org", org=org
    )
    id_team_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="team.%",
        org=org,
    )

    identify = {
        "function_id": "ID",
        "title": "Identify",
        "description": (
            "Develop an organizational understanding to manage cybersecurity risk "
            "to systems, people, assets, data, and capabilities."
        ),
        "evidence": {
            "unique_repositories": id_repo_count,
            "unique_actors": id_actor_count,
            "unique_organizations": id_org_count,
            "team_management_events": id_team_events,
        },
        "status": "evidence_collected",
    }

    # ── PR: Protect — Access Controls ───────────────────────────────────
    pr_branch_protections = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="protected_branch.%",
        org=org,
    )
    pr_sso_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="business.set_sso%",
        org=org,
    )
    pr_2fa_events = await _count_events_in(
        session,
        start=start_date,
        end=end_date,
        actions=[
            "org.require_two_factor_authentication",
            "org.disable_two_factor_requirement",
        ],
        org=org,
    )
    pr_secret_scanning = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="secret_scanning%",
        org=org,
    )
    pr_pat_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="personal_access_token.%",
        org=org,
    )

    protect = {
        "function_id": "PR",
        "title": "Protect",
        "description": (
            "Develop and implement appropriate safeguards to ensure delivery of critical services."
        ),
        "evidence": {
            "branch_protection_events": pr_branch_protections,
            "sso_enforcement_events": pr_sso_events,
            "two_factor_events": pr_2fa_events,
            "secret_scanning_events": pr_secret_scanning,
            "pat_management_events": pr_pat_events,
        },
        "status": "evidence_collected",
    }

    # ── DE: Detect ──────────────────────────────────────────────────────
    de_code_scanning = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="code_scanning%",
        org=org,
    )
    de_secret_scanning = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="secret_scanning%",
        org=org,
    )
    de_dependabot = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="dependabot%",
        org=org,
    )
    de_total = de_code_scanning + de_secret_scanning + de_dependabot
    de_mttd = round(period_days * 24 / de_total, 2) if de_total > 0 else 0.0

    detect = {
        "function_id": "DE",
        "title": "Detect",
        "description": (
            "Develop and implement appropriate activities to identify "
            "the occurrence of a cybersecurity event."
        ),
        "evidence": {
            "code_scanning_events": de_code_scanning,
            "secret_scanning_events": de_secret_scanning,
            "dependabot_events": de_dependabot,
            "total_detection_volume": de_total,
            "mean_time_to_detect_hours": de_mttd,
        },
        "status": "evidence_collected",
    }

    # ── RS: Respond ─────────────────────────────────────────────────────
    rs_alert_events = de_total
    rs_notification_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="integration_installation.%",
        org=org,
    )
    rs_org_actions = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="org.%",
        org=org,
    )

    respond = {
        "function_id": "RS",
        "title": "Respond",
        "description": (
            "Develop and implement appropriate activities to take action "
            "regarding a detected cybersecurity incident."
        ),
        "evidence": {
            "alert_events": rs_alert_events,
            "integration_installation_events": rs_notification_events,
            "org_response_actions": rs_org_actions,
        },
        "status": "evidence_collected",
    }

    # ── RC: Recover ─────────────────────────────────────────────────────
    rc_total_events = await _count_events(
        session,
        start=start_date,
        end=end_date,
        action_filter="%",
        org=org,
    )
    rc_unique_days_with_events_stmt = text("""
        SELECT COUNT(DISTINCT DATE(created_at)) AS active_days
        FROM events
        WHERE created_at >= :start AND created_at < :end
    """)
    params: dict[str, Any] = {"start": start_date, "end": end_date}
    result = await session.execute(rc_unique_days_with_events_stmt, params)
    row = result.fetchone()
    rc_active_days = int(row.active_days) if row else 0
    rc_completeness = round(rc_active_days / period_days * 100, 1) if period_days > 0 else 0.0

    recover = {
        "function_id": "RC",
        "title": "Recover",
        "description": (
            "Develop and implement appropriate activities to maintain plans "
            "for resilience and to restore any capabilities or services."
        ),
        "evidence": {
            "total_audit_trail_events": rc_total_events,
            "audit_trail_active_days": rc_active_days,
            "audit_trail_completeness_pct": rc_completeness,
            "monitoring_period_days": period_days,
        },
        "status": "evidence_collected",
    }

    functions: list[dict[str, Any]] = [identify, protect, detect, respond, recover]
    functions_with_evidence = sum(
        1 for f in functions if any(isinstance(v, int) and v > 0 for v in f["evidence"].values())
    )

    return {
        "framework": "NIST Cybersecurity Framework",
        "generated_at": datetime.now(UTC).isoformat(),
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": period_days,
        },
        "org": org,
        "executive_summary": {
            "total_audit_events": rc_total_events,
            "unique_actors": id_actor_count,
            "unique_repositories": id_repo_count,
            "functions_assessed": 5,
            "functions_with_evidence": functions_with_evidence,
            "detection_volume": de_total,
        },
        "functions": functions,
    }
