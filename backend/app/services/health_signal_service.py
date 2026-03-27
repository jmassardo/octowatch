"""Health signal service: SQL queries for Org Health tab signals.

All queries enforce RBAC via scoped_orgs parameter.
Reference: docs/detection-health-signal-spec.md §4.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def get_health_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Aggregate counts across all health signal types."""
    result = await session.execute(
        text("""
            WITH stale AS (
                SELECT org, repo, MAX(created_at) AS last_event_at
                FROM events
                WHERE org = ANY(:scoped_orgs) AND repo IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '2 years'
                GROUP BY org, repo
                HAVING MAX(created_at) <= NOW() - INTERVAL '90 days'
            ),
            pat_summary AS (
                SELECT
                    COUNT(*) FILTER (WHERE data->>'token_expiry_date' IS NULL
                                        OR data->>'token_expiry_date' = '') AS no_expiry,
                    COUNT(*) FILTER (WHERE created_at <= NOW() - INTERVAL '90 days'
                                       AND (data->>'token_expiry_date' IS NULL
                                         OR data->>'token_expiry_date' = '')) AS stale_90d
                FROM events
                WHERE action = 'personal_access_token.create'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '365 days'
            ),
            bypass_summary AS (
                SELECT COUNT(DISTINCT actor) AS offender_count
                FROM events
                WHERE action = ANY(ARRAY[
                    'secret_scanning.push_protection.bypass',
                    'protected_branch.policy_override',
                    'branch_protection_rule.policy_override'
                ])
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
                  AND actor IS NOT NULL
            ),
            ext_collab AS (
                SELECT
                    COUNT(*) AS total_active,
                    COUNT(*) FILTER (WHERE role IN ('admin', 'maintain')) AS elevated
                FROM external_collaborators
                WHERE org = ANY(:scoped_orgs) AND is_active = TRUE
            )
            SELECT
                (SELECT COUNT(*) FROM stale) AS stale_repos,
                ps.no_expiry AS pat_no_expiry,
                ps.stale_90d AS pat_stale,
                bs.offender_count AS bypass_offenders,
                ec.total_active AS ext_collab_total,
                ec.elevated AS ext_collab_elevated
            FROM pat_summary ps, bypass_summary bs, ext_collab ec
        """),
        {"scoped_orgs": scoped_orgs},
    )
    row = result.mappings().first()
    if not row:
        return {
            "stale_repos": 0,
            "pat_no_expiry": 0,
            "pat_stale": 0,
            "bypass_offenders": 0,
            "ext_collab_total": 0,
            "ext_collab_elevated": 0,
        }
    return dict(row)


async def get_pat_health_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, int]:
    """PAT health counts: no_expiry, expired, stale_90d."""
    result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE data->>'token_expiry_date' IS NULL
                                    OR data->>'token_expiry_date' = '') AS no_expiry_count,
                COUNT(*) FILTER (WHERE (data->>'token_expired')::BOOLEAN = TRUE) AS expired_count,
                COUNT(*) FILTER (WHERE created_at <= NOW() - INTERVAL '90 days'
                                   AND (data->>'token_expiry_date' IS NULL
                                     OR data->>'token_expiry_date' = '')) AS stale_90d_count
            FROM events
            WHERE action = 'personal_access_token.create'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '365 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    row = result.mappings().first()
    if not row:
        return {"no_expiry_count": 0, "expired_count": 0, "stale_90d_count": 0}
    return dict(row)


async def get_pat_token_age_signals(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """PATs with no expiry, expired, and stale >90d (US-1C)."""
    result = await session.execute(
        text("""
            SELECT
                actor AS github_login,
                data->>'token_name' AS token_name,
                data->>'token_id' AS token_id,
                data->>'token_type' AS token_type,
                created_at,
                EXTRACT(DAY FROM NOW() - created_at)::INT AS age_days,
                CASE
                    WHEN (data->>'token_expired')::BOOLEAN = TRUE THEN 'expired'
                    WHEN created_at <= NOW() - INTERVAL '90 days'
                         AND (data->>'token_expiry_date' IS NULL OR data->>'token_expiry_date' = '')
                        THEN 'stale_90d'
                    WHEN data->>'token_expiry_date' IS NULL OR data->>'token_expiry_date' = ''
                        THEN 'no_expiry'
                    ELSE 'ok'
                END AS signal_type
            FROM events
            WHERE action = 'personal_access_token.create'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '365 days'
              AND (
                  data->>'token_expiry_date' IS NULL
                  OR data->>'token_expiry_date' = ''
                  OR (data->>'token_expired')::BOOLEAN = TRUE
                  OR created_at <= NOW() - INTERVAL '90 days'
              )
            ORDER BY created_at ASC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_dormant_tokens(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """PATs created >30d ago with no usage events (US-1D)."""
    result = await session.execute(
        text("""
            SELECT
                create_evt.actor AS github_login,
                create_evt.data->>'token_id' AS token_id,
                create_evt.data->>'token_name' AS token_name,
                create_evt.data->>'token_type' AS token_type,
                create_evt.created_at,
                EXTRACT(DAY FROM NOW() - create_evt.created_at)::INT AS age_days,
                MAX(use_evt.created_at) AS last_used_at
            FROM events AS create_evt
            LEFT JOIN events AS use_evt
                ON use_evt.action = 'personal_access_token.access'
                AND use_evt.org = ANY(:scoped_orgs)
                AND use_evt.data->>'token_id' = create_evt.data->>'token_id'
                AND use_evt.created_at BETWEEN create_evt.created_at
                                            AND create_evt.created_at + INTERVAL '30 days'
            WHERE create_evt.action = 'personal_access_token.create'
              AND create_evt.org = ANY(:scoped_orgs)
              AND create_evt.created_at <= NOW() - INTERVAL '30 days'
              AND create_evt.created_at >= NOW() - INTERVAL '180 days'
            GROUP BY
                create_evt.actor,
                create_evt.data->>'token_id',
                create_evt.data->>'token_name',
                create_evt.data->>'token_type',
                create_evt.created_at
            HAVING MAX(use_evt.created_at) IS NULL
            ORDER BY create_evt.created_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_bypass_offenders(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    lookback_days: int = 90,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Top actors by bypass count (US-2C)."""
    result = await session.execute(
        text("""
            SELECT
                actor,
                COUNT(*) AS total_bypasses,
                COUNT(*) FILTER (WHERE action = 'secret_scanning.push_protection.bypass')
                    AS push_protection_bypasses,
                COUNT(*) FILTER (WHERE action IN (
                    'protected_branch.policy_override',
                    'branch_protection_rule.policy_override'
                )) AS branch_protection_overrides,
                MIN(created_at) AS first_bypass_at,
                MAX(created_at) AS last_bypass_at,
                COUNT(DISTINCT DATE_TRUNC('day', created_at)) AS active_days
            FROM events
            WHERE action = ANY(ARRAY[
                'secret_scanning.push_protection.bypass',
                'protected_branch.policy_override',
                'branch_protection_rule.policy_override'
            ])
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - make_interval(days => :lookback_days)
              AND actor IS NOT NULL
              AND actor_is_bot = FALSE
            GROUP BY actor
            HAVING COUNT(*) >= 1
            ORDER BY total_bypasses DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_stale_repositories(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    stale_threshold_days: int = 90,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Repos with no event activity beyond threshold (US-3A)."""
    result = await session.execute(
        text("""
            WITH repo_last_activity AS (
                SELECT org, repo, MAX(created_at) AS last_event_at
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '2 years'
                GROUP BY org, repo
            )
            SELECT
                org, repo, last_event_at,
                EXTRACT(DAY FROM NOW() - last_event_at)::INT AS days_since_activity
            FROM repo_last_activity
            WHERE last_event_at <= NOW() - make_interval(days => :threshold_days)
            ORDER BY last_event_at ASC
            LIMIT :limit
        """),
        {
            "scoped_orgs": scoped_orgs,
            "threshold_days": stale_threshold_days,
            "limit": limit,
        },
    )
    return [dict(row) for row in result.mappings().all()]


async def get_archived_repositories(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Archived repos still present — never deleted (US-3B)."""
    result = await session.execute(
        text("""
            WITH archived AS (
                SELECT DISTINCT ON (org, repo)
                    org, repo, created_at AS archived_at, actor AS archived_by
                FROM events
                WHERE action = 'repo.archived'
                  AND org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
                ORDER BY org, repo, created_at DESC
            ),
            deleted AS (
                SELECT DISTINCT org, repo
                FROM events
                WHERE action IN ('repo.destroy', 'repo.delete')
                  AND org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
            )
            SELECT
                a.org, a.repo, a.archived_at, a.archived_by,
                EXTRACT(DAY FROM NOW() - a.archived_at)::INT AS days_since_archived
            FROM archived a
            LEFT JOIN deleted d ON d.org = a.org AND d.repo = a.repo
            WHERE d.repo IS NULL
            ORDER BY a.archived_at ASC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_abandoned_forks(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Forks with no push within 30d of fork (US-3C)."""
    result = await session.execute(
        text("""
            WITH forks AS (
                SELECT actor, org, repo, created_at AS forked_at
                FROM events
                WHERE action = 'repo.fork'
                  AND org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
                  AND created_at BETWEEN NOW() - INTERVAL '180 days'
                                      AND NOW() - INTERVAL '30 days'
            ),
            fork_pushes AS (
                SELECT DISTINCT repo
                FROM events
                WHERE action IN ('git.push', 'push')
                  AND org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '180 days'
            )
            SELECT
                f.actor, f.org, f.repo, f.forked_at,
                EXTRACT(DAY FROM NOW() - f.forked_at)::INT AS days_since_fork
            FROM forks f
            LEFT JOIN fork_pushes p ON p.repo = f.repo
            WHERE p.repo IS NULL
            ORDER BY f.forked_at ASC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_external_collaborators(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Active outside collaborators with IdP enrichment (US-5B)."""
    result = await session.execute(
        text("""
            SELECT
                ec.github_login,
                ec.org,
                ec.repo,
                ec.role,
                ec.granted_at,
                ec.granted_by,
                ec.last_event_at,
                CASE
                    WHEN ec.last_event_at IS NULL THEN NULL
                    ELSE EXTRACT(DAY FROM NOW() - ec.last_event_at)::INT
                END AS days_since_last_event,
                ia.email                    AS idp_email,
                ia.employment_status        AS idp_employment_status
            FROM external_collaborators ec
            LEFT JOIN idp_actor_enrichments ia
                ON ia.github_login = ec.github_login
            WHERE ec.org       = ANY(:scoped_orgs)
              AND ec.is_active  = TRUE
            ORDER BY ec.granted_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_external_collaborator_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, int]:
    """Summary counts for external collaborators."""
    result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_active,
                COUNT(*) FILTER (WHERE repo IS NULL) AS org_level_count,
                COUNT(*) FILTER (WHERE role IN ('admin', 'maintain')) AS elevated_count,
                COUNT(*) FILTER (
                    WHERE last_event_at IS NULL
                       OR last_event_at < NOW() - INTERVAL '60 days'
                ) AS dormant_count
            FROM external_collaborators
            WHERE org = ANY(:scoped_orgs) AND is_active = TRUE
        """),
        {"scoped_orgs": scoped_orgs},
    )
    row = result.mappings().first()
    if not row:
        return {"total_active": 0, "org_level_count": 0, "elevated_count": 0, "dormant_count": 0}
    return dict(row)


async def get_dormant_collaborators(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    dormancy_days: int = 60,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Collaborators inactive for X+ days (US-5C)."""
    result = await session.execute(
        text("""
            SELECT
                github_login, org, repo, role,
                granted_at, last_event_at,
                CASE
                    WHEN last_event_at IS NULL
                        THEN EXTRACT(DAY FROM NOW() - granted_at)::INT
                    ELSE EXTRACT(DAY FROM NOW() - last_event_at)::INT
                END AS days_inactive
            FROM external_collaborators
            WHERE org = ANY(:scoped_orgs)
              AND is_active = TRUE
              AND (
                  last_event_at IS NULL
                  OR last_event_at < NOW() - make_interval(days => :dormancy_days)
              )
            ORDER BY days_inactive DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "dormancy_days": dormancy_days, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]
