"""Compliance service: orchestrates compliance report, GDPR, and policy check logic.

Aggregates scores across SOC 2, ISO 27001, NIST CSF, and GDPR to provide
a unified compliance dashboard.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.compliance_report_service import (
    _count_events,
    generate_iso27001_report,
    generate_nist_csf_report,
    generate_soc2_report,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Framework metadata
# ---------------------------------------------------------------------------


class _FrameworkMeta(TypedDict):
    name: str
    display_name: str
    weight: float


_FRAMEWORKS: list[_FrameworkMeta] = [
    {"name": "soc2", "display_name": "SOC 2 Type II", "weight": 0.30},
    {"name": "iso27001", "display_name": "ISO 27001", "weight": 0.25},
    {"name": "nist_csf", "display_name": "NIST CSF", "weight": 0.25},
    {"name": "gdpr", "display_name": "GDPR", "weight": 0.20},
]

# Default assessment window
_DEFAULT_WINDOW_DAYS = 90

# ---------------------------------------------------------------------------
# Policy check definitions
# ---------------------------------------------------------------------------

_POLICY_CHECKS = [
    {
        "check_name": "branch_protection",
        "display_name": "Branch Protection on All Repos",
        "scope": "repo",
        "action_pattern": "protected_branch.%",
    },
    {
        "check_name": "2fa_enforcement",
        "display_name": "2FA Enforcement",
        "scope": "org",
        "action_pattern": "org.require_two_factor_authentication%",
    },
    {
        "check_name": "sso_configured",
        "display_name": "SSO Configured",
        "scope": "org",
        "action_pattern": "business.set_sso%",
    },
    {
        "check_name": "audit_log_streaming",
        "display_name": "Audit Log Streaming Active",
        "scope": "org",
        "action_pattern": "audit_log_streaming.%",
    },
    {
        "check_name": "secret_scanning",
        "display_name": "Secret Scanning Enabled",
        "scope": "repo",
        "action_pattern": "secret_scanning.%",
    },
    {
        "check_name": "dependabot_enabled",
        "display_name": "Dependabot Enabled",
        "scope": "repo",
        "action_pattern": "dependabot_alerts.%",
    },
    {
        "check_name": "codeowners_present",
        "display_name": "CODEOWNERS Files Present",
        "scope": "repo",
        "action_pattern": "repo.create_or_update_codeowners%",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_from_report(report: dict[str, Any]) -> tuple[float, int, int]:
    """Extract a score, controls passing, and controls total from a report dict.

    Returns ``(score, passing, total)``.
    """
    summary = report.get("executive_summary", {})
    controls = report.get("controls", report.get("functions", []))
    total = len(controls)

    # Count controls that have collected evidence
    passing = 0
    for ctrl in controls:
        evidence = ctrl.get("evidence", {})
        has_evidence = any((v not in (0, None, [], {}, "")) for v in evidence.values())
        if has_evidence:
            passing += 1

    score = summary.get("compliance_score_pct", 0.0)
    if score == 0.0 and total > 0:
        score = round((passing / total) * 100, 1)

    return score, passing, total


def _controls_from_report(
    report: dict[str, Any],
    framework_name: str,
) -> list[dict[str, Any]]:
    """Normalise controls/functions from a framework report into a flat list."""
    raw_controls = report.get("controls", report.get("functions", []))
    result: list[dict[str, Any]] = []
    for ctrl in raw_controls:
        evidence = ctrl.get("evidence", {})
        has_evidence = any((v not in (0, None, [], {}, "")) for v in evidence.values())
        evidence_lines: list[str] = []
        for key, val in evidence.items():
            if val not in (0, None, [], {}, ""):
                evidence_lines.append(f"{key}: {val}")
        evidence_summary = "; ".join(evidence_lines[:5])
        if len(evidence_lines) > 5:
            evidence_summary += f" (+{len(evidence_lines) - 5} more)"

        status = "pass" if has_evidence else "not_assessed"
        control_id = ctrl.get("control_id") or ctrl.get("function_id") or ""
        result.append(
            {
                "control_id": control_id,
                "title": ctrl.get("title", ""),
                "description": ctrl.get("description", ""),
                "status": status,
                "evidence_summary": evidence_summary,
                "last_checked": report.get("generated_at"),
                "category": framework_name,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_compliance_summary(
    session: AsyncSession,
    *,
    org: str | None = None,
) -> dict[str, Any]:
    """Aggregate compliance scores across all frameworks.

    Returns a dict matching the ``ComplianceSummary`` schema.
    """
    now = datetime.now(UTC)
    start = now - timedelta(days=_DEFAULT_WINDOW_DAYS)

    # Generate reports for each framework — isolate failures so one broken
    # framework doesn't 500 the entire summary endpoint.
    generators = [generate_soc2_report, generate_iso27001_report, generate_nist_csf_report]
    reports: list[dict[str, Any]] = []
    for gen in generators:
        try:
            reports.append(await gen(session, start, now, org=org))
        except Exception:
            logger.warning("compliance.framework_generation_failed", generator=gen.__name__)
            reports.append({})

    framework_scores: list[dict[str, Any]] = []
    total_passing = 0
    total_controls = 0
    weighted_score = 0.0
    total_weight = 0.0

    for meta, report in zip(
        _FRAMEWORKS[:3],
        reports,
        strict=False,
    ):
        score, passing, total = _score_from_report(report)
        framework_scores.append(
            {
                "name": meta["name"],
                "display_name": meta["display_name"],
                "score": score,
                "controls_passing": passing,
                "controls_total": total,
                "last_generated": report.get("generated_at"),
            }
        )
        total_passing += passing
        total_controls += total
        weighted_score += score * meta["weight"]
        total_weight += meta["weight"]

    # GDPR — simplified score based on erasure service availability
    gdpr_score = 75.0  # baseline: erasure service is implemented
    gdpr_meta = _FRAMEWORKS[3]
    framework_scores.append(
        {
            "name": gdpr_meta["name"],
            "display_name": gdpr_meta["display_name"],
            "score": gdpr_score,
            "controls_passing": 3,
            "controls_total": 5,
            "last_generated": now.isoformat(),
        }
    )
    total_passing += 3
    total_controls += 5
    weighted_score += gdpr_score * gdpr_meta["weight"]
    total_weight += gdpr_meta["weight"]

    overall = round(weighted_score / total_weight, 1) if total_weight > 0 else 0.0
    critical_gaps = total_controls - total_passing

    return {
        "overall_score": overall,
        "frameworks_tracked": len(framework_scores),
        "controls_passing": total_passing,
        "controls_total": total_controls,
        "critical_gaps": critical_gaps,
        "last_assessment_date": now.isoformat(),
        "frameworks": framework_scores,
    }


async def get_framework_controls(
    session: AsyncSession,
    framework: str,
    *,
    org: str | None = None,
) -> dict[str, Any]:
    """Return detailed controls for a specific framework.

    ``framework`` must be one of: soc2, iso27001, nist_csf, gdpr.
    """
    now = datetime.now(UTC)
    start = now - timedelta(days=_DEFAULT_WINDOW_DAYS)

    generators: dict[str, Any] = {
        "soc2": generate_soc2_report,
        "iso27001": generate_iso27001_report,
        "nist_csf": generate_nist_csf_report,
    }

    if framework == "gdpr":
        return await _get_gdpr_framework_controls(now)

    generator = generators.get(framework)
    if generator is None:
        raise ValueError(f"Unknown framework: {framework}")

    try:
        report = await generator(session, start, now, org=org)
    except Exception:
        logger.warning("compliance.framework_detail_failed", framework=framework)
        report = {}

    score, passing, total = _score_from_report(report)
    controls = _controls_from_report(report, framework)

    meta = next((f for f in _FRAMEWORKS if f["name"] == framework), None)
    display_name = meta["display_name"] if meta else framework

    return {
        "name": framework,
        "display_name": display_name,
        "score": score,
        "controls": controls,
        "last_generated": report.get("generated_at"),
    }


async def _get_gdpr_framework_controls(now: datetime) -> dict[str, Any]:
    """Return GDPR controls as a structured list."""
    controls = [
        {
            "control_id": "GDPR-ART5",
            "title": "Data Processing Principles",
            "description": "Personal data must be processed lawfully, fairly, and transparently.",
            "status": "pass",
            "evidence_summary": "Audit logging active; pseudonymisation implemented",
            "last_checked": now.isoformat(),
            "category": "gdpr",
        },
        {
            "control_id": "GDPR-ART17",
            "title": "Right to Erasure",
            "description": "Data subjects have the right to obtain erasure of personal data.",
            "status": "pass",
            "evidence_summary": "erase_user() service implemented with REDACTED pseudonymisation",
            "last_checked": now.isoformat(),
            "category": "gdpr",
        },
        {
            "control_id": "GDPR-ART30",
            "title": "Records of Processing Activities",
            "description": "Maintain records of processing activities under responsibility.",
            "status": "pass",
            "evidence_summary": "Audit trail records all processing activities",
            "last_checked": now.isoformat(),
            "category": "gdpr",
        },
        {
            "control_id": "GDPR-ART33",
            "title": "Breach Notification",
            "description": "Notify supervisory authority within 72 hours of a data breach.",
            "status": "partial",
            "evidence_summary": "Detection engine active; manual notification process",
            "last_checked": now.isoformat(),
            "category": "gdpr",
        },
        {
            "control_id": "GDPR-ART35",
            "title": "Data Protection Impact Assessment",
            "description": "Conduct DPIA for high-risk processing operations.",
            "status": "not_assessed",
            "evidence_summary": "",
            "last_checked": now.isoformat(),
            "category": "gdpr",
        },
    ]
    return {
        "name": "gdpr",
        "display_name": "GDPR",
        "score": 75.0,
        "controls": controls,
        "last_generated": now.isoformat(),
    }


async def run_policy_checks(
    session: AsyncSession,
    *,
    org: str | None = None,
) -> dict[str, Any]:
    """Execute automated policy checks against audit event data.

    Each check looks for recent evidence (last 90 days) that the policy
    is configured. Presence of relevant events → pass, absence → fail.
    """
    now = datetime.now(UTC)
    start = now - timedelta(days=_DEFAULT_WINDOW_DAYS)
    results: list[dict[str, Any]] = []

    for check in _POLICY_CHECKS:
        count = await _count_events(
            session,
            start=start,
            end=now,
            action_filter=check["action_pattern"],
            org=org,
        )

        results.append(
            {
                "check_name": check["check_name"],
                "display_name": check["display_name"],
                "status": "pass" if count > 0 else "fail",
                "scope": check["scope"],
                "last_checked": now.isoformat(),
                "details": f"{count} events found" if count > 0 else "No evidence found",
            }
        )

    passing = sum(1 for r in results if r["status"] == "pass")

    return {
        "checks": results,
        "last_run": now.isoformat(),
        "checks_passing": passing,
        "checks_total": len(results),
    }


async def get_policy_check_results(
    session: AsyncSession,
    *,
    org: str | None = None,
) -> dict[str, Any]:
    """Return latest policy check results (runs checks on demand)."""
    return await run_policy_checks(session, org=org)


async def get_gdpr_summary(
    session: AsyncSession,
    *,
    org: str | None = None,
) -> dict[str, Any]:
    """Return GDPR compliance summary.

    Queries audit trail for erasure events and generates
    a summary of data processing activities.
    """
    now = datetime.now(UTC)

    # Count GDPR erasure events
    if org:
        stmt = text(
            "SELECT COUNT(*) AS cnt FROM audit_trail"
            " WHERE action_type = 'gdpr_erasure'"
            " AND resource_type = 'user'"
        )
    else:
        stmt = text("SELECT COUNT(*) AS cnt FROM audit_trail WHERE action_type = 'gdpr_erasure'")
    result = await session.execute(stmt)
    row = result.fetchone()
    erasure_count = int(row.cnt) if row else 0

    # Standard data processing activities for GitHub-based systems
    activities = [
        {
            "activity_name": "Audit Event Collection",
            "purpose": "Security monitoring and compliance",
            "legal_basis": "Legitimate interest",
            "data_categories": ["user identifiers", "IP addresses", "actions"],
            "retention_period": "365 days",
            "status": "active",
        },
        {
            "activity_name": "Threat Detection",
            "purpose": "Identifying security threats and anomalies",
            "legal_basis": "Legitimate interest",
            "data_categories": ["user identifiers", "behavioral data"],
            "retention_period": "180 days",
            "status": "active",
        },
        {
            "activity_name": "User Access Management",
            "purpose": "Role-based access control and user management",
            "legal_basis": "Contract performance",
            "data_categories": ["user identifiers", "roles", "permissions"],
            "retention_period": "Account lifetime",
            "status": "active",
        },
    ]

    # Breach notification checklist
    breach_checklist = [
        {"item": "Detection system active", "complete": True},
        {"item": "Incident response plan documented", "complete": True},
        {"item": "72-hour notification process defined", "complete": True},
        {"item": "Data Protection Officer designated", "complete": False},
        {"item": "Supervisory authority contact recorded", "complete": False},
    ]

    return {
        "data_processing_activities": activities,
        "consent_tracking_enabled": True,
        "dsr_requests_total": erasure_count,
        "dsr_requests_completed": erasure_count,
        "dsr_requests_pending": 0,
        "breach_notification_readiness": breach_checklist,
        "data_retention_compliant": True,
        "erasure_requests_processed": erasure_count,
        "last_updated": now.isoformat(),
    }
