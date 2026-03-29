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
                WHERE org = ANY(:scoped_orgs) AND status = 'active'
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
                ec.login        AS github_login,
                ec.org,
                ec.repo,
                ec.role,
                ec.added_at     AS granted_at,
                ec.added_by     AS granted_by,
                ec.last_event_at,
                CASE
                    WHEN ec.last_event_at IS NULL THEN NULL
                    ELSE EXTRACT(DAY FROM NOW() - ec.last_event_at)::INT
                END AS days_since_last_event,
                ia.email                    AS idp_email,
                ia.employment_status        AS idp_employment_status
            FROM external_collaborators ec
            LEFT JOIN idp_actor_enrichments ia
                ON ia.github_login = ec.login
            WHERE ec.org       = ANY(:scoped_orgs)
              AND ec.status    = 'active'
            ORDER BY ec.added_at DESC
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
            WHERE org = ANY(:scoped_orgs) AND status = 'active'
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
                login AS github_login, org, repo, role,
                added_at AS granted_at, last_event_at,
                CASE
                    WHEN last_event_at IS NULL
                        THEN EXTRACT(DAY FROM NOW() - added_at)::INT
                    ELSE EXTRACT(DAY FROM NOW() - last_event_at)::INT
                END AS days_inactive
            FROM external_collaborators
            WHERE org = ANY(:scoped_orgs)
              AND status = 'active'
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


# ── Phase 1: Audit stream, security, secret scanning, SSO, privilege, visibility ──


async def get_audit_stream_status(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Most recent streaming config event per org (last 7 days)."""
    result = await session.execute(
        text("""
            SELECT DISTINCT ON (org)
                org, action, actor, created_at,
                EXTRACT(HOURS FROM NOW() - created_at)::INT AS hours_ago
            FROM events
            WHERE action LIKE 'audit_log_streaming.%%'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '7 days'
            ORDER BY org, created_at DESC
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_security_coverage(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Security feature enable/disable state per org (90 days)."""
    result = await session.execute(
        text("""
            WITH feature_states AS (
                SELECT DISTINCT ON (org, repo,
                    CASE
                        WHEN action LIKE 'secret_scanning%%' THEN 'secret_scanning'
                        WHEN action LIKE 'repository_secret_scanning%%'
                            THEN 'secret_scanning'
                        WHEN action LIKE 'dependency_graph%%' THEN 'dependency_graph'
                        WHEN action LIKE 'dependabot%%' THEN 'dependabot'
                        WHEN action LIKE '%%codeql%%' THEN 'codeql'
                        WHEN action LIKE '%%advanced_security%%' THEN 'ghas'
                        ELSE 'other'
                    END
                )
                    org, repo,
                    CASE
                        WHEN action LIKE 'secret_scanning%%' THEN 'secret_scanning'
                        WHEN action LIKE 'repository_secret_scanning%%'
                            THEN 'secret_scanning'
                        WHEN action LIKE 'dependency_graph%%' THEN 'dependency_graph'
                        WHEN action LIKE 'dependabot%%' THEN 'dependabot'
                        WHEN action LIKE '%%codeql%%' THEN 'codeql'
                        WHEN action LIKE '%%advanced_security%%' THEN 'ghas'
                        ELSE 'other'
                    END AS feature,
                    action,
                    CASE
                        WHEN action LIKE '%%.disable%%' OR action LIKE '%%_disabled%%'
                            THEN 'disabled'
                        ELSE 'enabled'
                    END AS state,
                    created_at, actor
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND (action LIKE 'secret_scanning%%'
                       OR action LIKE 'repository_secret_scanning%%'
                       OR action LIKE 'dependency_graph%%'
                       OR action LIKE 'dependabot%%'
                       OR action LIKE '%%codeql%%'
                       OR action LIKE '%%advanced_security%%')
                  AND repo IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '90 days'
                ORDER BY org, repo,
                    CASE
                        WHEN action LIKE 'secret_scanning%%' THEN 'secret_scanning'
                        WHEN action LIKE 'repository_secret_scanning%%'
                            THEN 'secret_scanning'
                        WHEN action LIKE 'dependency_graph%%' THEN 'dependency_graph'
                        WHEN action LIKE 'dependabot%%' THEN 'dependabot'
                        WHEN action LIKE '%%codeql%%' THEN 'codeql'
                        WHEN action LIKE '%%advanced_security%%' THEN 'ghas'
                        ELSE 'other'
                    END,
                    created_at DESC
            )
            SELECT
                org,
                COUNT(DISTINCT repo) AS total_repos,
                COUNT(DISTINCT repo) FILTER (
                    WHERE feature = 'secret_scanning' AND state = 'enabled'
                ) AS secret_scanning_enabled,
                COUNT(DISTINCT repo) FILTER (
                    WHERE feature = 'dependabot' AND state = 'enabled'
                ) AS dependabot_enabled,
                COUNT(DISTINCT repo) FILTER (
                    WHERE feature = 'codeql' AND state = 'enabled'
                ) AS codeql_enabled,
                COUNT(DISTINCT repo) FILTER (
                    WHERE feature = 'ghas' AND state = 'enabled'
                ) AS ghas_enabled,
                COUNT(DISTINCT repo) FILTER (
                    WHERE state = 'disabled'
                ) AS any_feature_disabled
            FROM feature_states
            GROUP BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_secret_scanning_alert_health(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Secret scanning MTTR and unresolved counts (90 days)."""
    result = await session.execute(
        text("""
            WITH alerts AS (
                SELECT
                    org,
                    data->>'number'                         AS alert_number,
                    data->>'secret_type'                    AS secret_type,
                    data->>'secret_type_display_name'       AS secret_type_display_name,
                    (data->>'publicly_leaked')::BOOLEAN     AS publicly_leaked,
                    (data->>'multi_repo')::BOOLEAN          AS multi_repo,
                    action,
                    actor,
                    created_at
                FROM events
                WHERE namespace = 'secret_scanning_alert'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
            ),
            opens AS (
                SELECT org, alert_number, secret_type, publicly_leaked,
                       created_at AS opened_at
                FROM alerts WHERE action = 'secret_scanning_alert.create'
            ),
            resolves AS (
                SELECT org, alert_number, created_at AS resolved_at
                FROM alerts WHERE action = 'secret_scanning_alert.resolve'
            ),
            mttr AS (
                SELECT
                    o.org,
                    AVG(EXTRACT(HOURS FROM r.resolved_at - o.opened_at))
                        AS avg_hours_to_resolve,
                    COUNT(*) AS resolved_count
                FROM opens o
                JOIN resolves r USING (org, alert_number)
                GROUP BY o.org
            ),
            unresolved AS (
                SELECT
                    o.org,
                    COUNT(*) AS unresolved_total,
                    COUNT(*) FILTER (
                        WHERE NOW() - o.opened_at > INTERVAL '7 days'
                    ) AS unresolved_gt_7d,
                    COUNT(*) FILTER (
                        WHERE NOW() - o.opened_at > INTERVAL '30 days'
                    ) AS unresolved_gt_30d,
                    COUNT(*) FILTER (
                        WHERE o.publicly_leaked = TRUE
                    ) AS publicly_leaked_count
                FROM opens o
                LEFT JOIN resolves r USING (org, alert_number)
                WHERE r.alert_number IS NULL
                GROUP BY o.org
            )
            SELECT
                u.org,
                u.unresolved_total,
                u.unresolved_gt_7d,
                u.unresolved_gt_30d,
                u.publicly_leaked_count,
                m.avg_hours_to_resolve,
                m.resolved_count
            FROM unresolved u
            LEFT JOIN mttr m USING (org)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_sso_health(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Most recent SSO enable/disable state per org (90 days)."""
    result = await session.execute(
        text("""
            SELECT DISTINCT ON (org)
                org, action, actor, created_at,
                CASE WHEN action = 'org.disable_saml'
                     THEN 'disabled' ELSE 'enabled'
                END AS sso_state
            FROM events
            WHERE action IN ('org.disable_saml', 'org.enable_saml')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
            ORDER BY org, created_at DESC
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_privilege_change_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Admin promotions, integration manager grants (30 days)."""
    result = await session.execute(
        text("""
            SELECT
                org,
                COUNT(*) FILTER (
                    WHERE action = 'org.member_to_admin'
                ) AS admin_promotions,
                COUNT(*) FILTER (
                    WHERE action = 'org.integration_manager_added'
                ) AS integration_mgr_grants,
                COUNT(*) FILTER (
                    WHERE action LIKE 'organization_role.%%'
                ) AS custom_role_changes,
                MIN(created_at) AS earliest_event,
                MAX(created_at) AS latest_event
            FROM events
            WHERE action IN (
                'org.member_to_admin',
                'org.integration_manager_added',
                'organization_role.create',
                'organization_role.update',
                'organization_role.destroy'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '30 days'
            GROUP BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_repo_visibility_trends(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Private/internal to public transitions (90 days)."""
    result = await session.execute(
        text("""
            SELECT
                DATE_TRUNC('week', created_at)           AS week,
                org,
                data->>'previous_visibility'             AS from_visibility,
                data->>'visibility'                      AS to_visibility,
                COUNT(*)                                 AS change_count,
                ARRAY_AGG(repo ORDER BY created_at DESC) AS repos_changed
            FROM events
            WHERE action = 'repo.access'
              AND org = ANY(:scoped_orgs)
              AND data->>'visibility' = 'public'
              AND data->>'previous_visibility' IN ('private', 'internal')
              AND created_at >= NOW() - INTERVAL '90 days'
            GROUP BY 1, 2, 3, 4
            ORDER BY week DESC
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


# ── Phase 2: Code scanning, vulnerabilities, app governance, webhooks ─────────


async def get_code_scanning_health(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Code scanning MTTR, dismissal rates (90 days)."""
    result = await session.execute(
        text("""
            WITH created AS (
                SELECT org, repo, data->>'alert_number' AS alert_num,
                       created_at AS opened_at
                FROM events
                WHERE action = 'code_scanning.alert_created'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
            ),
            closed AS (
                SELECT org, repo, data->>'alert_number' AS alert_num,
                       created_at AS closed_at
                FROM events
                WHERE action = 'code_scanning.alert_closed_by_user'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
            ),
            dismissed AS (
                SELECT org, repo, COUNT(*) AS dismissed_count
                FROM events
                WHERE action = 'code_scanning.alert_closed_by_user'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '30 days'
                GROUP BY org, repo
            ),
            reappeared AS (
                SELECT org, repo, COUNT(*) AS reappear_count
                FROM events
                WHERE action = 'code_scanning.alert_reappeared'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '30 days'
                GROUP BY org, repo
            )
            SELECT
                c.org,
                c.repo,
                COUNT(*) AS total_alerts_30d,
                AVG(EXTRACT(HOURS FROM cl.closed_at - c.opened_at))
                    AS avg_hours_to_close,
                COALESCE(d.dismissed_count, 0) AS dismissed_30d,
                COALESCE(r.reappear_count, 0)  AS reappeared_30d
            FROM created c
            LEFT JOIN closed cl USING (org, repo, alert_num)
            LEFT JOIN dismissed d USING (org, repo)
            LEFT JOIN reappeared r USING (org, repo)
            GROUP BY c.org, c.repo, d.dismissed_count, r.reappear_count
            ORDER BY total_alerts_30d DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_vulnerability_aging(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Dependabot vulnerability aging (180 days)."""
    result = await session.execute(
        text("""
            WITH created_alerts AS (
                SELECT
                    org,
                    repo,
                    data->>'alert_number'         AS alert_number,
                    data->>'severity'             AS severity,
                    data->>'package_name'         AS package_name,
                    data->>'affected_range'       AS affected_range,
                    created_at                    AS alert_created_at
                FROM events
                WHERE action = 'repository_vulnerability_alert.create'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '180 days'
            ),
            dismissed_alerts AS (
                SELECT org, repo, data->>'alert_number' AS alert_number
                FROM events
                WHERE action IN (
                    'repository_vulnerability_alert.dismiss',
                    'repository_vulnerability_alert.resolve'
                )
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '180 days'
            )
            SELECT
                c.org,
                COUNT(*) FILTER (WHERE d.alert_number IS NULL)
                    AS total_open,
                COUNT(*) FILTER (
                    WHERE d.alert_number IS NULL AND c.severity = 'critical'
                ) AS open_critical,
                COUNT(*) FILTER (
                    WHERE d.alert_number IS NULL AND c.severity = 'high'
                ) AS open_high,
                COUNT(*) FILTER (
                    WHERE d.alert_number IS NULL
                      AND NOW() - c.alert_created_at > INTERVAL '30 days'
                ) AS open_gt_30d,
                COUNT(*) FILTER (
                    WHERE d.alert_number IS NULL
                      AND c.severity = 'critical'
                      AND NOW() - c.alert_created_at > INTERVAL '14 days'
                ) AS critical_open_gt_14d,
                AVG(EXTRACT(DAYS FROM NOW() - c.alert_created_at))
                    FILTER (WHERE d.alert_number IS NULL) AS avg_open_days
            FROM created_alerts c
            LEFT JOIN dismissed_alerts d USING (org, repo, alert_number)
            GROUP BY c.org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_app_governance_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """OAuth/GitHub App summary (90 days)."""
    result = await session.execute(
        text("""
            SELECT
                org,
                COUNT(*) FILTER (
                    WHERE action = 'integration_installation.create'
                ) AS apps_installed_90d,
                COUNT(*) FILTER (
                    WHERE action = 'integration_installation.delete'
                ) AS apps_removed_90d,
                COUNT(*) FILTER (
                    WHERE action = 'org.oauth_app_access_approved'
                ) AS oauth_apps_approved_90d,
                COUNT(*) FILTER (
                    WHERE action = 'org.oauth_app_access_denied'
                ) AS oauth_apps_denied_90d,
                COUNT(*) FILTER (
                    WHERE action = 'integration.revoke_all_tokens'
                ) AS token_revocations_90d
            FROM events
            WHERE action IN (
                'integration_installation.create',
                'integration_installation.delete',
                'org.oauth_app_access_approved',
                'org.oauth_app_access_denied',
                'integration.revoke_all_tokens'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
            GROUP BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_webhook_activity(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Recent webhook creation/modification activity (30 days)."""
    result = await session.execute(
        text("""
            SELECT
                org,
                COUNT(*) FILTER (WHERE action = 'hook.create')
                    AS webhooks_created_30d,
                COUNT(*) FILTER (WHERE action = 'hook.destroy')
                    AS webhooks_removed_30d,
                COUNT(*) FILTER (WHERE action = 'hook.events_changed')
                    AS webhooks_modified_30d
            FROM events
            WHERE action IN ('hook.create', 'hook.destroy', 'hook.events_changed')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '30 days'
            GROUP BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


# ── Phase 3: Workflows, branch protection, Copilot, codespaces, runners ──────


async def get_workflow_health(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Workflow failure rates (30 days)."""
    result = await session.execute(
        text("""
            WITH run_outcomes AS (
                SELECT
                    org,
                    repo,
                    data->>'name'           AS workflow_name,
                    data->>'workflow_id'    AS workflow_id,
                    data->>'conclusion'     AS conclusion,
                    data->>'head_branch'    AS head_branch,
                    created_at
                FROM events
                WHERE action = 'workflows.completed_workflow_run'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '30 days'
            )
            SELECT
                org,
                repo,
                workflow_name,
                COUNT(*)                           AS total_runs,
                COUNT(*) FILTER (WHERE conclusion = 'success')
                    AS successes,
                COUNT(*) FILTER (WHERE conclusion = 'failure')
                    AS failures,
                COUNT(*) FILTER (WHERE conclusion = 'cancelled')
                    AS cancelled,
                ROUND(
                    100.0 * COUNT(*) FILTER (WHERE conclusion = 'failure')
                    / NULLIF(COUNT(*), 0), 2
                ) AS failure_rate_pct,
                MAX(created_at) AS last_run_at
            FROM run_outcomes
            GROUP BY org, repo, workflow_name
            HAVING COUNT(*) >= 5
            ORDER BY failure_rate_pct DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_workflow_secret_usage(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    threshold: int = 5,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Jobs with excessive secrets passed (7 days)."""
    result = await session.execute(
        text("""
            SELECT
                org,
                repo,
                data->>'job_name'            AS job_name,
                data->>'workflow_run_id'     AS workflow_run_id,
                jsonb_array_length(
                    COALESCE((data->'secrets_passed')::JSONB, '[]'::JSONB)
                ) AS secrets_count,
                created_at
            FROM events
            WHERE action = 'workflows.prepared_workflow_job'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '7 days'
              AND jsonb_array_length(
                  COALESCE((data->'secrets_passed')::JSONB, '[]'::JSONB)
              ) > :threshold
            ORDER BY secrets_count DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "threshold": threshold, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_branch_protection_health(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Branch protection change summary (30 days)."""
    result = await session.execute(
        text("""
            WITH protection_changes AS (
                SELECT
                    org, repo, action, actor, created_at,
                    CASE
                        WHEN action LIKE '%%policy_override%%' THEN 'override'
                        WHEN action LIKE '%%update%%'
                             OR action LIKE '%%create%%' THEN 'modified'
                        WHEN action IN ('protected_branch.destroy',
                                        'required_status_check.destroy')
                            THEN 'removed'
                        ELSE 'other'
                    END AS change_type
                FROM events
                WHERE namespace IN ('protected_branch', 'required_status_check',
                                    'repository_ruleset')
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '30 days'
            )
            SELECT
                org,
                COUNT(*) FILTER (WHERE change_type = 'removed')
                    AS protections_removed_30d,
                COUNT(*) FILTER (WHERE change_type = 'override')
                    AS policy_overrides_30d,
                COUNT(*) FILTER (WHERE change_type = 'modified')
                    AS protections_modified_30d,
                COUNT(DISTINCT actor)  AS distinct_actors,
                COUNT(DISTINCT repo)   AS distinct_repos_affected
            FROM protection_changes
            GROUP BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_copilot_seat_health(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Copilot seat utilization (90 days)."""
    result = await session.execute(
        text("""
            WITH seat_events AS (
                SELECT
                    org,
                    action,
                    actor,
                    data->>'user' AS target_user,
                    created_at
                FROM events
                WHERE namespace = 'copilot'
                  AND action IN (
                      'copilot.cfb_seat_added',
                      'copilot.cfb_seat_cancelled',
                      'copilot.cfb_seat_assignment_created',
                      'copilot.cfb_seat_assignment_unassigned'
                  )
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
            )
            SELECT
                org,
                COUNT(*) FILTER (
                    WHERE action LIKE '%%seat_added%%'
                       OR action LIKE '%%seat_assignment_created%%'
                ) AS seats_granted_90d,
                COUNT(*) FILTER (
                    WHERE action LIKE '%%cancelled%%'
                       OR action LIKE '%%unassigned%%'
                ) AS seats_removed_90d,
                COUNT(DISTINCT target_user) FILTER (
                    WHERE action LIKE '%%seat_added%%'
                ) AS unique_users_granted,
                MAX(created_at) FILTER (
                    WHERE action = 'copilot.cfb_seat_management_changed'
                ) AS last_policy_change_at
            FROM seat_events
            GROUP BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_codespace_cost_signals(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Codespace active/cost signals (30 days)."""
    result = await session.execute(
        text("""
            WITH codespace_lifecycle AS (
                SELECT DISTINCT ON (org, data->>'name', actor)
                    org,
                    repo,
                    actor,
                    data->>'name'         AS codespace_name,
                    data->>'machine_type' AS machine_type,
                    action,
                    created_at
                FROM events
                WHERE namespace = 'codespaces'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '30 days'
                ORDER BY org, data->>'name', actor, created_at DESC
            ),
            created AS (
                SELECT org, repo, actor, codespace_name, machine_type,
                       created_at
                FROM codespace_lifecycle WHERE action = 'codespaces.create'
            ),
            suspended AS (
                SELECT org, codespace_name, created_at AS suspended_at
                FROM codespace_lifecycle
                WHERE action = 'codespaces.suspend_environment'
            ),
            destroyed AS (
                SELECT org, codespace_name
                FROM codespace_lifecycle WHERE action = 'codespaces.destroy'
            )
            SELECT
                c.org,
                COUNT(*) FILTER (
                    WHERE d.codespace_name IS NULL AND s.codespace_name IS NULL
                ) AS active_never_suspended,
                COUNT(*) FILTER (
                    WHERE c.machine_type IN (
                        'largePremium', 'xLargePremium', '16core', '32core'
                    )
                ) AS large_machine_count,
                COUNT(DISTINCT c.actor) AS unique_users_with_codespaces,
                MAX(c.created_at) AS most_recent_create
            FROM created c
            LEFT JOIN destroyed d USING (org, codespace_name)
            LEFT JOIN suspended s USING (org, codespace_name)
            GROUP BY c.org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_runner_fleet_health(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Self-hosted runner fleet (7 days)."""
    result = await session.execute(
        text("""
            SELECT
                org,
                repo,
                data->>'runner_id'           AS runner_id,
                data->>'runner_name'         AS runner_name,
                data->>'source_version'      AS source_version,
                data->>'target_version'      AS target_version,
                data->>'runner_group_name'   AS runner_group,
                action,
                created_at
            FROM events
            WHERE action IN (
                'org.self_hosted_runner_updated',
                'repo.self_hosted_runner_updated',
                'org.add_self_hosted_runner',
                'repo.add_self_hosted_runner'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '7 days'
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


# ── Phase 4: Ingestion gaps, system health, threat intel ─────────────────────


async def get_ingestion_gap_status(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Check for data gaps per org."""
    result = await session.execute(
        text("""
            SELECT
                org,
                MAX(created_at) AS last_event_at,
                EXTRACT(MINUTES FROM NOW() - MAX(created_at))::INT
                    AS minutes_since_last
            FROM events
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY org
        """),
        {"scoped_orgs": scoped_orgs},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_system_health_events(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Active system health warnings."""
    result = await session.execute(
        text("""
            SELECT id, occurred_at, org, signal_type, severity, detail
            FROM system_health_events
            WHERE (org = ANY(:scoped_orgs) OR org IS NULL)
              AND resolved_at IS NULL
            ORDER BY occurred_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_threat_intel_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> dict[str, Any]:
    """Threat intel domain stats."""
    result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_domains,
                COUNT(*) FILTER (WHERE active = TRUE) AS active_domains,
                COUNT(*) FILTER (
                    WHERE expires_at IS NOT NULL AND expires_at < NOW()
                ) AS expired_domains,
                MAX(added_at) AS last_added_at
            FROM threat_intel_domains
        """),
    )
    row = result.mappings().first()
    if not row:
        return {
            "total_domains": 0,
            "active_domains": 0,
            "expired_domains": 0,
            "last_added_at": None,
        }
    return dict(row)


async def get_ghost_members(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    dormancy_days: int = 90,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find members with no audit log activity in the last N days."""
    result = await session.execute(
        text(f"""
            WITH all_actors AS (
                SELECT DISTINCT actor FROM events
                WHERE org = ANY(:scoped_orgs) AND actor IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '365 days'
            ),
            recent_actors AS (
                SELECT DISTINCT actor FROM events
                WHERE org = ANY(:scoped_orgs) AND actor IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '{int(dormancy_days)} days'
            )
            SELECT a.actor,
                   e.last_active
            FROM all_actors a
            LEFT JOIN LATERAL (
                SELECT MAX(created_at) AS last_active FROM events
                WHERE actor = a.actor AND org = ANY(:scoped_orgs)
            ) e ON true
            WHERE a.actor NOT IN (SELECT actor FROM recent_actors)
            ORDER BY e.last_active ASC NULLS FIRST
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_stale_prs(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    stale_days: int = 30,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find PRs that have been open longer than stale_days."""
    result = await session.execute(
        text(f"""
            WITH opened AS (
                SELECT org, repo, data->>'number' AS pr_number,
                       data->>'title' AS title, actor,
                       created_at AS opened_at
                FROM events
                WHERE action IN ('pull_request.opened', 'pull_request.reopened')
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '365 days'
            ),
            closed AS (
                SELECT org, repo, data->>'number' AS pr_number
                FROM events
                WHERE action IN ('pull_request.closed', 'pull_request.merged')
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '365 days'
            )
            SELECT o.org, o.repo, o.pr_number, o.title, o.actor, o.opened_at,
                   EXTRACT(DAYS FROM NOW() - o.opened_at)::INT AS days_open
            FROM opened o
            LEFT JOIN closed c USING (org, repo, pr_number)
            WHERE c.pr_number IS NULL
              AND o.opened_at < NOW() - INTERVAL '{int(stale_days)} days'
            ORDER BY o.opened_at ASC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_unhealthy_webhooks(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find webhooks/apps with recent error signals."""
    result = await session.execute(
        text("""
            SELECT org, repo, action, actor,
                   data->>'hook_id' AS hook_id,
                   data->>'name' AS app_name,
                   data->>'config_url' AS config_url,
                   created_at
            FROM events
            WHERE action IN (
                'hook.destroy', 'integration.destroy',
                'oauth_application.destroy', 'hook.create',
                'integration_installation.destroy'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_skipped_workflows(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find workflows that have been disabled or are consistently skipped."""
    result = await session.execute(
        text("""
            SELECT org, repo, action, actor,
                   data->>'name' AS workflow_name,
                   data->>'workflow_id' AS workflow_id,
                   created_at
            FROM events
            WHERE action IN (
                'workflows.disable_workflow',
                'workflows.delete_workflow'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_waf_findings(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> list[dict[str, Any]]:
    """Evaluate Well-Architected Framework alignment signals against audit events."""
    findings: list[dict[str, Any]] = []

    # 1. Audit log streaming (governance / security)
    stream_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action LIKE 'audit_log_streaming.%%'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '30 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    stream_count = stream_result.scalar() or 0
    findings.append(
        {
            "id": "waf-audit-streaming",
            "pillar": "governance",
            "finding": "Audit log streaming configuration",
            "severity": "info" if stream_count > 0 else "warning",
            "status": "pass" if stream_count > 0 else "warning",
            "evaluated": True,
            "detail": (
                f"{stream_count} streaming events in last 30 days"
                if stream_count > 0
                else "No audit log streaming events detected"
            ),
            "evidence_count": stream_count,
        }
    )

    # 2. Secret scanning enablement (security)
    secret_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE action = 'repository.enable_secret_scanning'
                ) AS enabled,
                COUNT(*) FILTER (
                    WHERE action = 'repository.disable_secret_scanning'
                ) AS disabled
            FROM events
            WHERE action IN (
                'repository.enable_secret_scanning',
                'repository.disable_secret_scanning'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    secret_row = secret_result.mappings().first()
    enabled_count = (secret_row["enabled"] if secret_row else 0) or 0
    disabled_count = (secret_row["disabled"] if secret_row else 0) or 0
    findings.append(
        {
            "id": "waf-secret-scanning",
            "pillar": "appsec",
            "finding": "Secret scanning enablement",
            "severity": "critical" if disabled_count > 0 else "info",
            "status": "fail" if disabled_count > 0 else "pass",
            "evaluated": True,
            "detail": (
                f"{disabled_count} repos disabled secret scanning, "
                f"{enabled_count} repos enabled in last 90 days"
            ),
            "evidence_count": enabled_count + disabled_count,
        }
    )

    # 3. Branch protection coverage (reliability)
    bp_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE action IN (
                        'protected_branch.destroy',
                        'protected_branch.policy_override'
                    )
                ) AS removed_or_overridden,
                COUNT(*) FILTER (
                    WHERE action = 'protected_branch.create'
                ) AS created
            FROM events
            WHERE action IN (
                'protected_branch.create',
                'protected_branch.destroy',
                'protected_branch.policy_override'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    bp_row = bp_result.mappings().first()
    bp_removed = (bp_row["removed_or_overridden"] if bp_row else 0) or 0
    bp_created = (bp_row["created"] if bp_row else 0) or 0
    findings.append(
        {
            "id": "waf-branch-protection",
            "pillar": "governance",
            "finding": "Branch protection coverage",
            "severity": "critical" if bp_removed > bp_created else "info",
            "status": "fail" if bp_removed > bp_created else "pass",
            "evaluated": True,
            "detail": (
                f"{bp_created} branch protections created, "
                f"{bp_removed} removed/overridden in last 90 days"
            ),
            "evidence_count": bp_created + bp_removed,
        }
    )

    # 4. SAML/SSO status (security)
    sso_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE action LIKE 'org.saml_%%' OR action LIKE 'org.sso_%%'
                ) AS sso_events,
                COUNT(*) FILTER (
                    WHERE action IN (
                        'org.disable_saml', 'org.disable_two_factor_requirement'
                    )
                ) AS sso_disabled
            FROM events
            WHERE (action LIKE 'org.saml_%%'
                   OR action LIKE 'org.sso_%%'
                   OR action = 'org.disable_two_factor_requirement')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    sso_row = sso_result.mappings().first()
    sso_events = (sso_row["sso_events"] if sso_row else 0) or 0
    sso_disabled = (sso_row["sso_disabled"] if sso_row else 0) or 0
    findings.append(
        {
            "id": "waf-sso-status",
            "pillar": "governance",
            "finding": "SAML / SSO enforcement",
            "severity": "critical" if sso_disabled > 0 else "info",
            "status": ("fail" if sso_disabled > 0 else ("pass" if sso_events > 0 else "warning")),
            "evaluated": True,
            "detail": (
                f"{sso_disabled} SSO disable events detected"
                if sso_disabled > 0
                else (
                    f"{sso_events} SSO configuration events in last 90 days"
                    if sso_events > 0
                    else "No SSO-related events detected"
                )
            ),
            "evidence_count": sso_events,
        }
    )

    # 5. IP allowlist (security)
    ip_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action LIKE 'ip_allow_list%%'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    ip_count = ip_result.scalar() or 0
    findings.append(
        {
            "id": "waf-ip-allowlist",
            "pillar": "governance",
            "finding": "IP allowlist configuration",
            "severity": "info" if ip_count > 0 else "warning",
            "status": "pass" if ip_count > 0 else "warning",
            "evaluated": True,
            "detail": (
                f"{ip_count} IP allowlist events in last 90 days"
                if ip_count > 0
                else "No IP allowlist configuration events detected"
            ),
            "evidence_count": ip_count,
        }
    )

    # 6. Dependabot alerts (operational excellence)
    dep_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE action = 'dependabot_alerts.enable'
                ) AS enabled,
                COUNT(*) FILTER (
                    WHERE action = 'dependabot_alerts.disable'
                ) AS disabled
            FROM events
            WHERE action IN (
                'dependabot_alerts.enable', 'dependabot_alerts.disable'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    dep_row = dep_result.mappings().first()
    dep_enabled = (dep_row["enabled"] if dep_row else 0) or 0
    dep_disabled = (dep_row["disabled"] if dep_row else 0) or 0
    findings.append(
        {
            "id": "waf-dependabot",
            "pillar": "appsec",
            "finding": "Dependabot alert coverage",
            "severity": "warning" if dep_disabled > 0 else "info",
            "status": "warning" if dep_disabled > 0 else "pass",
            "evaluated": True,
            "detail": (
                f"{dep_disabled} repos disabled Dependabot alerts, "
                f"{dep_enabled} repos enabled in last 90 days"
            ),
            "evidence_count": dep_enabled + dep_disabled,
        }
    )

    # 7. Code scanning (security)
    cs_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action LIKE 'code_scanning.%%'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    cs_count = cs_result.scalar() or 0
    findings.append(
        {
            "id": "waf-code-scanning",
            "pillar": "appsec",
            "finding": "Code scanning activity",
            "severity": "info" if cs_count > 0 else "warning",
            "status": "pass" if cs_count > 0 else "warning",
            "evaluated": True,
            "detail": (
                f"{cs_count} code scanning events in last 90 days"
                if cs_count > 0
                else "No code scanning events detected"
            ),
            "evidence_count": cs_count,
        }
    )

    # 8. Webhook health (operational excellence)
    wh_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE action = 'hook.destroy'
                ) AS destroyed,
                COUNT(*) FILTER (
                    WHERE action = 'hook.create'
                ) AS created
            FROM events
            WHERE action IN ('hook.create', 'hook.destroy')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    wh_row = wh_result.mappings().first()
    wh_destroyed = (wh_row["destroyed"] if wh_row else 0) or 0
    wh_created = (wh_row["created"] if wh_row else 0) or 0
    findings.append(
        {
            "id": "waf-webhook-health",
            "pillar": "governance",
            "finding": "Webhook lifecycle management",
            "severity": "warning" if wh_destroyed > wh_created else "info",
            "status": "warning" if wh_destroyed > wh_created else "pass",
            "evaluated": True,
            "detail": (f"{wh_created} webhooks created, {wh_destroyed} destroyed in last 90 days"),
            "evidence_count": wh_created + wh_destroyed,
        }
    )

    # 9. Push protection bypasses (governance)
    bypass_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action = 'secret_scanning.push_protection.bypass'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    bypass_count = bypass_result.scalar() or 0
    findings.append(
        {
            "id": "waf-push-protection-bypass",
            "pillar": "governance",
            "finding": "Push protection bypass events",
            "severity": "critical" if bypass_count > 0 else "info",
            "status": "fail" if bypass_count > 0 else "pass",
            "evaluated": True,
            "detail": (
                f"{bypass_count} push protection bypasses in last 90 days"
                if bypass_count > 0
                else "No push protection bypass events detected"
            ),
            "evidence_count": bypass_count,
        }
    )

    # 10. Direct pushes to default branch (appsec)
    push_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action = 'git.push'
              AND (data->>'ref' = 'refs/heads/main'
                   OR data->>'ref' = 'refs/heads/master')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    push_count = push_result.scalar() or 0
    findings.append(
        {
            "id": "waf-direct-push",
            "pillar": "appsec",
            "finding": "Direct pushes to default branch",
            "severity": "warning" if push_count > 5 else "info",
            "status": "warning" if push_count > 5 else "pass",
            "evaluated": True,
            "detail": f"{push_count} direct pushes to main/master in last 90 days",
            "evidence_count": push_count,
        }
    )

    return findings
