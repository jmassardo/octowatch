"""Supply chain security analysis service.

Provides workflow file analysis, supply chain posture assessment,
and dependency risk summarisation based on audit log events and
detection rules in the ``supply_chain`` category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.detection import RuleDefinition

logger = structlog.get_logger(__name__)

# ── Well-known safe action owners ────────────────────────────────────────────

_VERIFIED_ACTION_ORGS: set[str] = {
    "actions",
    "github",
    "azure",
    "aws-actions",
    "google-github-actions",
    "docker",
    "hashicorp",
    "codecov",
    "softprops",
    "peter-evans",
}

_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_ACTION_USES_RE = re.compile(r"uses:\s*([^\s#]+)")
_PR_TARGET_RE = re.compile(r"pull_request_target", re.IGNORECASE)
_CHECKOUT_HEAD_RE = re.compile(
    r"actions/checkout.*ref.*github\.event\.pull_request\.head",
    re.DOTALL,
)
_EXPRESSION_INJECTION_RE = re.compile(
    r"\$\{\{.*github\.event\.(issue|comment|pull_request|discussion)"
)


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class SupplyChainFinding:
    """A single supply-chain risk discovered in a workflow file."""

    rule_slug: str
    title: str
    severity: str
    confidence: str
    line: int | None
    detail: str
    recommendation: str


@dataclass
class SupplyChainPosture:
    """Aggregate supply chain security posture across scoped orgs."""

    score: int  # 0-100
    unpinned_actions: int
    dependency_alerts: int
    risky_workflows: int
    rules_active: int
    total_detections: int
    critical_detections: int
    recent_risks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DependencyRiskSummary:
    """Summary of dependency-related risks across orgs."""

    total_risks: int
    by_severity: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)
    top_repos: list[dict[str, Any]] = field(default_factory=list)


# ── Workflow analysis ────────────────────────────────────────────────────────


async def analyze_workflow_file(content: str) -> list[SupplyChainFinding]:
    """Analyse a workflow YAML string for supply-chain risks.

    Checks performed:
    * Unpinned actions (referenced by branch/tag instead of SHA)
    * ``pull_request_target`` with checkout of PR head
    * Actions from unverified / unusual organisations
    * Expression injection in ``run:`` blocks
    """
    findings: list[SupplyChainFinding] = []
    lines = content.splitlines()

    has_pr_target = bool(_PR_TARGET_RE.search(content))
    has_checkout_head = bool(_CHECKOUT_HEAD_RE.search(content))

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()

        # ── Check for action references ──────────────────────────────
        match = _ACTION_USES_RE.search(stripped)
        if match:
            action_ref = match.group(1)
            findings.extend(_check_action_ref(action_ref, line_no))

        # ── Expression injection in run blocks ───────────────────────
        is_run = (
            stripped.startswith("run:")
            or stripped.startswith("- run:")
            or stripped.startswith("run: |")
        )
        if is_run:
            injection_match = _EXPRESSION_INJECTION_RE.search(stripped)
            if injection_match:
                findings.append(
                    SupplyChainFinding(
                        rule_slug="workflow-injection",
                        title="Potential expression injection",
                        severity="high",
                        confidence="medium",
                        line=line_no,
                        detail=(
                            f"Untrusted GitHub event data used in run block: "
                            f"{injection_match.group(0)}"
                        ),
                        recommendation=(
                            "Use an intermediate environment variable instead "
                            "of inline expressions to prevent script injection."
                        ),
                    )
                )

    # ── pull_request_target with checkout of PR head ─────────────────
    if has_pr_target and has_checkout_head:
        findings.append(
            SupplyChainFinding(
                rule_slug="workflow-injection",
                title="Dangerous pull_request_target with PR head checkout",
                severity="critical",
                confidence="high",
                line=None,
                detail=(
                    "This workflow uses pull_request_target and checks out the "
                    "PR head, allowing untrusted code to run with write "
                    "permissions and access to secrets."
                ),
                recommendation=(
                    "Avoid checking out PR head code in pull_request_target "
                    "workflows. Use pull_request trigger instead, or isolate "
                    "untrusted code in a separate workflow without secret access."
                ),
            )
        )

    return findings


def _check_action_ref(action_ref: str, line_no: int) -> list[SupplyChainFinding]:
    """Return findings for a single ``uses:`` reference."""
    findings: list[SupplyChainFinding] = []

    # Skip local actions (./path) and Docker references
    if action_ref.startswith("./") or action_ref.startswith("docker://"):
        return findings

    parts = action_ref.split("@", maxsplit=1)
    if len(parts) != 2:
        return findings

    action_path, version = parts
    owner = action_path.split("/")[0] if "/" in action_path else action_path

    # ── Pinning check ────────────────────────────────────────────────
    if not _SHA_RE.match(version):
        findings.append(
            SupplyChainFinding(
                rule_slug="action-version-pinning-violation",
                title="Unpinned GitHub Action",
                severity="medium",
                confidence="high",
                line=line_no,
                detail=(
                    f"Action '{action_ref}' is referenced by tag/branch "
                    f"'{version}' instead of a commit SHA."
                ),
                recommendation=(
                    f"Pin '{action_path}' to a full commit SHA (e.g., {action_path}@<40-char-sha>)."
                ),
            )
        )

    # ── Unverified org check ─────────────────────────────────────────
    if owner.lower() not in _VERIFIED_ACTION_ORGS:
        findings.append(
            SupplyChainFinding(
                rule_slug="malicious-github-action",
                title="Action from unverified organisation",
                severity="high" if not _SHA_RE.match(version) else "medium",
                confidence="medium",
                line=line_no,
                detail=(
                    f"Action '{action_ref}' is from organisation '{owner}' "
                    f"which is not in the verified-safe list."
                ),
                recommendation=(
                    f"Verify that '{owner}' is a trusted publisher. "
                    f"Consider forking the action into your org or pinning "
                    f"to a specific commit SHA after code review."
                ),
            )
        )

    return findings


# ── Posture & risk queries ───────────────────────────────────────────────────


async def get_supply_chain_posture(
    session: AsyncSession,
    scoped_orgs: list[str],
) -> SupplyChainPosture:
    """Overall supply chain security posture for *scoped_orgs*."""

    # Count active supply-chain rules
    rules_q = await session.execute(
        text(
            "SELECT count(*) FROM rule_definitions "
            "WHERE category = 'supply_chain' AND enabled = true AND status = 'active'"
        )
    )
    rules_active = rules_q.scalar() or 0

    # Detection stats scoped by org
    org_filter, params = _org_filter(scoped_orgs)

    total_q = await session.execute(
        text(
            "SELECT count(*) FROM detections d "
            "JOIN rule_definitions r ON d.rule_id = r.id "
            f"WHERE r.category = 'supply_chain' {org_filter}"
        ),
        params,
    )
    total_detections = total_q.scalar() or 0

    critical_q = await session.execute(
        text(
            "SELECT count(*) FROM detections d "
            "JOIN rule_definitions r ON d.rule_id = r.id "
            f"WHERE r.category = 'supply_chain' AND d.severity = 'critical' {org_filter}"
        ),
        params,
    )
    critical_detections = critical_q.scalar() or 0

    # Count detections by slug for specific metrics
    slug_counts = await _count_detections_by_slug(session, scoped_orgs)
    unpinned = slug_counts.get("action-version-pinning-violation", 0)
    risky = slug_counts.get("workflow-injection", 0)

    # Dependency alerts (Dependabot-related events)
    dep_q = await session.execute(
        text(
            "SELECT count(*) FROM audit_events "
            f"WHERE action LIKE 'dependabot_alerts.%%' {org_filter}"
        ),
        params,
    )
    dep_alerts = dep_q.scalar() or 0

    # Compute score (100 = perfect, deductions for issues)
    score = _compute_score(
        total_detections=total_detections,
        critical=critical_detections,
        unpinned=unpinned,
        risky_workflows=risky,
    )

    # Recent risks (last 10 detections)
    recent_q = await session.execute(
        text(
            "SELECT d.id, d.title, d.severity, d.status, d.org, d.repo, "
            "d.triggered_at, r.slug as rule_slug "
            "FROM detections d "
            "JOIN rule_definitions r ON d.rule_id = r.id "
            f"WHERE r.category = 'supply_chain' {org_filter} "
            "ORDER BY d.triggered_at DESC LIMIT 10"
        ),
        params,
    )
    recent_rows = recent_q.fetchall()
    recent_risks = [
        {
            "id": r.id,
            "title": r.title,
            "severity": r.severity,
            "status": r.status,
            "org": r.org,
            "repo": r.repo,
            "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
            "rule_slug": r.rule_slug,
        }
        for r in recent_rows
    ]

    return SupplyChainPosture(
        score=score,
        unpinned_actions=unpinned,
        dependency_alerts=dep_alerts,
        risky_workflows=risky,
        rules_active=rules_active,
        total_detections=total_detections,
        critical_detections=critical_detections,
        recent_risks=recent_risks,
    )


async def get_dependency_risk_summary(
    session: AsyncSession,
    scoped_orgs: list[str],
) -> DependencyRiskSummary:
    """Summary of dependency-related risks across scoped orgs."""
    org_filter, params = _org_filter(scoped_orgs)

    # By severity
    sev_q = await session.execute(
        text(
            "SELECT d.severity, count(*) as cnt FROM detections d "
            "JOIN rule_definitions r ON d.rule_id = r.id "
            f"WHERE r.category = 'supply_chain' {org_filter} "
            "GROUP BY d.severity"
        ),
        params,
    )
    by_severity: dict[str, int] = {row.severity: row.cnt for row in sev_q.fetchall()}

    # By rule slug (type)
    type_q = await session.execute(
        text(
            "SELECT r.slug, count(*) as cnt FROM detections d "
            "JOIN rule_definitions r ON d.rule_id = r.id "
            f"WHERE r.category = 'supply_chain' {org_filter} "
            "GROUP BY r.slug"
        ),
        params,
    )
    by_type: dict[str, int] = {row.slug: row.cnt for row in type_q.fetchall()}

    # Top repos by risk count
    repo_q = await session.execute(
        text(
            "SELECT d.repo, count(*) as cnt FROM detections d "
            "JOIN rule_definitions r ON d.rule_id = r.id "
            f"WHERE r.category = 'supply_chain' AND d.repo IS NOT NULL {org_filter} "
            "GROUP BY d.repo ORDER BY cnt DESC LIMIT 10"
        ),
        params,
    )
    top_repos = [{"repo": row.repo, "count": row.cnt} for row in repo_q.fetchall()]

    total = sum(by_severity.values())

    return DependencyRiskSummary(
        total_risks=total,
        by_severity=by_severity,
        by_type=by_type,
        top_repos=top_repos,
    )


# ── Rule seeding ─────────────────────────────────────────────────────────────


async def seed_supply_chain_rules(session: AsyncSession) -> int:
    """Seed supply-chain detection rules from the fixture file.

    Inserts rules whose slug does not already exist, returning the number
    of newly created rules.
    """
    import json
    from pathlib import Path

    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "supply_chain_rules.json"
    with open(fixture_path) as f:
        rules_data: list[dict[str, Any]] = json.load(f)

    created = 0
    for rule in rules_data:
        existing = await session.execute(
            text("SELECT id FROM rule_definitions WHERE slug = :slug"),
            {"slug": rule["slug"]},
        )
        if existing.scalar() is not None:
            continue

        new_rule = RuleDefinition(
            name=rule["name"],
            slug=rule["slug"],
            description=rule["description"],
            category=rule["category"],
            default_severity=rule["default_severity"],
            default_confidence=rule["default_confidence"],
            logic_type=rule["logic_type"],
            logic_config=rule["logic_config"],
            created_by=rule.get("created_by", "system"),
        )
        session.add(new_rule)
        created += 1

    if created > 0:
        await session.flush()
        logger.info("seeded supply-chain rules", created=created)

    return created


# ── Helpers ──────────────────────────────────────────────────────────────────


def _org_filter(scoped_orgs: list[str]) -> tuple[str, dict[str, Any]]:
    """Build an org-scoping SQL fragment and parameter dict."""
    if not scoped_orgs:
        return "", {}
    placeholders = ", ".join(f":org_{i}" for i in range(len(scoped_orgs)))
    params = {f"org_{i}": org for i, org in enumerate(scoped_orgs)}
    return f"AND d.org IN ({placeholders})", params


async def _count_detections_by_slug(
    session: AsyncSession,
    scoped_orgs: list[str],
) -> dict[str, int]:
    """Count open detections grouped by rule slug for supply-chain rules."""
    org_filter, params = _org_filter(scoped_orgs)
    q = await session.execute(
        text(
            "SELECT r.slug, count(*) as cnt FROM detections d "
            "JOIN rule_definitions r ON d.rule_id = r.id "
            f"WHERE r.category = 'supply_chain' AND d.status = 'open' {org_filter} "
            "GROUP BY r.slug"
        ),
        params,
    )
    return {row.slug: row.cnt for row in q.fetchall()}


def _compute_score(
    *,
    total_detections: int,
    critical: int,
    unpinned: int,
    risky_workflows: int,
) -> int:
    """Compute a 0-100 supply chain health score.

    Starts at 100 and applies deductions for detected issues.
    """
    score = 100
    # Critical detections: -10 each, max -40
    score -= min(critical * 10, 40)
    # Unpinned actions: -2 each, max -20
    score -= min(unpinned * 2, 20)
    # Risky workflows: -5 each, max -20
    score -= min(risky_workflows * 5, 20)
    # General detections (non-critical): -1 each, max -20
    non_critical = max(total_detections - critical, 0)
    score -= min(non_critical, 20)
    return max(score, 0)
