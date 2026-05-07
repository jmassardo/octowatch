"""Team health analytics service: bus factor, engagement tiers, policy violations.

All metrics are computed from the ``events`` table using raw SQL queries,
consistent with the patterns in ``dev_activity`` and ``health_signal_service``.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ── Bus Factor ────────────────────────────────────────────────────────────────


async def get_bus_factor(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int = 90,
) -> list[dict[str, Any]]:
    """Calculate bus factor per repository.

    Bus factor = minimum number of developers who, if they left, would leave
    a repo with no one who understands the code.

    Approximation:
    - Count distinct actors who contributed (``git.push`` or ``pull_request.*``)
      in the lookback window.
    - Calculate each contributor's share of total commits/events.
    - If only 1-2 devs contributed >80% of events → bus_factor = 1 (critical).
    - Bus factor = count of developers who each contributed ≥10% of events,
      capped at 5.
    """
    result = await db.execute(
        text("""
            WITH repo_actor_counts AS (
                SELECT
                    repo,
                    actor,
                    COUNT(*) AS event_count
                FROM events
                WHERE repo IS NOT NULL
                  AND actor IS NOT NULL AND actor != ''
                  AND actor NOT LIKE :bot_suffix
                  AND (action = 'git.push' OR action LIKE :pr_pattern)
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                GROUP BY repo, actor
            ),
            repo_totals AS (
                SELECT
                    repo,
                    SUM(event_count) AS total_events,
                    COUNT(DISTINCT actor) AS contributor_count
                FROM repo_actor_counts
                GROUP BY repo
            ),
            repo_contributors AS (
                SELECT
                    rac.repo,
                    rac.actor,
                    rac.event_count,
                    rt.total_events,
                    rt.contributor_count,
                    ROUND(rac.event_count::numeric / rt.total_events * 100, 1) AS pct
                FROM repo_actor_counts rac
                JOIN repo_totals rt ON rt.repo = rac.repo
            )
            SELECT
                rc.repo,
                rc.contributor_count,
                ARRAY_AGG(rc.actor ORDER BY rc.event_count DESC) AS contributors,
                ARRAY_AGG(rc.pct ORDER BY rc.event_count DESC) AS pcts
            FROM repo_contributors rc
            GROUP BY rc.repo, rc.contributor_count
            ORDER BY rc.contributor_count ASC
        """),
        {
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "bot_suffix": "%[bot]",
            "pr_pattern": "pull_request.%",
        },
    )

    repos: list[dict[str, Any]] = []
    for row in result.fetchall():
        repo_name = row[0]
        contributor_count = row[1]
        contributors = list(row[2]) if row[2] else []
        pcts = [float(p) for p in row[3]] if row[3] else []

        # Bus factor = count of devs who each contributed >= 10%
        significant = sum(1 for p in pcts if p >= 10.0)
        bus_factor = max(1, min(significant, 5))

        # Check if top 1-2 devs dominate (>80%)
        top_two_pct = sum(pcts[:2]) if len(pcts) >= 2 else sum(pcts)
        if top_two_pct > 80.0 and contributor_count <= 2:
            bus_factor = 1

        if bus_factor <= 1:
            risk_level = "critical"
        elif bus_factor == 2:
            risk_level = "high"
        elif bus_factor <= 3:
            risk_level = "medium"
        else:
            risk_level = "low"

        top_contributors = [
            {"login": contributors[i], "pct": pcts[i]} for i in range(min(5, len(contributors)))
        ]

        repos.append(
            {
                "repo": repo_name,
                "bus_factor": bus_factor,
                "contributor_count": contributor_count,
                "top_contributors": top_contributors,
                "risk_level": risk_level,
            }
        )

    # Sort by bus_factor ascending (worst first)
    repos.sort(key=lambda r: (r["bus_factor"], r["repo"]))
    return repos


# ── Knowledge Concentration ──────────────────────────────────────────────────


async def get_knowledge_concentration(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int = 90,
) -> list[dict[str, Any]]:
    """Find repos/areas where knowledge is concentrated in few people.

    Returns repos where a single developer owns >50% of activity.
    """
    result = await db.execute(
        text("""
            WITH repo_actor_counts AS (
                SELECT
                    repo,
                    actor,
                    COUNT(*) AS event_count
                FROM events
                WHERE repo IS NOT NULL
                  AND actor IS NOT NULL AND actor != ''
                  AND actor NOT LIKE :bot_suffix
                  AND (action = 'git.push' OR action LIKE :pr_pattern)
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                GROUP BY repo, actor
            ),
            repo_totals AS (
                SELECT repo, SUM(event_count) AS total_events
                FROM repo_actor_counts
                GROUP BY repo
            ),
            top_contributor AS (
                SELECT DISTINCT ON (rac.repo)
                    rac.repo,
                    rac.actor AS top_actor,
                    rac.event_count,
                    rt.total_events,
                    ROUND(rac.event_count::numeric / rt.total_events * 100, 1) AS pct
                FROM repo_actor_counts rac
                JOIN repo_totals rt ON rt.repo = rac.repo
                ORDER BY rac.repo, rac.event_count DESC
            )
            SELECT repo, top_actor, pct, total_events
            FROM top_contributor
            WHERE pct > 50
            ORDER BY pct DESC
        """),
        {
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "bot_suffix": "%[bot]",
            "pr_pattern": "pull_request.%",
        },
    )

    risks: list[dict[str, Any]] = []
    for row in result.fetchall():
        pct = float(row[2])
        if pct >= 80:
            risk_level = "high"
        elif pct >= 65:
            risk_level = "medium"
        else:
            risk_level = "low"

        risks.append(
            {
                "repo": row[0],
                "top_actor": row[1],
                "concentration_pct": pct,
                "total_events": row[3],
                "risk_level": risk_level,
                "recommendation": (
                    f"Consider cross-team code reviews for {row[0]} "
                    f"to reduce dependency on @{row[1]}"
                ),
            }
        )

    return risks


# ── Developer Engagement Tiers ───────────────────────────────────────────────


async def get_developer_engagement(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int = 30,
) -> dict[str, Any]:
    """Classify developers into engagement tiers.

    Tiers based on last activity:
    - Active: events in last 7 days
    - Regular: last event 7-14 days ago
    - Occasional: last event 14-30 days ago
    - Dormant: last event >30 days ago (or within full lookback window)
    """
    result = await db.execute(
        text("""
            SELECT
                actor,
                MAX(created_at) AS last_active,
                COUNT(*) AS event_count
            FROM events
            WHERE actor IS NOT NULL AND actor != ''
              AND actor NOT LIKE :bot_suffix
              AND org = ANY(:scoped_orgs)
              AND (
                  action = 'git.push'
                  OR action LIKE :pr_pattern
                  OR action LIKE :repo_pattern
              )
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
            GROUP BY actor
            ORDER BY last_active DESC
        """),
        {
            "scoped_orgs": scoped_orgs,
            "lookback_days": max(lookback_days, 90),
            "bot_suffix": "%[bot]",
            "pr_pattern": "pull_request.%",
            "repo_pattern": "repo.%",
        },
    )

    tiers: dict[str, list[dict[str, Any]]] = {
        "active": [],
        "regular": [],
        "occasional": [],
        "dormant": [],
    }

    for row in result.fetchall():
        actor = row[0]
        last_active = row[1]
        event_count = row[2]

        dev_info = {
            "login": actor,
            "last_active": last_active.isoformat() if last_active else None,
            "event_count": event_count,
        }

        if last_active is None:
            tiers["dormant"].append(dev_info)
            continue

        from datetime import UTC, datetime

        now = datetime.now(UTC)
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=UTC)
        days_since = (now - last_active).days

        if days_since <= 7:
            tiers["active"].append(dev_info)
        elif days_since <= 14:
            tiers["regular"].append(dev_info)
        elif days_since <= 30:
            tiers["occasional"].append(dev_info)
        else:
            tiers["dormant"].append(dev_info)

    total = sum(len(v) for v in tiers.values())

    return {
        "tiers": tiers,
        "counts": {k: len(v) for k, v in tiers.items()},
        "total_developers": total,
        "active_pct": round(len(tiers["active"]) / total * 100, 1) if total > 0 else 0,
    }


# ── Engagement Trend ─────────────────────────────────────────────────────────


async def get_engagement_trend(
    db: AsyncSession,
    scoped_orgs: list[str],
) -> list[dict[str, Any]]:
    """Return monthly engagement tier distribution for the last 3 months."""
    result = await db.execute(
        text("""
            WITH monthly_actors AS (
                SELECT
                    DATE_TRUNC('month', created_at) AS month,
                    actor,
                    MAX(created_at) AS last_active_in_month
                FROM events
                WHERE actor IS NOT NULL AND actor != ''
                  AND actor NOT LIKE :bot_suffix
                  AND org = ANY(:scoped_orgs)
                  AND (
                      action = 'git.push'
                      OR action LIKE :pr_pattern
                      OR action LIKE :repo_pattern
                  )
                  AND created_at >= NOW() - INTERVAL '3 months'
                GROUP BY DATE_TRUNC('month', created_at), actor
            )
            SELECT
                month,
                COUNT(DISTINCT actor) AS total
            FROM monthly_actors
            GROUP BY month
            ORDER BY month
        """),
        {
            "scoped_orgs": scoped_orgs,
            "bot_suffix": "%[bot]",
            "pr_pattern": "pull_request.%",
            "repo_pattern": "repo.%",
        },
    )

    trend: list[dict[str, Any]] = []
    for row in result.fetchall():
        trend.append(
            {
                "month": str(row[0].date()) if row[0] else None,
                "active_developers": row[1],
            }
        )

    return trend


# ── Policy Violations ────────────────────────────────────────────────────────


_VIOLATION_ACTIONS: dict[str, dict[str, str]] = {
    "protected_branch.policy_override": {
        "type": "branch_protection_bypass",
        "severity": "high",
        "description": "Branch protection policy override",
    },
    "protected_branch.destroy": {
        "type": "branch_protection_bypass",
        "severity": "high",
        "description": "Branch protection rule deleted",
    },
    "protected_branch.update": {
        "type": "branch_protection_bypass",
        "severity": "medium",
        "description": "Branch protection rule modified",
    },
    "protected_branch.rejected_ref_update": {
        "type": "branch_protection_bypass",
        "severity": "medium",
        "description": "Branch protection rejected a push",
    },
    "git.push": {
        "type": "force_push_default_branch",
        "severity": "high",
        "description": "Force push to default branch",
    },
    "org.update_member": {
        "type": "admin_permission_escalation",
        "severity": "high",
        "description": "Organization member permission changed",
    },
    "org.add_member": {
        "type": "admin_permission_escalation",
        "severity": "medium",
        "description": "New member added to organization",
    },
    "two_factor_authentication.disabled": {
        "type": "2fa_disabled",
        "severity": "critical",
        "description": "Two-factor authentication disabled",
    },
    "public_key.create": {
        "type": "ssh_key_added",
        "severity": "medium",
        "description": "SSH key added",
    },
}


async def get_policy_violations(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int = 30,
) -> dict[str, Any]:
    """Detect policy violations from audit log event patterns.

    Violation types:
    - Branch protection bypass (protected_branch.* events)
    - Force push (git.push with force flag in data)
    - Admin permission escalation (org.update_member / org.add_member)
    - 2FA disabled
    - SSH key added
    """
    actions = list(_VIOLATION_ACTIONS.keys())

    result = await db.execute(
        text("""
            SELECT
                action,
                actor,
                repo,
                org,
                created_at,
                data
            FROM events
            WHERE action = ANY(:actions)
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
            ORDER BY created_at DESC
        """),
        {
            "actions": actions,
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
        },
    )

    violations: list[dict[str, Any]] = []
    for row in result.fetchall():
        action = row[0]
        actor = row[1]
        repo = row[2]
        org = row[3]
        created_at = row[4]
        data = row[5] if row[5] else {}

        meta = _VIOLATION_ACTIONS.get(action)
        if meta is None:
            continue

        # For git.push, only flag if force push
        if action == "git.push":
            is_force = data.get("force", False) if isinstance(data, dict) else False
            if not is_force:
                continue

        violations.append(
            {
                "type": meta["type"],
                "severity": meta["severity"],
                "description": meta["description"],
                "actor": actor,
                "repo": repo,
                "org": org,
                "timestamp": created_at.isoformat() if created_at else None,
                "action": action,
            }
        )

    # Previous period count for trend
    prev_result = await db.execute(
        text("""
            SELECT COUNT(*)
            FROM events
            WHERE action = ANY(:actions)
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :prev_end)
              AND created_at < NOW() - MAKE_INTERVAL(days => :lookback_days)
        """),
        {
            "actions": actions,
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "prev_end": lookback_days * 2,
        },
    )
    previous_count = prev_result.scalar() or 0

    current_count = len(violations)
    if previous_count > 0:
        trend_direction = "up" if current_count > previous_count else "down"
    else:
        trend_direction = "neutral"

    return {
        "violations": violations,
        "current_count": current_count,
        "previous_count": previous_count,
        "trend_direction": trend_direction,
    }


# ── Combined Summary ─────────────────────────────────────────────────────────


async def get_team_health_summary(
    db: AsyncSession,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Return combined summary for the MetricCards strip."""
    bus_factor_data = await get_bus_factor(db, scoped_orgs)
    engagement_data = await get_developer_engagement(db, scoped_orgs)
    violations_data = await get_policy_violations(db, scoped_orgs)
    concentration_data = await get_knowledge_concentration(db, scoped_orgs)

    # Compute overall bus factor score (1-5)
    if bus_factor_data:
        min_bf = min(r["bus_factor"] for r in bus_factor_data)
    else:
        min_bf = 5  # No repos = no risk

    # Knowledge concentration risk
    if not concentration_data:
        concentration_risk = "low"
    elif any(c["risk_level"] == "high" for c in concentration_data):
        concentration_risk = "high"
    elif any(c["risk_level"] == "medium" for c in concentration_data):
        concentration_risk = "medium"
    else:
        concentration_risk = "low"

    return {
        "bus_factor_score": min_bf,
        "active_contributors_pct": engagement_data["active_pct"],
        "total_developers": engagement_data["total_developers"],
        "dormant_developers": engagement_data["counts"]["dormant"],
        "policy_violations_count": violations_data["current_count"],
        "policy_violations_trend": violations_data["trend_direction"],
        "knowledge_concentration_risk": concentration_risk,
        "engagement_counts": engagement_data["counts"],
    }
