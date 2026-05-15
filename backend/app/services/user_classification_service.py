"""User behavior classification engine.

Classifies GitHub users into behavioral personas based on audit log activity
patterns within a configurable analysis window.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# ─── Persona constants ────────────────────────────────────────────────────────

PERSONA_POWER_USER = "Power User"
PERSONA_WEB_UI_ONLY = "Web UI Only"
PERSONA_IDE_ONLY = "IDE Only"
PERSONA_API_CLI_ONLY = "API/CLI Only"
PERSONA_COPILOT_ACTIVE = "Copilot Active"
PERSONA_TRULY_DORMANT = "Truly Dormant"
PERSONA_LIGHTLY_ACTIVE = "Lightly Active"
PERSONA_ADMIN_ONLY = "Admin Only"
PERSONA_CICD_BOT = "CI/CD Bot"

ALL_PERSONAS = [
    PERSONA_POWER_USER,
    PERSONA_WEB_UI_ONLY,
    PERSONA_IDE_ONLY,
    PERSONA_API_CLI_ONLY,
    PERSONA_COPILOT_ACTIVE,
    PERSONA_TRULY_DORMANT,
    PERSONA_LIGHTLY_ACTIVE,
    PERSONA_ADMIN_ONLY,
    PERSONA_CICD_BOT,
]

# ─── Surface classification helpers ──────────────────────────────────────────

WEB_ACTIONS = {
    "org.update_member",
    "repo.create",
    "repo.destroy",
    "repo.access",
    "team.add_member",
    "team.remove_member",
    "team.create",
    "team.destroy",
    "protected_branch.create",
    "protected_branch.destroy",
    "hook.create",
    "hook.destroy",
    "environment.create",
}
WEB_NAMESPACES = {
    "repo",
    "team",
    "hook",
    "protected_branch",
    "environment",
    "project",
    "pages",
    "discussion",
    "issue",
    "pull_request",
}

GIT_ACTIONS = {"git.clone", "git.push", "git.fetch"}

API_NAMESPACES = {"api"}

COPILOT_NAMESPACES = {"copilot"}

ADMIN_NAMESPACES = {
    "org",
    "enterprise",
    "business",
    "billing",
    "audit_log",
    "integration_installation",
    "oauth_application",
}

PASSIVE_ACTIONS = {"git.clone", "git.fetch", "repo.access"}

CICD_ACTOR_PATTERNS = ("[bot]", "github-actions", "dependabot")


def _classify_surface(action: str, namespace: str) -> str:
    """Map an event action/namespace to a surface category."""
    if namespace in COPILOT_NAMESPACES or action.startswith("copilot"):
        return "copilot"
    if action in GIT_ACTIONS:
        return "git"
    if namespace in API_NAMESPACES or action.startswith("api."):
        return "api"
    if namespace in WEB_NAMESPACES or action in WEB_ACTIONS:
        return "web"
    if namespace in ADMIN_NAMESPACES:
        return "admin"
    return "web"  # default fallback for unrecognized actions


def classify_single_user(
    *,
    event_count: int,
    surface_counts: dict[str, int],
    is_bot: bool,
    passive_count: int,
) -> tuple[str, float, list[str]]:
    """Classify a single user based on their activity metrics.

    Returns (persona, confidence_score, surfaces).
    """
    if event_count == 0:
        return PERSONA_TRULY_DORMANT, 1.0, []

    active_surfaces = [s for s, c in surface_counts.items() if c > 0]
    total = sum(surface_counts.values())

    # CI/CD Bot — machine-like patterns
    if is_bot or any(pattern in str(surface_counts) for pattern in CICD_ACTOR_PATTERNS):
        cicd_count = surface_counts.get("api", 0) + surface_counts.get("git", 0)
        if is_bot and cicd_count > 0:
            confidence = min(0.95, 0.7 + (cicd_count / max(total, 1)) * 0.25)
            return PERSONA_CICD_BOT, confidence, active_surfaces

    # Lightly Active — very low event count, mostly passive
    if event_count < 5 and passive_count == event_count:
        return PERSONA_LIGHTLY_ACTIVE, 0.9, active_surfaces
    if event_count < 5:
        return PERSONA_LIGHTLY_ACTIVE, 0.75, active_surfaces

    # Copilot Active — has copilot events
    copilot_count = surface_counts.get("copilot", 0)
    if copilot_count > 0:
        confidence = min(0.95, 0.7 + (copilot_count / max(total, 1)) * 0.25)
        return PERSONA_COPILOT_ACTIVE, confidence, active_surfaces

    # Admin Only — actions concentrated in admin namespaces
    admin_count = surface_counts.get("admin", 0)
    non_admin = total - admin_count
    if admin_count > 0 and non_admin == 0:
        return PERSONA_ADMIN_ONLY, 0.95, active_surfaces
    if admin_count > 0 and (admin_count / max(total, 1)) > 0.8:
        confidence = min(0.9, 0.6 + (admin_count / max(total, 1)) * 0.3)
        return PERSONA_ADMIN_ONLY, confidence, active_surfaces

    # Power User — active across 3+ surfaces with high volume
    non_admin_surfaces = [s for s in active_surfaces if s != "admin"]
    if len(non_admin_surfaces) >= 3 and event_count >= 20:
        confidence = min(0.95, 0.7 + (len(non_admin_surfaces) / 5) * 0.25)
        return PERSONA_POWER_USER, confidence, active_surfaces

    # Dominant surface classification
    if total > 0:
        dominant = max(surface_counts, key=lambda s: surface_counts.get(s, 0))
        dominant_ratio = surface_counts.get(dominant, 0) / total

        if dominant == "web" and dominant_ratio >= 0.6:
            return PERSONA_WEB_UI_ONLY, min(0.95, 0.5 + dominant_ratio * 0.4), active_surfaces
        if dominant == "git" and dominant_ratio >= 0.6:
            return PERSONA_IDE_ONLY, min(0.95, 0.5 + dominant_ratio * 0.4), active_surfaces
        if dominant == "api" and dominant_ratio >= 0.6:
            return PERSONA_API_CLI_ONLY, min(0.95, 0.5 + dominant_ratio * 0.4), active_surfaces

    # Power User fallback for multi-surface users
    if len(non_admin_surfaces) >= 2 and event_count >= 10:
        return PERSONA_POWER_USER, 0.6, active_surfaces

    # Default to dominant surface or web
    return PERSONA_WEB_UI_ONLY, 0.5, active_surfaces


async def classify_users(
    db: AsyncSession,
    org: str,
    window_days: int = 90,
) -> int:
    """Classify all users in an org by their audit log activity.

    Returns the number of users classified.
    """
    now = datetime.now(UTC)
    classified_count = 0

    # Get all members of the org (actors with events + members with zero events)
    result = await db.execute(
        text("""
            SELECT
                actor,
                COUNT(*) AS event_count,
                BOOL_OR(actor_is_bot) AS is_bot,
                COALESCE(
                    jsonb_object_agg(
                        COALESCE(namespace, 'unknown'),
                        cnt
                    ) FILTER (WHERE namespace IS NOT NULL),
                    '{}'::jsonb
                ) AS namespace_counts,
                COALESCE(
                    jsonb_object_agg(
                        COALESCE(action, 'unknown'),
                        action_cnt
                    ) FILTER (WHERE action IS NOT NULL),
                    '{}'::jsonb
                ) AS action_counts,
                COUNT(*) FILTER (
                    WHERE action IN ('git.clone', 'git.fetch', 'repo.access')
                ) AS passive_count
            FROM (
                SELECT
                    actor,
                    actor_is_bot,
                    namespace,
                    action,
                    COUNT(*) OVER (PARTITION BY actor, namespace) AS cnt,
                    COUNT(*) OVER (PARTITION BY actor, action) AS action_cnt
                FROM events
                WHERE org = :org
                  AND created_at >= NOW() - MAKE_INTERVAL(days => :window_days)
                  AND actor IS NOT NULL
                  AND actor != ''
            ) sub
            GROUP BY actor
        """),
        {"org": org, "window_days": window_days},
    )

    rows = result.fetchall()

    for row in rows:
        actor = row[0]
        event_count = int(row[1])
        is_bot = bool(row[2])
        namespace_counts: dict[str, int] = row[3] if isinstance(row[3], dict) else {}
        action_counts: dict[str, int] = row[4] if isinstance(row[4], dict) else {}
        passive_count = int(row[5])

        # Build surface counts from namespace and action data
        surface_counts: dict[str, int] = {}
        for ns, count in namespace_counts.items():
            surface = _classify_surface(ns, ns)
            surface_counts[surface] = surface_counts.get(surface, 0) + int(count)

        # Override with specific action-based classification
        for action, count in action_counts.items():
            ns = action.split(".")[0] if "." in action else action
            surface = _classify_surface(action, ns)
            # Don't double-count; use action-level for specific git/api actions
            if action in GIT_ACTIONS or ns in API_NAMESPACES or ns in COPILOT_NAMESPACES:
                surface_counts[surface] = max(surface_counts.get(surface, 0), int(count))

        persona, confidence, surfaces = classify_single_user(
            event_count=event_count,
            surface_counts=surface_counts,
            is_bot=is_bot,
            passive_count=passive_count,
        )

        # Upsert classification
        await db.execute(
            text("""
                INSERT INTO user_classifications
                    (user_login, org, persona, confidence_score, event_count,
                     surfaces, analysis_window_days, classified_at, updated_at)
                VALUES
                    (:user_login, :org, :persona, :confidence_score, :event_count,
                     :surfaces, :window_days, :classified_at, :classified_at)
                ON CONFLICT (user_login, org)
                    WHERE user_login = :user_login AND org = :org
                DO UPDATE SET
                    persona = EXCLUDED.persona,
                    confidence_score = EXCLUDED.confidence_score,
                    event_count = EXCLUDED.event_count,
                    surfaces = EXCLUDED.surfaces,
                    analysis_window_days = EXCLUDED.analysis_window_days,
                    classified_at = EXCLUDED.classified_at,
                    updated_at = EXCLUDED.classified_at
            """),
            {
                "user_login": actor,
                "org": org,
                "persona": persona,
                "confidence_score": confidence,
                "event_count": event_count,
                "surfaces": surfaces,
                "window_days": window_days,
                "classified_at": now,
            },
        )
        classified_count += 1

    logger.info(
        "user_classification.classify_complete",
        org=org,
        classified_count=classified_count,
        window_days=window_days,
    )
    return classified_count


async def get_classification_summary(
    db: AsyncSession,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Return aggregate persona breakdown for the given orgs."""
    result = await db.execute(
        text("""
            SELECT
                persona,
                COUNT(*) AS user_count,
                AVG(confidence_score) AS avg_confidence,
                SUM(event_count) AS total_events
            FROM user_classifications
            WHERE org = ANY(:orgs)
            GROUP BY persona
            ORDER BY user_count DESC
        """),
        {"orgs": scoped_orgs},
    )

    personas: list[dict[str, Any]] = []
    total_users = 0
    dormant_count = 0
    power_user_count = 0

    for row in result.fetchall():
        count = int(row[1])
        total_users += count
        if row[0] == PERSONA_TRULY_DORMANT:
            dormant_count = count
        if row[0] == PERSONA_POWER_USER:
            power_user_count = count
        personas.append(
            {
                "persona": row[0],
                "user_count": count,
                "avg_confidence": round(float(row[2]), 3),
                "total_events": int(row[3]),
            }
        )

    return {
        "personas": personas,
        "total_users": total_users,
        "dormant_count": dormant_count,
        "dormant_pct": round(dormant_count / max(total_users, 1) * 100, 1),
        "power_user_count": power_user_count,
        "power_user_pct": round(power_user_count / max(total_users, 1) * 100, 1),
    }


async def get_user_classifications(
    db: AsyncSession,
    scoped_orgs: list[str],
    persona: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Return paginated user classifications with optional persona filter."""
    offset = (page - 1) * page_size

    # Build count query
    count_params: dict[str, Any] = {"orgs": scoped_orgs}
    count_sql = """
        SELECT COUNT(*) FROM user_classifications
        WHERE org = ANY(:orgs)
    """
    if persona:
        count_sql += " AND persona = :persona"
        count_params["persona"] = persona

    count_result = await db.execute(text(count_sql), count_params)
    total = count_result.scalar() or 0

    # Build data query
    data_params: dict[str, Any] = {
        "orgs": scoped_orgs,
        "limit": page_size,
        "offset": offset,
    }
    data_sql = """
        SELECT id, user_login, org, persona, confidence_score,
               event_count, surfaces, analysis_window_days, classified_at
        FROM user_classifications
        WHERE org = ANY(:orgs)
    """
    if persona:
        data_sql += " AND persona = :persona"
        data_params["persona"] = persona
    data_sql += " ORDER BY event_count DESC, user_login ASC LIMIT :limit OFFSET :offset"

    data_result = await db.execute(text(data_sql), data_params)
    users = [
        {
            "id": row[0],
            "user_login": row[1],
            "org": row[2],
            "persona": row[3],
            "confidence_score": round(float(row[4]), 3),
            "event_count": int(row[5]),
            "surfaces": row[6] if isinstance(row[6], list) else [],
            "analysis_window_days": int(row[7]),
            "classified_at": row[8].isoformat() if row[8] else None,
        }
        for row in data_result.fetchall()
    ]

    return {
        "users": users,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }
