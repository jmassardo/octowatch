"""User behavior security analytics service.

Analyzes audit log events for security-focused behavioral signals:
- Risk scoring based on behavioral anomalies
- Anomaly detection (deviation from personal baseline)
- Risky action identification (permission escalation, unusual access patterns)
- Insider threat signals and compromised account indicators
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# ─── Risk signal definitions ─────────────────────────────────────────────────

# Actions that contribute to elevated risk scores
RISKY_ACTIONS: dict[str, dict[str, Any]] = {
    # Permission escalation
    "org.update_member": {"weight": 3, "category": "permission_change", "label": "Org role change"},
    "team.add_member": {"weight": 2, "category": "permission_change", "label": "Team addition"},
    "team.change_privacy": {
        "weight": 3,
        "category": "permission_change",
        "label": "Team visibility change",
    },
    "org.invite_member": {
        "weight": 2,
        "category": "permission_change",
        "label": "Org member invite",
    },
    # Security feature changes
    "protected_branch.destroy": {
        "weight": 5,
        "category": "security_bypass",
        "label": "Branch protection removed",
    },
    "protected_branch.policy_override": {
        "weight": 4,
        "category": "security_bypass",
        "label": "Branch protection override",
    },
    "repo.update_default_branch": {
        "weight": 2,
        "category": "security_bypass",
        "label": "Default branch changed",
    },
    # Token/secret management
    "personal_access_token.create": {
        "weight": 3,
        "category": "credential_activity",
        "label": "PAT created",
    },
    "oauth_application.create": {
        "weight": 4,
        "category": "credential_activity",
        "label": "OAuth app created",
    },
    "integration_installation.create": {
        "weight": 3,
        "category": "credential_activity",
        "label": "App installed",
    },
    # Repository access patterns
    "repo.create": {"weight": 1, "category": "repo_activity", "label": "Repo created"},
    "repo.destroy": {"weight": 4, "category": "repo_activity", "label": "Repo deleted"},
    "git.clone": {"weight": 1, "category": "repo_activity", "label": "Repo cloned"},
    "repo.transfer": {"weight": 4, "category": "repo_activity", "label": "Repo transferred"},
    "private_repository_forking.enable": {
        "weight": 3,
        "category": "repo_activity",
        "label": "Private forking enabled",
    },
    # Admin actions
    "org.remove_member": {
        "weight": 2,
        "category": "admin_action",
        "label": "Member removed from org",
    },
    "org.disable_two_factor_requirement": {
        "weight": 5,
        "category": "security_bypass",
        "label": "2FA requirement disabled",
    },
    "org.disable_saml": {
        "weight": 5,
        "category": "security_bypass",
        "label": "SAML SSO disabled",
    },
    "hook.create": {"weight": 2, "category": "integration_change", "label": "Webhook created"},
    "hook.config_changed": {
        "weight": 3,
        "category": "integration_change",
        "label": "Webhook config changed",
    },
}

RISK_CATEGORIES = {
    "permission_change": {
        "label": "Permission Changes",
        "description": "Role escalations, team membership changes, access grants",
    },
    "security_bypass": {
        "label": "Security Bypasses",
        "description": "Disabling protections, removing branch rules, bypassing 2FA",
    },
    "credential_activity": {
        "label": "Credential Activity",
        "description": "Token creation spikes, OAuth app registrations, key management",
    },
    "repo_activity": {
        "label": "Unusual Repo Activity",
        "description": "Mass cloning, repo transfers, deletions, forking private repos",
    },
    "admin_action": {
        "label": "Administrative Actions",
        "description": "Member removals, org setting changes, policy modifications",
    },
    "integration_change": {
        "label": "Integration Changes",
        "description": "Webhook additions, app installations, external connections",
    },
}

# ─── Risk level thresholds ───────────────────────────────────────────────────

RISK_THRESHOLD_HIGH = 15
RISK_THRESHOLD_MEDIUM = 7
RISK_THRESHOLD_LOW = 3


def _risk_level(score: int) -> str:
    """Map a numeric risk score to a severity level."""
    if score >= RISK_THRESHOLD_HIGH:
        return "high"
    if score >= RISK_THRESHOLD_MEDIUM:
        return "medium"
    if score >= RISK_THRESHOLD_LOW:
        return "low"
    return "none"


# ─── Service functions ───────────────────────────────────────────────────────


async def get_risk_summary(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int = 30,
) -> dict[str, Any]:
    """Return aggregate risk metrics across all users in scope.

    Computes:
    - Total users with risk signals
    - High/medium/low risk user counts
    - Top risk categories
    - Anomaly count (users with activity significantly above baseline)
    """
    if not scoped_orgs:
        return _empty_risk_summary()

    # Get risk signal counts per user
    result = await db.execute(
        text("""
            SELECT
                actor,
                action,
                COUNT(*) AS action_count
            FROM events
            WHERE org = ANY(:orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
              AND actor IS NOT NULL
              AND actor != ''
              AND action = ANY(:risky_actions)
            GROUP BY actor, action
            ORDER BY action_count DESC
        """),
        {
            "orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "risky_actions": list(RISKY_ACTIONS.keys()),
        },
    )

    user_scores: dict[str, int] = {}
    category_counts: dict[str, int] = {}

    for row in result.fetchall():
        actor = str(row[0])
        action = str(row[1])
        count = int(row[2])
        action_meta = RISKY_ACTIONS.get(action)
        if not action_meta:
            continue

        weight = action_meta["weight"] * count
        user_scores[actor] = user_scores.get(actor, 0) + weight

        category = action_meta["category"]
        category_counts[category] = category_counts.get(category, 0) + count

    # Compute anomaly count (users with 2x+ activity vs their 90-day baseline)
    anomaly_result = await db.execute(
        text("""
            WITH recent AS (
                SELECT actor, COUNT(*) AS recent_count
                FROM events
                WHERE org = ANY(:orgs)
                  AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                  AND actor IS NOT NULL AND actor != ''
                GROUP BY actor
            ),
            baseline AS (
                SELECT actor, COUNT(*) / GREATEST(3, :baseline_factor) AS avg_count
                FROM events
                WHERE org = ANY(:orgs)
                  AND created_at >= NOW() - MAKE_INTERVAL(days => 90)
                  AND created_at < NOW() - MAKE_INTERVAL(days => :lookback_days)
                  AND actor IS NOT NULL AND actor != ''
                GROUP BY actor
            )
            SELECT COUNT(*) FROM recent r
            JOIN baseline b ON r.actor = b.actor
            WHERE r.recent_count > b.avg_count * 2
              AND r.recent_count > 20
        """),
        {
            "orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "baseline_factor": max(1, (90 - lookback_days) // lookback_days),
        },
    )
    anomaly_count = anomaly_result.scalar() or 0

    # Compute risk tier counts
    high_risk = sum(1 for s in user_scores.values() if s >= RISK_THRESHOLD_HIGH)
    medium_risk = sum(
        1 for s in user_scores.values() if RISK_THRESHOLD_MEDIUM <= s < RISK_THRESHOLD_HIGH
    )
    low_risk = sum(
        1 for s in user_scores.values() if RISK_THRESHOLD_LOW <= s < RISK_THRESHOLD_MEDIUM
    )

    # Top categories
    top_categories = [
        {
            "category": cat,
            "label": RISK_CATEGORIES.get(cat, {}).get("label", cat),
            "description": RISK_CATEGORIES.get(cat, {}).get("description", ""),
            "event_count": count,
        }
        for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "total_users_with_signals": len(user_scores),
        "high_risk_count": high_risk,
        "medium_risk_count": medium_risk,
        "low_risk_count": low_risk,
        "anomaly_count": int(anomaly_count),
        "top_categories": top_categories,
        "lookback_days": lookback_days,
    }


def _empty_risk_summary() -> dict[str, Any]:
    """Return an empty risk summary when no orgs are in scope."""
    return {
        "total_users_with_signals": 0,
        "high_risk_count": 0,
        "medium_risk_count": 0,
        "low_risk_count": 0,
        "anomaly_count": 0,
        "top_categories": [],
        "lookback_days": 30,
    }


async def get_risky_users(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int = 30,
    risk_level: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Return paginated list of users with risk scores and signal breakdown.

    Each user includes:
    - Risk score and level
    - Signal breakdown by category
    - Most recent risky actions
    - Activity anomaly indicator
    """
    if not scoped_orgs:
        return {"users": [], "total": 0, "page": page, "page_size": page_size}

    # Get all risky actions per user
    result = await db.execute(
        text("""
            SELECT
                actor,
                action,
                COUNT(*) AS action_count,
                MAX(created_at) AS last_seen,
                array_agg(DISTINCT org) AS orgs
            FROM events
            WHERE org = ANY(:orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
              AND actor IS NOT NULL
              AND actor != ''
              AND action = ANY(:risky_actions)
            GROUP BY actor, action
            ORDER BY actor, action_count DESC
        """),
        {
            "orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "risky_actions": list(RISKY_ACTIONS.keys()),
        },
    )

    # Build per-user risk profiles
    user_profiles: dict[str, dict[str, Any]] = {}

    for row in result.fetchall():
        actor = str(row[0])
        action = str(row[1])
        count = int(row[2])
        last_seen = row[3]
        orgs = row[4] if row[4] else []

        if actor not in user_profiles:
            user_profiles[actor] = {
                "user_login": actor,
                "risk_score": 0,
                "signals": [],
                "categories": {},
                "orgs": set(),
                "last_risky_action_at": None,
            }

        profile = user_profiles[actor]
        action_meta = RISKY_ACTIONS.get(action)
        if not action_meta:
            continue

        weight = action_meta["weight"] * count
        profile["risk_score"] += weight
        profile["signals"].append(
            {
                "action": action,
                "label": action_meta["label"],
                "category": action_meta["category"],
                "count": count,
                "weight": weight,
                "last_seen": last_seen.isoformat() if last_seen else None,
            }
        )

        category = action_meta["category"]
        profile["categories"][category] = profile["categories"].get(category, 0) + count
        profile["orgs"].update(orgs)

        if last_seen and (
            profile["last_risky_action_at"] is None or last_seen > profile["last_risky_action_at"]
        ):
            profile["last_risky_action_at"] = last_seen

    # Convert to sorted list
    users_list = []
    for profile in user_profiles.values():
        score = profile["risk_score"]
        level = _risk_level(score)

        # Apply risk level filter if provided
        if risk_level and level != risk_level:
            continue

        users_list.append(
            {
                "user_login": profile["user_login"],
                "risk_score": score,
                "risk_level": level,
                "signals": sorted(profile["signals"], key=lambda s: s["weight"], reverse=True)[:10],
                "category_breakdown": [
                    {
                        "category": cat,
                        "label": RISK_CATEGORIES.get(cat, {}).get("label", cat),
                        "count": cnt,
                    }
                    for cat, cnt in sorted(
                        profile["categories"].items(), key=lambda x: x[1], reverse=True
                    )
                ],
                "orgs": sorted(profile["orgs"]),
                "last_risky_action_at": (
                    profile["last_risky_action_at"].isoformat()
                    if profile["last_risky_action_at"]
                    else None
                ),
            }
        )

    # Sort by risk score descending
    users_list.sort(key=lambda u: u["risk_score"], reverse=True)

    total = len(users_list)
    offset = (page - 1) * page_size
    paginated = users_list[offset : offset + page_size]

    return {"users": paginated, "total": total, "page": page, "page_size": page_size}


async def get_anomalous_users(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int = 30,
    threshold_multiplier: float = 2.0,
) -> dict[str, Any]:
    """Detect users whose recent activity deviates significantly from baseline.

    Compares activity in the lookback window to the 90-day average prior.
    Returns users whose recent activity is threshold_multiplier times their baseline.
    """
    if not scoped_orgs:
        return {"anomalies": [], "lookback_days": lookback_days}

    result = await db.execute(
        text("""
            WITH recent AS (
                SELECT
                    actor,
                    COUNT(*) AS recent_count,
                    COUNT(DISTINCT action) AS recent_action_types,
                    COUNT(DISTINCT COALESCE(source_ip::text, '')) AS recent_ips
                FROM events
                WHERE org = ANY(:orgs)
                  AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                  AND actor IS NOT NULL AND actor != ''
                GROUP BY actor
            ),
            baseline AS (
                SELECT
                    actor,
                    COUNT(*) AS baseline_total,
                    COUNT(*) / GREATEST(1, (90 - :lookback_days)) AS daily_baseline,
                    COUNT(DISTINCT action) AS baseline_action_types,
                    COUNT(DISTINCT COALESCE(source_ip::text, '')) AS baseline_ips
                FROM events
                WHERE org = ANY(:orgs)
                  AND created_at >= NOW() - MAKE_INTERVAL(days => 90)
                  AND created_at < NOW() - MAKE_INTERVAL(days => :lookback_days)
                  AND actor IS NOT NULL AND actor != ''
                GROUP BY actor
            )
            SELECT
                r.actor,
                r.recent_count,
                r.recent_action_types,
                r.recent_ips,
                b.baseline_total,
                b.daily_baseline,
                b.baseline_action_types,
                b.baseline_ips,
                ROUND(r.recent_count::numeric / GREATEST(1, b.daily_baseline * :lookback_days), 2)
                    AS activity_ratio
            FROM recent r
            JOIN baseline b ON r.actor = b.actor
            WHERE r.recent_count > b.daily_baseline * :lookback_days * :threshold
              AND r.recent_count > 20
            ORDER BY activity_ratio DESC
            LIMIT 100
        """),
        {
            "orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "threshold": threshold_multiplier,
        },
    )

    anomalies = []
    for row in result.fetchall():
        actor = str(row[0])
        recent_count = int(row[1])
        recent_action_types = int(row[2])
        recent_ips = int(row[3])
        # row[4] is baseline_total (not needed for output)
        daily_baseline = int(row[5])
        baseline_action_types = int(row[6])
        baseline_ips = int(row[7])
        activity_ratio = float(row[8])

        deviation_reasons = []
        if activity_ratio > threshold_multiplier:
            deviation_reasons.append(f"Activity volume {activity_ratio:.1f}x above baseline")
        if recent_action_types > baseline_action_types * 1.5:
            deviation_reasons.append("Performing unusual action types")
        if recent_ips > baseline_ips * 2 and recent_ips > 3:
            deviation_reasons.append(f"Accessing from {recent_ips} IPs (baseline: {baseline_ips})")

        anomalies.append(
            {
                "user_login": actor,
                "recent_event_count": recent_count,
                "baseline_daily_avg": daily_baseline,
                "activity_ratio": activity_ratio,
                "recent_action_types": recent_action_types,
                "baseline_action_types": baseline_action_types,
                "recent_ips": recent_ips,
                "baseline_ips": baseline_ips,
                "deviation_reasons": deviation_reasons,
            }
        )

    return {"anomalies": anomalies, "lookback_days": lookback_days}


async def get_permission_drift(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int = 90,
) -> dict[str, Any]:
    """Identify users with excessive permissions relative to their actual activity.

    Compares users who have admin/elevated actions in their history against
    their actual recent development activity to detect permission bloat.
    """
    if not scoped_orgs:
        return {"users": [], "lookback_days": lookback_days}

    # Find users who have admin permissions but low actual dev activity
    result = await db.execute(
        text("""
            WITH admin_actors AS (
                SELECT DISTINCT actor
                FROM events
                WHERE org = ANY(:orgs)
                  AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                  AND actor IS NOT NULL AND actor != ''
                  AND (
                      namespace IN ('org', 'enterprise', 'billing', 'audit_log')
                      OR action IN (
                          'org.update_member', 'team.add_member', 'team.remove_member',
                          'protected_branch.create', 'protected_branch.destroy'
                      )
                  )
            ),
            activity_summary AS (
                SELECT
                    e.actor,
                    COUNT(*) AS total_events,
                    COUNT(*) FILTER (
                        WHERE namespace IN ('org', 'enterprise', 'billing', 'audit_log')
                    ) AS admin_events,
                    COUNT(*) FILTER (
                        WHERE action IN ('git.push', 'git.clone', 'git.fetch')
                           OR namespace IN ('pull_request', 'issue')
                    ) AS dev_events,
                    MAX(created_at) AS last_active
                FROM events e
                WHERE e.org = ANY(:orgs)
                  AND e.created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                  AND e.actor IN (SELECT actor FROM admin_actors)
                GROUP BY e.actor
            )
            SELECT
                actor,
                total_events,
                admin_events,
                dev_events,
                last_active,
                ROUND(admin_events::numeric / GREATEST(1, total_events) * 100, 1) AS admin_pct
            FROM activity_summary
            WHERE admin_events > 0
            ORDER BY admin_pct DESC, total_events ASC
            LIMIT 50
        """),
        {"orgs": scoped_orgs, "lookback_days": lookback_days},
    )

    users = []
    for row in result.fetchall():
        actor = str(row[0])
        total_events = int(row[1])
        admin_events = int(row[2])
        dev_events = int(row[3])
        last_active = row[4]
        admin_pct = float(row[5])

        # Flag users with high admin %, low dev activity
        if admin_pct > 50 and dev_events < 5:
            status = "review_recommended"
            reason = "High admin activity with minimal development — may have excessive permissions"
        elif total_events < 10 and admin_events > 0:
            status = "low_activity"
            reason = "Low overall activity despite having admin access"
        else:
            status = "normal"
            reason = "Permission usage appears proportional to activity"

        users.append(
            {
                "user_login": actor,
                "total_events": total_events,
                "admin_events": admin_events,
                "dev_events": dev_events,
                "admin_pct": admin_pct,
                "last_active": last_active.isoformat() if last_active else None,
                "status": status,
                "reason": reason,
            }
        )

    return {"users": users, "lookback_days": lookback_days}
