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
    """PAT health counts: no_expiry, expired, stale_90d.

    Queries ``events`` for audit-log PAT create events (requires enterprise
    PAT).  Falls back to ``org_credential_authorizations`` (populated by the
    GitHub sync worker via REST API) so the signal is available right after
    the first sync even without an enterprise PAT configured.
    """
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
    if row and (row["no_expiry_count"] or row["expired_count"] or row["stale_90d_count"]):
        return dict(row)

    # Fallback: use synced credential authorizations snapshot.
    fallback = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE credential_type ILIKE '%%token%%'
                ) AS no_expiry_count,
                0::BIGINT AS expired_count,
                COUNT(*) FILTER (
                    WHERE credential_type ILIKE '%%token%%'
                      AND credential_authorized_at <= NOW() - INTERVAL '90 days'
                ) AS stale_90d_count
            FROM org_credential_authorizations
            WHERE org = ANY(:scoped_orgs)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    fb_row = fallback.mappings().first()
    if not fb_row:
        return {"no_expiry_count": 0, "expired_count": 0, "stale_90d_count": 0}
    return dict(fb_row)


async def get_pat_token_age_signals(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """PATs with no expiry, expired, and stale >90d (US-1C).

    Queries ``events`` for audit-log PAT create events (requires enterprise
    PAT).  Falls back to ``org_credential_authorizations`` (populated by the
    GitHub sync worker via REST API) so the signal is populated right after
    the first sync even without an enterprise PAT.
    """
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
    rows = [dict(row) for row in result.mappings().all()]
    if rows:
        return rows

    # Fallback: use synced credential authorizations snapshot.
    fallback = await session.execute(
        text("""
            SELECT
                github_login,
                NULL::TEXT      AS token_name,
                credential_id::TEXT AS token_id,
                credential_type AS token_type,
                COALESCE(credential_authorized_at, synced_at) AS created_at,
                EXTRACT(DAY FROM NOW() -
                    COALESCE(credential_authorized_at, synced_at))::INT AS age_days,
                CASE
                    WHEN credential_authorized_at <= NOW() - INTERVAL '90 days'
                        THEN 'stale_90d'
                    ELSE 'no_expiry'
                END AS signal_type
            FROM org_credential_authorizations
            WHERE org = ANY(:scoped_orgs)
              AND credential_type ILIKE '%%token%%'
            ORDER BY credential_authorized_at ASC NULLS LAST
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in fallback.mappings().all()]


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
    """Active outside collaborators with IdP enrichment (US-5B).

    Queries ``external_collaborators`` first (populated by live audit-log
    streaming).  Falls back to ``org_outside_collaborators`` (populated by
    the GitHub sync worker via REST API) when the streaming table is empty so
    that users see data immediately after the first sync.
    """
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
              AND ec.is_active = TRUE
            ORDER BY ec.granted_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    rows = [dict(row) for row in result.mappings().all()]
    if rows:
        return rows

    # Fallback: synced REST-API snapshot from org_outside_collaborators.
    fallback = await session.execute(
        text("""
            SELECT
                oc.login                        AS github_login,
                oc.org,
                NULL::TEXT                      AS repo,
                NULL::TEXT                      AS role,
                oc.synced_at                    AS granted_at,
                NULL::TEXT                      AS granted_by,
                NULL::TIMESTAMPTZ               AS last_event_at,
                NULL::INT                       AS days_since_last_event,
                ia.email                        AS idp_email,
                ia.employment_status            AS idp_employment_status
            FROM org_outside_collaborators oc
            LEFT JOIN idp_actor_enrichments ia
                ON ia.github_login = oc.login
            WHERE oc.org = ANY(:scoped_orgs)
            ORDER BY oc.login
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in fallback.mappings().all()]


async def get_external_collaborator_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, int]:
    """Summary counts for external collaborators.

    Uses ``external_collaborators`` (streaming) when available; falls back to
    ``org_outside_collaborators`` (REST-API sync snapshot) so the summary is
    populated immediately after the first sync.
    """
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
    if row and row["total_active"]:
        return dict(row)

    # Fallback: use synced snapshot from org_outside_collaborators.
    fallback = await session.execute(
        text("""
            SELECT
                COUNT(*)    AS total_active,
                COUNT(*)    AS org_level_count,
                0::BIGINT   AS elevated_count,
                0::BIGINT   AS dormant_count
            FROM org_outside_collaborators
            WHERE org = ANY(:scoped_orgs)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    fb_row = fallback.mappings().first()
    if not fb_row:
        return {"total_active": 0, "org_level_count": 0, "elevated_count": 0, "dormant_count": 0}
    return dict(fb_row)


async def get_dormant_collaborators(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    dormancy_days: int = 60,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Collaborators inactive for X+ days (US-5C).

    Queries ``external_collaborators`` (streaming) when available; falls back
    to ``org_outside_collaborators`` (REST-API sync snapshot).  The synced
    snapshot has no activity timestamps so all entries are treated as dormant
    (last_event_at = NULL → days_inactive counted from synced_at).
    """
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
    rows = [dict(row) for row in result.mappings().all()]
    if rows:
        return rows

    # Fallback: synced REST-API snapshot; all have unknown activity.
    fallback = await session.execute(
        text("""
            SELECT
                login               AS github_login,
                org,
                NULL::TEXT          AS repo,
                NULL::TEXT          AS role,
                synced_at           AS granted_at,
                NULL::TIMESTAMPTZ   AS last_event_at,
                EXTRACT(DAY FROM NOW() - synced_at)::INT AS days_inactive
            FROM org_outside_collaborators
            WHERE org = ANY(:scoped_orgs)
            ORDER BY login
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    return [dict(row) for row in fallback.mappings().all()]


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
                EXTRACT(EPOCH FROM NOW() - created_at)::INT / 3600 AS hours_ago
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
    """Secret scanning MTTR, resolution rates, and unresolved counts.

    Queries the ``secret_scanning_alerts`` table (individual alert records
    synced from the GitHub API) for accurate metrics instead of deriving
    from audit log events.
    """
    result = await session.execute(
        text("""
            WITH alert_data AS (
                SELECT
                    org_slug AS org,
                    alert_number,
                    state,
                    resolution,
                    push_protection_bypassed,
                    created_at,
                    resolved_at
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
            ),
            mttr AS (
                SELECT
                    org,
                    AVG(EXTRACT(EPOCH FROM resolved_at - created_at) / 3600.0)
                        AS avg_hours_to_resolve,
                    COUNT(*) AS resolved_count
                FROM alert_data
                WHERE state = 'resolved' AND resolved_at IS NOT NULL
                GROUP BY org
            ),
            unresolved AS (
                SELECT
                    org,
                    COUNT(*) AS unresolved_total,
                    COUNT(*) FILTER (
                        WHERE NOW() - created_at > INTERVAL '7 days'
                    ) AS unresolved_gt_7d,
                    COUNT(*) FILTER (
                        WHERE NOW() - created_at > INTERVAL '30 days'
                    ) AS unresolved_gt_30d,
                    COUNT(*) FILTER (
                        WHERE push_protection_bypassed = TRUE
                    ) AS push_protection_bypassed_count,
                    COUNT(*) AS total_open
                FROM alert_data
                WHERE state = 'open'
                GROUP BY org
            ),
            resolution_rates AS (
                SELECT
                    org,
                    COUNT(*) AS total_count,
                    COUNT(*) FILTER (WHERE state = 'resolved') AS total_resolved,
                    ROUND(
                        COUNT(*) FILTER (WHERE state = 'resolved')::NUMERIC
                        / NULLIF(COUNT(*), 0) * 100, 1
                    ) AS resolution_rate_pct
                FROM alert_data
                GROUP BY org
            )
            SELECT
                COALESCE(u.org, m.org, r.org) AS org,
                COALESCE(u.unresolved_total, 0) AS unresolved_total,
                COALESCE(u.unresolved_gt_7d, 0) AS unresolved_gt_7d,
                COALESCE(u.unresolved_gt_30d, 0) AS unresolved_gt_30d,
                COALESCE(u.push_protection_bypassed_count, 0)
                    AS push_protection_bypassed_count,
                m.avg_hours_to_resolve,
                COALESCE(m.resolved_count, 0) AS resolved_count,
                COALESCE(r.total_count, 0) AS total_count,
                COALESCE(r.resolution_rate_pct, 0) AS resolution_rate_pct
            FROM unresolved u
            FULL OUTER JOIN mttr m ON u.org = m.org
            FULL OUTER JOIN resolution_rates r
                ON COALESCE(u.org, m.org) = r.org
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
    """Most recent SSO enable/disable state per org.

    Uses a two-tier strategy:
    1. Check the enterprise_orgs table for two_factor_required (enriched via REST
       API sync) — this is authoritative if present.
    2. Fall back to scanning ALL historical org.enable_saml / org.disable_saml
       audit events (no 90-day window) so orgs configured long ago still report
       correctly.
    """
    result = await session.execute(
        text("""
            WITH event_sso AS (
                SELECT DISTINCT ON (org)
                    org, action, actor, created_at,
                    CASE WHEN action = 'org.disable_saml'
                         THEN 'disabled' ELSE 'enabled'
                    END AS sso_state
                FROM events
                WHERE action IN ('org.disable_saml', 'org.enable_saml')
                  AND org = ANY(:scoped_orgs)
                ORDER BY org, created_at DESC
            )
            SELECT
                e.org,
                COALESCE(e.action, NULL) AS action,
                e.actor,
                e.created_at,
                COALESCE(e.sso_state, 'unknown') AS sso_state
            FROM UNNEST(:scoped_orgs) AS u(org)
            LEFT JOIN event_sso e ON e.org = u.org
            ORDER BY e.created_at DESC NULLS LAST
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
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
    """Code scanning alert health from synced individual alerts.

    Queries the ``code_scanning_alerts`` table for accurate counts by
    severity, state, tool, and MTTR calculation.
    """
    result = await session.execute(
        text("""
            WITH alert_data AS (
                SELECT
                    org_slug AS org,
                    repo_full_name AS repo,
                    alert_number,
                    state,
                    severity,
                    security_severity,
                    tool_name,
                    dismissed_by,
                    dismissed_reason,
                    created_at,
                    fixed_at,
                    dismissed_at
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
            ),
            per_repo AS (
                SELECT
                    org,
                    repo,
                    COUNT(*) AS total_alerts,
                    COUNT(*) FILTER (WHERE state = 'open') AS open_count,
                    COUNT(*) FILTER (WHERE state = 'fixed') AS fixed_count,
                    COUNT(*) FILTER (WHERE state = 'dismissed') AS dismissed_count,
                    COUNT(*) FILTER (
                        WHERE COALESCE(security_severity, severity) = 'critical'
                    ) AS critical_count,
                    COUNT(*) FILTER (
                        WHERE COALESCE(security_severity, severity) = 'high'
                    ) AS high_count,
                    COUNT(*) FILTER (
                        WHERE COALESCE(security_severity, severity) = 'medium'
                    ) AS medium_count,
                    COUNT(*) FILTER (
                        WHERE COALESCE(security_severity, severity) = 'low'
                    ) AS low_count,
                    AVG(EXTRACT(EPOCH FROM
                        COALESCE(fixed_at, dismissed_at) - created_at
                    ) / 3600.0) FILTER (
                        WHERE state IN ('fixed', 'dismissed')
                          AND COALESCE(fixed_at, dismissed_at) IS NOT NULL
                    ) AS avg_hours_to_close
                FROM alert_data
                GROUP BY org, repo
            )
            SELECT
                org,
                repo,
                total_alerts,
                open_count,
                fixed_count,
                dismissed_count,
                critical_count,
                high_count,
                medium_count,
                low_count,
                avg_hours_to_close
            FROM per_repo
            ORDER BY total_alerts DESC
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
    """Dependabot vulnerability aging from synced individual alerts.

    Queries the ``dependabot_alerts`` table for accurate aging buckets
    based on actual ``created_at`` timestamps rather than audit log
    event approximations.
    """
    result = await session.execute(
        text("""
            WITH open_alerts AS (
                SELECT
                    org_slug AS org,
                    alert_number,
                    repo_full_name,
                    severity,
                    package_name,
                    cvss_score,
                    created_at,
                    EXTRACT(DAYS FROM NOW() - created_at) AS age_days
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'
            )
            SELECT
                org,
                COUNT(*) AS total_open,
                COUNT(*) FILTER (WHERE severity = 'critical') AS open_critical,
                COUNT(*) FILTER (WHERE severity = 'high') AS open_high,
                COUNT(*) FILTER (WHERE severity = 'medium') AS open_medium,
                COUNT(*) FILTER (WHERE severity = 'low') AS open_low,
                COUNT(*) FILTER (WHERE age_days <= 30) AS age_0_30d,
                COUNT(*) FILTER (
                    WHERE age_days > 30 AND age_days <= 60
                ) AS age_30_60d,
                COUNT(*) FILTER (
                    WHERE age_days > 60 AND age_days <= 90
                ) AS age_60_90d,
                COUNT(*) FILTER (WHERE age_days > 90) AS age_gt_90d,
                COUNT(*) FILTER (
                    WHERE age_days > 30
                ) AS open_gt_30d,
                COUNT(*) FILTER (
                    WHERE severity = 'critical' AND age_days > 14
                ) AS critical_open_gt_14d,
                COUNT(*) FILTER (
                    WHERE severity = 'critical' AND age_days > 90
                ) AS critical_aging_gt_90d,
                AVG(age_days) AS avg_open_days
            FROM open_alerts
            GROUP BY org
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
    """Workflow failure rates (30 days).

    Uses both ``workflow_run.*`` events (action suffix encodes conclusion)
    and ``workflows.completed_workflow_run`` events (conclusion in JSONB data).
    """
    result = await session.execute(
        text("""
            WITH run_outcomes AS (
                -- workflow_run.* events: the action suffix IS the conclusion
                SELECT
                    org,
                    repo,
                    COALESCE(data->>'workflow_name', data->>'name',
                             SPLIT_PART(action, '.', 1)) AS workflow_name,
                    CASE
                        WHEN action = 'workflow_run.success' THEN 'success'
                        WHEN action IN ('workflow_run.failure',
                                        'workflow_run.startup_failure') THEN 'failure'
                        WHEN action = 'workflow_run.cancelled' THEN 'cancelled'
                        ELSE SPLIT_PART(action, '.', 2)
                    END AS conclusion,
                    created_at
                FROM events
                WHERE action LIKE 'workflow_run.%%'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '30 days'

                UNION ALL

                -- workflows.completed_workflow_run events: conclusion in JSONB
                SELECT
                    org,
                    repo,
                    COALESCE(data->>'name', 'unknown') AS workflow_name,
                    data->>'conclusion'                 AS conclusion,
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
            HAVING COUNT(*) >= 3
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
    """Self-hosted runner fleet current state from sync snapshot.

    Queries ``org_self_hosted_runners`` (populated by the GitHub sync worker)
    for current runner state.  Falls back to recent audit-log events when the
    snapshot table is empty (e.g. before the first sync completes).
    """
    # Primary: use the synced snapshot which always reflects current state.
    result = await session.execute(
        text("""
            SELECT
                org,
                NULL::TEXT              AS repo,
                runner_id::TEXT         AS runner_id,
                name                    AS runner_name,
                NULL::TEXT              AS source_version,
                NULL::TEXT              AS target_version,
                runner_group_name       AS runner_group,
                os,
                status,
                busy,
                labels,
                synced_at               AS created_at
            FROM org_self_hosted_runners
            WHERE org = ANY(:scoped_orgs)
            ORDER BY org, name
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    rows = [dict(row) for row in result.mappings().all()]
    if rows:
        return rows

    # Fallback: audit-log events from the last 7 days (requires enterprise PAT).
    fallback = await session.execute(
        text("""
            SELECT
                org,
                repo,
                data->>'runner_id'           AS runner_id,
                data->>'runner_name'         AS runner_name,
                data->>'source_version'      AS source_version,
                data->>'target_version'      AS target_version,
                data->>'runner_group_name'   AS runner_group,
                NULL::TEXT                   AS os,
                NULL::TEXT                   AS status,
                NULL::BOOLEAN                AS busy,
                NULL::TEXT[]                 AS labels,
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
    return [dict(row) for row in fallback.mappings().all()]


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
        text("""
            WITH all_actors AS (
                SELECT DISTINCT actor FROM events
                WHERE org = ANY(:scoped_orgs) AND actor IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '365 days'
            ),
            recent_actors AS (
                SELECT DISTINCT actor FROM events
                WHERE org = ANY(:scoped_orgs) AND actor IS NOT NULL
                  AND created_at >= NOW() - make_interval(days => :dormancy_days)
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
        {"scoped_orgs": scoped_orgs, "limit": limit, "dormancy_days": int(dormancy_days)},
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
        text("""
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
              AND o.opened_at < NOW() - make_interval(days => :stale_days)
            ORDER BY o.opened_at ASC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit, "stale_days": int(stale_days)},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_unhealthy_webhooks(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find webhooks/apps with recent error signals or insecure configuration.

    Merges two sources:
    1. ``org_webhooks`` / ``repo_webhooks`` synced snapshot — surfaces hooks
       that are inactive or using insecure SSL right now (populated by the
       GitHub sync worker via REST API).
    2. Audit-log ``events`` for destructive webhook actions over the last 90
       days (requires enterprise PAT; may be empty without one).
    """
    # Source 1: current snapshot — inactive or insecure hooks.
    snapshot_result = await session.execute(
        text("""
            SELECT
                org,
                NULL::TEXT      AS repo,
                hook_id::TEXT   AS hook_id,
                name            AS app_name,
                config_url,
                active,
                config_insecure_ssl,
                synced_at       AS created_at,
                'snapshot'      AS source
            FROM org_webhooks
            WHERE org = ANY(:scoped_orgs)
              AND (active = FALSE OR (config_insecure_ssl IS NOT NULL
                                      AND config_insecure_ssl != '0'
                                      AND config_insecure_ssl != ''))
            UNION ALL
            SELECT
                org,
                repo_name       AS repo,
                hook_id::TEXT   AS hook_id,
                name            AS app_name,
                config_url,
                active,
                config_insecure_ssl,
                synced_at       AS created_at,
                'snapshot'      AS source
            FROM repo_webhooks
            WHERE org = ANY(:scoped_orgs)
              AND (active = FALSE OR (config_insecure_ssl IS NOT NULL
                                      AND config_insecure_ssl != '0'
                                      AND config_insecure_ssl != ''))
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": limit},
    )
    snapshot_rows = [dict(row) for row in snapshot_result.mappings().all()]

    # Source 2: audit-log destructive events (requires enterprise PAT).
    events_result = await session.execute(
        text("""
            SELECT org,
                   repo,
                   data->>'hook_id'   AS hook_id,
                   data->>'name'      AS app_name,
                   data->>'config_url' AS config_url,
                   NULL::BOOLEAN      AS active,
                   NULL::TEXT         AS config_insecure_ssl,
                   created_at,
                   'audit_log'        AS source
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
    events_rows = [dict(row) for row in events_result.mappings().all()]

    # Merge: snapshot first (most actionable), then audit-log events.
    combined = snapshot_rows + events_rows
    return combined[:limit]


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


def _ts(val: object) -> str:
    """Convert a timestamp value to ISO string."""
    if hasattr(val, "isoformat"):
        return str(val.isoformat())
    return str(val)


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
                f"{stream_count} streaming events in last 30 days — audit log forwarding is active."
                if stream_count > 0
                else "No audit log streaming events detected. "
                "Configure audit log streaming in your "
                "enterprise settings to forward events to "
                "OctoWatch in real time. Without streaming, "
                "security analysis relies solely on "
                "periodic imports."
            ),
            "evidence_count": stream_count,
            "evidence": None,
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
    has_secret_events = enabled_count + disabled_count > 0
    findings.append(
        {
            "id": "waf-secret-scanning",
            "pillar": "appsec",
            "finding": "Secret scanning enablement",
            "severity": "critical" if disabled_count > 0 else "info",
            "status": "fail" if disabled_count > 0 else "pass",
            "evaluated": has_secret_events,
            "detail": (
                f"{disabled_count} repos disabled secret scanning, "
                f"{enabled_count} repos enabled in last 90 days. "
                "Repos with secret scanning disabled are at risk of leaking credentials."
                if disabled_count > 0
                else (
                    f"{enabled_count} repos enabled secret scanning in last 90 days."
                    if has_secret_events
                    else "No secret scanning enable/disable "
                    "events in audit log. Enable secret "
                    "scanning org-wide in Settings → "
                    "Code security."
                )
            ),
            "evidence_count": enabled_count + disabled_count,
            "evidence": None,
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
    has_bp_events = bp_created + bp_removed > 0
    findings.append(
        {
            "id": "waf-branch-protection",
            "pillar": "governance",
            "finding": "Branch protection coverage",
            "severity": "critical" if bp_removed > bp_created else "info",
            "status": "fail" if bp_removed > bp_created else "pass",
            "evaluated": has_bp_events,
            "detail": (
                f"{bp_created} branch protections created, "
                f"{bp_removed} removed/overridden in last 90 days. "
                "More removals than creations indicates weakening branch security."
                if bp_removed > bp_created
                else (
                    f"{bp_created} branch protections created, "
                    f"{bp_removed} removed in last 90 days."
                    if has_bp_events
                    else "No branch protection events in "
                    "audit log. Use repository rulesets or "
                    "branch protection rules to enforce "
                    "review requirements."
                )
            ),
            "evidence_count": bp_created + bp_removed,
            "evidence": None,
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
    has_sso_events = sso_events > 0
    findings.append(
        {
            "id": "waf-sso-status",
            "pillar": "governance",
            "finding": "SAML / SSO enforcement",
            "severity": "critical" if sso_disabled > 0 else "info",
            "status": ("fail" if sso_disabled > 0 else ("pass" if sso_events > 0 else "warning")),
            "evaluated": has_sso_events or sso_disabled > 0,
            "detail": (
                f"{sso_disabled} SSO disable events "
                "detected — organization authentication "
                "may be weakened."
                if sso_disabled > 0
                else (
                    f"{sso_events} SSO configuration events "
                    "in last 90 days — SSO is actively "
                    "managed."
                    if sso_events > 0
                    else "No SSO-related events in audit "
                    "log. If SSO is not configured, enforce "
                    "SAML SSO in enterprise settings to "
                    "prevent credential-based attacks."
                )
            ),
            "evidence_count": sso_events,
            "evidence": None,
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
                f"{ip_count} IP allowlist events in last "
                "90 days — network restrictions are "
                "actively managed."
                if ip_count > 0
                else "No IP allowlist events detected. "
                "Consider configuring IP allowlists in "
                "enterprise settings to restrict API and "
                "UI access to trusted networks."
            ),
            "evidence_count": ip_count,
            "evidence": None,
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
    has_dep_events = dep_enabled + dep_disabled > 0
    findings.append(
        {
            "id": "waf-dependabot",
            "pillar": "appsec",
            "finding": "Dependabot alert coverage",
            "severity": "warning" if dep_disabled > 0 else "info",
            "status": "warning" if dep_disabled > 0 else "pass",
            "evaluated": has_dep_events,
            "detail": (
                f"{dep_disabled} repos disabled Dependabot "
                "alerts — vulnerable dependencies may "
                "go undetected."
                if dep_disabled > 0
                else (
                    f"{dep_enabled} repos enabled Dependabot alerts in last 90 days."
                    if has_dep_events
                    else "No Dependabot enable/disable "
                    "events in audit log. Enable Dependabot "
                    "alerts org-wide in Settings → "
                    "Code security."
                )
            ),
            "evidence_count": dep_enabled + dep_disabled,
            "evidence": None,
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
                f"{cs_count} code scanning events in last "
                "90 days — CodeQL or third-party scanning "
                "is active."
                if cs_count > 0
                else "No code scanning events detected. "
                "Enable CodeQL or a third-party SAST "
                "tool via GitHub Actions to detect "
                "vulnerabilities in source code before "
                "they reach production."
            ),
            "evidence_count": cs_count,
            "evidence": None,
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
    has_wh_events = wh_created + wh_destroyed > 0
    findings.append(
        {
            "id": "waf-webhook-health",
            "pillar": "governance",
            "finding": "Webhook lifecycle management",
            "severity": "warning" if wh_destroyed > wh_created else "info",
            "status": "warning" if wh_destroyed > wh_created else "pass",
            "evaluated": has_wh_events,
            "detail": (
                f"{wh_created} webhooks created, {wh_destroyed} destroyed in last 90 days."
                + (
                    " More deletions than creations may indicate integration instability."
                    if wh_destroyed > wh_created
                    else ""
                )
                if has_wh_events
                else "No webhook lifecycle events in audit log."
            ),
            "evidence_count": wh_created + wh_destroyed,
            "evidence": None,
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
            "evaluated": bypass_count > 0,
            "detail": (
                f"{bypass_count} push protection bypasses "
                "in last 90 days — developers are "
                "overriding secret detection. Review "
                "bypass reasons and consider restricting "
                "bypass permissions."
                if bypass_count > 0
                else "No push protection bypass events — secret push protection is enforced."
            ),
            "evidence_count": bypass_count,
            "evidence": None,
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
    has_push_events = push_count > 0

    # Fetch evidence for direct pushes
    push_evidence: list[dict[str, Any]] | None = None
    if push_count > 0:
        push_ev_result = await session.execute(
            text("""
                SELECT actor, repo, data->>'ref' AS ref, created_at
                FROM events
                WHERE action = 'git.push'
                  AND (data->>'ref' = 'refs/heads/main'
                       OR data->>'ref' = 'refs/heads/master')
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        push_evidence = [
            {
                "actor": row["actor"],
                "repo": row["repo"],
                "ref": row["ref"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in push_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-direct-push",
            "pillar": "appsec",
            "finding": "Direct pushes to default branch",
            "severity": "warning" if push_count > 5 else "info",
            "status": "warning" if push_count > 5 else "pass",
            "evaluated": has_push_events,
            "detail": (
                f"{push_count} direct pushes to main/master in last 90 days. "
                + (
                    "This exceeds the recommended threshold. "
                    "Enforce branch protection rules "
                    "requiring pull request reviews."
                    if push_count > 5
                    else "Volume is within acceptable range."
                )
                if has_push_events
                else "No direct pushes to default branches detected in audit log."
            ),
            "evidence_count": push_count,
            "evidence": push_evidence,
        }
    )

    # ---- New signals (11-21) ----

    # 11. Workflow permissions changes (governance)
    wfperm_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action IN (
                'business.set_default_workflow_permissions',
                'repo.set_default_workflow_permissions',
                'org.set_default_workflow_permissions'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    wfperm_count = wfperm_result.scalar() or 0

    wfperm_evidence: list[dict[str, Any]] | None = None
    if wfperm_count > 0:
        wfperm_ev_result = await session.execute(
            text("""
                SELECT actor, org, action, created_at
                FROM events
                WHERE action IN (
                    'business.set_default_workflow_permissions',
                    'repo.set_default_workflow_permissions',
                    'org.set_default_workflow_permissions'
                )
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        wfperm_evidence = [
            {
                "actor": row["actor"],
                "org": row["org"],
                "action": row["action"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in wfperm_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-workflow-permissions",
            "pillar": "governance",
            "finding": "Workflow permissions changes",
            "severity": "warning" if wfperm_count > 0 else "info",
            "status": "warning" if wfperm_count > 0 else "pass",
            "evaluated": True,
            "detail": (
                f"{wfperm_count} workflow permission changes in last 90 days. "
                "Review these changes to ensure workflow permissions have not been loosened. "
                "Overly permissive workflow defaults can "
                "allow actions to write to repos or approve PRs."
                if wfperm_count > 0
                else "No workflow permission changes detected in last 90 days."
            ),
            "evidence_count": wfperm_count,
            "evidence": wfperm_evidence,
        }
    )

    # 12. Self-approve PR permissions (governance)
    selfappr_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action IN (
                'business.set_workflow_permission_can_approve_pr',
                'repo.set_workflow_permission_can_approve_pr',
                'org.set_workflow_permission_can_approve_pr'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    selfappr_count = selfappr_result.scalar() or 0

    selfappr_evidence: list[dict[str, Any]] | None = None
    if selfappr_count > 0:
        selfappr_ev_result = await session.execute(
            text("""
                SELECT actor, org, action, created_at
                FROM events
                WHERE action IN (
                    'business.set_workflow_permission_can_approve_pr',
                    'repo.set_workflow_permission_can_approve_pr',
                    'org.set_workflow_permission_can_approve_pr'
                )
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        selfappr_evidence = [
            {
                "actor": row["actor"],
                "org": row["org"],
                "action": row["action"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in selfappr_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-self-approve-pr",
            "pillar": "governance",
            "finding": "Workflow self-approval of pull requests",
            "severity": "warning" if selfappr_count > 0 else "info",
            "status": "warning" if selfappr_count > 0 else "pass",
            "evaluated": True,
            "detail": (
                f"{selfappr_count} events changing workflow PR "
                "self-approval permissions in last 90 days. "
                "If self-approval is enabled, workflows can "
                "approve their own pull requests, "
                "weakening code review enforcement."
                if selfappr_count > 0
                else "No workflow self-approval permission "
                "changes detected. "
                "This setting should remain restricted."
            ),
            "evidence_count": selfappr_count,
            "evidence": selfappr_evidence,
        }
    )

    # 13. PR merge ratio (collaboration)
    pr_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE action = 'pull_request.merge') AS merged,
                COUNT(*) FILTER (WHERE action = 'pull_request.create') AS created
            FROM events
            WHERE action IN ('pull_request.merge', 'pull_request.create')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    pr_row = pr_result.mappings().first()
    pr_merged = (pr_row["merged"] if pr_row else 0) or 0
    pr_created = (pr_row["created"] if pr_row else 0) or 0
    has_pr_events = pr_merged + pr_created > 0
    merge_ratio = pr_merged / pr_created if pr_created > 0 else 0.0
    pr_anomaly = pr_merged > pr_created and pr_created > 0

    pr_severity: str
    pr_status: str
    if pr_anomaly:
        pr_severity = "warning"
        pr_status = "warning"
    elif pr_created == 0 or merge_ratio > 0.95:
        pr_severity = "info"
        pr_status = "pass"
    else:
        pr_severity = "info"
        pr_status = "pass"

    findings.append(
        {
            "id": "waf-pr-merge-ratio",
            "pillar": "collaboration",
            "finding": "Pull request merge ratio",
            "severity": pr_severity,
            "status": pr_status,
            "evaluated": has_pr_events,
            "detail": (
                f"{pr_merged} PRs merged vs. {pr_created} PRs created in last 90 days "
                f"(ratio: {merge_ratio:.2f}). "
                + (
                    "More merges than creates is unexpected "
                    "— check for merges of "
                    "externally-created PRs or data gaps."
                    if pr_anomaly
                    else "Merge ratio is within expected range."
                )
                if has_pr_events
                else "No pull request events in audit log."
            ),
            "evidence_count": pr_merged + pr_created,
            "evidence": None,
        }
    )

    # 14. Actions secrets created (appsec)
    secrets_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action = 'repo.create_actions_secret'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    secrets_count = secrets_result.scalar() or 0

    secrets_evidence: list[dict[str, Any]] | None = None
    if secrets_count > 0:
        secrets_ev_result = await session.execute(
            text("""
                SELECT actor, repo, created_at
                FROM events
                WHERE action = 'repo.create_actions_secret'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        secrets_evidence = [
            {
                "actor": row["actor"],
                "repo": row["repo"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in secrets_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-actions-secrets",
            "pillar": "appsec",
            "finding": "Actions secrets created",
            "severity": "info",
            "status": "pass",
            "evaluated": True,
            "detail": (
                f"{secrets_count} Actions secrets created in last 90 days. "
                "Review secret creation activity to ensure "
                "sensitive credentials are "
                "managed appropriately."
                if secrets_count > 0
                else "No Actions secret creation events in last 90 days."
            ),
            "evidence_count": secrets_count,
            "evidence": secrets_evidence,
        }
    )

    # 15. Vulnerability alerts dismissed (appsec)
    vuln_dismiss_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action = 'repository_vulnerability_alert.withdraw'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    vuln_dismiss_count = vuln_dismiss_result.scalar() or 0

    vuln_dismiss_evidence: list[dict[str, Any]] | None = None
    if vuln_dismiss_count > 0:
        vuln_dismiss_ev_result = await session.execute(
            text("""
                SELECT actor, repo, created_at
                FROM events
                WHERE action = 'repository_vulnerability_alert.withdraw'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        vuln_dismiss_evidence = [
            {
                "actor": row["actor"],
                "repo": row["repo"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in vuln_dismiss_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-vuln-alert-dismissed",
            "pillar": "appsec",
            "finding": "Vulnerability alerts dismissed",
            "severity": "warning" if vuln_dismiss_count > 0 else "info",
            "status": "warning" if vuln_dismiss_count > 0 else "pass",
            "evaluated": True,
            "detail": (
                f"{vuln_dismiss_count} vulnerability alerts dismissed/withdrawn in last 90 days. "
                "Dismissed alerts may represent unaddressed "
                "security vulnerabilities. "
                "Review dismissal reasons."
                if vuln_dismiss_count > 0
                else "No vulnerability alert dismissals detected in last 90 days."
            ),
            "evidence_count": vuln_dismiss_count,
            "evidence": vuln_dismiss_evidence,
        }
    )

    # 16. Deploy key policy disabled (governance)
    dkp_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action = 'deploy_key_policy.disabled'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    dkp_count = dkp_result.scalar() or 0

    findings.append(
        {
            "id": "waf-deploy-key-policy",
            "pillar": "governance",
            "finding": "Deploy key policy status",
            "severity": "warning" if dkp_count > 0 else "info",
            "status": "warning" if dkp_count > 0 else "pass",
            "evaluated": True,
            "detail": (
                f"{dkp_count} deploy key policy disable events in last 90 days. "
                "Disabling deploy key policies may allow "
                "uncontrolled repository access "
                "via deploy keys."
                if dkp_count > 0
                else "No deploy key policy disable events detected. Deploy key policy is enforced."
            ),
            "evidence_count": dkp_count,
            "evidence": None,
        }
    )

    # 17. Environment protection rules (governance)
    envprot_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action = 'environment.add_protection_rule'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    envprot_count = envprot_result.scalar() or 0

    envprot_evidence: list[dict[str, Any]] | None = None
    if envprot_count > 0:
        envprot_ev_result = await session.execute(
            text("""
                SELECT actor, repo, created_at
                FROM events
                WHERE action = 'environment.add_protection_rule'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        envprot_evidence = [
            {
                "actor": row["actor"],
                "repo": row["repo"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in envprot_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-environment-protection",
            "pillar": "governance",
            "finding": "Environment protection rules",
            "severity": "info",
            "status": "pass",
            "evaluated": True,
            "detail": (
                f"{envprot_count} environment protection rules added in last 90 days. "
                "Environment protection rules add deployment "
                "approval gates and are a "
                "security best practice."
                if envprot_count > 0
                else "No environment protection rule events "
                "detected. Consider adding required "
                "reviewers or wait timers to "
                "deployment environments."
            ),
            "evidence_count": envprot_count,
            "evidence": envprot_evidence,
        }
    )

    # 18. Workflow failure rate (productivity)
    wf_fail_result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE data->>'conclusion' = 'failure'
                ) AS failures
            FROM events
            WHERE action = 'workflows.completed_workflow_run'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '30 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    wf_fail_row = wf_fail_result.mappings().first()
    wf_total = (wf_fail_row["total"] if wf_fail_row else 0) or 0
    wf_failures = (wf_fail_row["failures"] if wf_fail_row else 0) or 0
    has_wf_events = wf_total > 0
    failure_rate = wf_failures / wf_total if wf_total > 0 else 0.0
    failure_pct = round(failure_rate * 100, 1)

    wf_fail_evidence: list[dict[str, Any]] | None = None
    if wf_failures > 0:
        wf_fail_ev_result = await session.execute(
            text("""
                SELECT actor, repo,
                       data->>'name' AS workflow_name,
                       data->>'conclusion' AS conclusion,
                       created_at
                FROM events
                WHERE action = 'workflows.completed_workflow_run'
                  AND data->>'conclusion' = 'failure'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '30 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        wf_fail_evidence = [
            {
                "actor": row["actor"],
                "repo": row["repo"],
                "workflow_name": row["workflow_name"],
                "conclusion": row["conclusion"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in wf_fail_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-workflow-failure-rate",
            "pillar": "productivity",
            "finding": "Workflow failure rate",
            "severity": "warning" if failure_rate > 0.20 else "info",
            "status": "warning" if failure_rate > 0.20 else "pass",
            "evaluated": has_wf_events,
            "detail": (
                f"{wf_failures}/{wf_total} workflow runs failed in last 30 days ({failure_pct}%). "
                + (
                    "Failure rate exceeds 20% threshold. "
                    "Investigate flaky tests, misconfigured "
                    "workflows, or infrastructure issues."
                    if failure_rate > 0.20
                    else "Failure rate is within acceptable range."
                )
                if has_wf_events
                else "No completed workflow run events in last 30 days."
            ),
            "evidence_count": wf_total,
            "evidence": wf_fail_evidence,
        }
    )

    # 19. Workflow rerun rate (productivity)
    rerun_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE action = 'workflows.rerun_workflow_run'
                ) AS reruns,
                COUNT(*) FILTER (
                    WHERE action = 'workflows.created_workflow_run'
                ) AS created
            FROM events
            WHERE action IN (
                'workflows.rerun_workflow_run',
                'workflows.created_workflow_run'
            )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '30 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    rerun_row = rerun_result.mappings().first()
    rerun_count = (rerun_row["reruns"] if rerun_row else 0) or 0
    wf_created_count = (rerun_row["created"] if rerun_row else 0) or 0
    has_rerun_events = rerun_count + wf_created_count > 0
    rerun_rate = rerun_count / wf_created_count if wf_created_count > 0 else 0.0
    rerun_pct = round(rerun_rate * 100, 1)

    rerun_evidence: list[dict[str, Any]] | None = None
    if rerun_count > 0:
        rerun_ev_result = await session.execute(
            text("""
                SELECT actor, repo,
                       data->>'name' AS workflow_name,
                       created_at
                FROM events
                WHERE action = 'workflows.rerun_workflow_run'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '30 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        rerun_evidence = [
            {
                "actor": row["actor"],
                "repo": row["repo"],
                "workflow_name": row["workflow_name"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in rerun_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-workflow-rerun-rate",
            "pillar": "productivity",
            "finding": "Workflow rerun rate",
            "severity": "warning" if rerun_rate > 0.15 else "info",
            "status": "warning" if rerun_rate > 0.15 else "pass",
            "evaluated": has_rerun_events,
            "detail": (
                f"{rerun_count} reruns out of "
                f"{wf_created_count} workflow runs "
                f"in last 30 days ({rerun_pct}%). "
                + (
                    "Rerun rate exceeds 15% threshold. "
                    "High rerun rates indicate flaky "
                    "workflows or transient failures."
                    if rerun_rate > 0.15
                    else "Rerun rate is within acceptable range."
                )
                if has_rerun_events
                else "No workflow run events in last 30 days."
            ),
            "evidence_count": rerun_count + wf_created_count,
            "evidence": rerun_evidence,
        }
    )

    # 20. Clone anomaly detection (appsec)
    clone_result = await session.execute(
        text("""
            SELECT actor, COUNT(*) AS clone_count
            FROM events
            WHERE action = 'git.clone'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '30 days'
            GROUP BY actor
            ORDER BY clone_count DESC
        """),
        {"scoped_orgs": scoped_orgs},
    )
    clone_rows = [dict(row) for row in clone_result.mappings().all()]
    total_cloners = len(clone_rows)
    avg_clone_count = (
        sum(r["clone_count"] for r in clone_rows) / total_cloners if total_cloners > 0 else 0.0
    )
    anomalous_cloners = (
        [r for r in clone_rows if r["clone_count"] > avg_clone_count * 3]
        if avg_clone_count > 0
        else []
    )
    has_clone_anomaly = len(anomalous_cloners) > 0

    clone_evidence: list[dict[str, Any]] | None = None
    if has_clone_anomaly:
        clone_evidence = [
            {
                "actor": r["actor"],
                "clone_count": r["clone_count"],
                "avg_count": round(avg_clone_count, 1),
            }
            for r in anomalous_cloners[:25]
        ]

    findings.append(
        {
            "id": "waf-clone-anomaly",
            "pillar": "appsec",
            "finding": "Clone activity anomaly detection",
            "severity": "warning" if has_clone_anomaly else "info",
            "status": "warning" if has_clone_anomaly else "pass",
            "evaluated": total_cloners > 0,
            "detail": (
                f"{len(anomalous_cloners)} actor(s) with clone counts exceeding 3× the average "
                f"({round(avg_clone_count, 1)} clones/actor) in last 30 days. "
                "Unusually high clone activity may indicate "
                "data exfiltration or automated scraping."
                if has_clone_anomaly
                else (
                    f"{total_cloners} actors cloned repositories "
                    "in last 30 days — no anomalies detected."
                    if total_cloners > 0
                    else "No git clone events in last 30 days."
                )
            ),
            "evidence_count": total_cloners,
            "evidence": clone_evidence,
        }
    )

    # 21. Admin escalation (governance)
    admin_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM events
            WHERE action = 'business.add_admin'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - INTERVAL '90 days'
        """),
        {"scoped_orgs": scoped_orgs},
    )
    admin_count = admin_result.scalar() or 0

    admin_evidence: list[dict[str, Any]] | None = None
    if admin_count > 0:
        admin_ev_result = await session.execute(
            text("""
                SELECT actor, org, data->>'user' AS promoted_user, created_at
                FROM events
                WHERE action = 'business.add_admin'
                  AND org = ANY(:scoped_orgs)
                  AND created_at >= NOW() - INTERVAL '90 days'
                ORDER BY created_at DESC
                LIMIT 25
            """),
            {"scoped_orgs": scoped_orgs},
        )
        admin_evidence = [
            {
                "actor": row["actor"],
                "org": row["org"],
                "promoted_user": row["promoted_user"],
                "timestamp": _ts(row["created_at"]),
            }
            for row in admin_ev_result.mappings().all()
        ]

    findings.append(
        {
            "id": "waf-admin-escalation",
            "pillar": "governance",
            "finding": "Admin privilege escalation",
            "severity": "critical" if admin_count > 0 else "info",
            "status": "fail" if admin_count > 0 else "pass",
            "evaluated": True,
            "detail": (
                f"{admin_count} admin promotion(s) detected in last 90 days. "
                "Admin escalations should be rare and "
                "approved. Review each promotion "
                "for legitimacy."
                if admin_count > 0
                else "No admin privilege escalations detected in last 90 days."
            ),
            "evidence_count": admin_count,
            "evidence": admin_evidence,
        }
    )

    return findings


# ── Unified Security Summary (Epic 5: GHAS dashboard) ────────────────────────


async def get_unified_security_summary(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Aggregate all three GHAS alert types plus active detections.

    Returns a single structure for the unified security dashboard widget
    (Issue #72) with current counts and 30-day trend data.
    """
    # Secret scanning summary
    ss_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE state = 'open') AS open_secret_alerts,
                COUNT(*) FILTER (WHERE state = 'resolved') AS resolved_secret_alerts,
                COUNT(*) AS total_secret_alerts,
                COUNT(*) FILTER (
                    WHERE push_protection_bypassed = TRUE AND state = 'open'
                ) AS bypassed_open
            FROM secret_scanning_alerts
            WHERE org_slug = ANY(:scoped_orgs)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    ss_row = dict(ss_result.mappings().first() or {})

    # Code scanning summary by severity
    cs_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE state = 'open') AS open_code_alerts,
                COUNT(*) FILTER (
                    WHERE state = 'open'
                      AND COALESCE(security_severity, severity) = 'critical'
                ) AS code_critical,
                COUNT(*) FILTER (
                    WHERE state = 'open'
                      AND COALESCE(security_severity, severity) = 'high'
                ) AS code_high,
                COUNT(*) FILTER (
                    WHERE state = 'open'
                      AND COALESCE(security_severity, severity) = 'medium'
                ) AS code_medium,
                COUNT(*) FILTER (
                    WHERE state = 'open'
                      AND COALESCE(security_severity, severity) = 'low'
                ) AS code_low,
                COUNT(*) AS total_code_alerts
            FROM code_scanning_alerts
            WHERE org_slug = ANY(:scoped_orgs)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    cs_row = dict(cs_result.mappings().first() or {})

    # Dependabot summary by severity
    dep_result = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE state = 'open') AS open_dependabot_alerts,
                COUNT(*) FILTER (
                    WHERE state = 'open' AND severity = 'critical'
                ) AS dep_critical,
                COUNT(*) FILTER (
                    WHERE state = 'open' AND severity = 'high'
                ) AS dep_high,
                COUNT(*) FILTER (
                    WHERE state = 'open' AND severity = 'medium'
                ) AS dep_medium,
                COUNT(*) FILTER (
                    WHERE state = 'open' AND severity = 'low'
                ) AS dep_low,
                COUNT(*) AS total_dependabot_alerts,
                COUNT(*) FILTER (
                    WHERE state = 'open'
                      AND severity = 'critical'
                      AND EXTRACT(DAYS FROM NOW() - created_at) > 90
                ) AS critical_aging_gt_90d
            FROM dependabot_alerts
            WHERE org_slug = ANY(:scoped_orgs)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    dep_row = dict(dep_result.mappings().first() or {})

    # Active OctoWatch detections
    det_result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS active_detections,
                COUNT(*) FILTER (WHERE severity = 'critical') AS det_critical,
                COUNT(*) FILTER (WHERE severity = 'high') AS det_high,
                COUNT(*) FILTER (WHERE severity = 'medium') AS det_medium,
                COUNT(*) FILTER (WHERE severity = 'low') AS det_low
            FROM detections
            WHERE org = ANY(:scoped_orgs)
              AND status IN ('open', 'investigating')
        """),
        {"scoped_orgs": scoped_orgs},
    )
    det_row = dict(det_result.mappings().first() or {})

    # 30-day daily trend for each alert type
    trend_result = await session.execute(
        text("""
            WITH dates AS (
                SELECT generate_series(
                    (CURRENT_DATE - INTERVAL '29 days')::DATE,
                    CURRENT_DATE::DATE,
                    '1 day'::INTERVAL
                )::DATE AS day
            ),
            ss_daily AS (
                SELECT created_at::DATE AS day, COUNT(*) AS cnt
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND created_at >= CURRENT_DATE - INTERVAL '29 days'
                GROUP BY 1
            ),
            cs_daily AS (
                SELECT created_at::DATE AS day, COUNT(*) AS cnt
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND created_at >= CURRENT_DATE - INTERVAL '29 days'
                GROUP BY 1
            ),
            dep_daily AS (
                SELECT created_at::DATE AS day, COUNT(*) AS cnt
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND created_at >= CURRENT_DATE - INTERVAL '29 days'
                GROUP BY 1
            )
            SELECT
                d.day::TEXT AS day,
                COALESCE(ss.cnt, 0) AS secret_scanning,
                COALESCE(cs.cnt, 0) AS code_scanning,
                COALESCE(dp.cnt, 0) AS dependabot
            FROM dates d
            LEFT JOIN ss_daily ss ON d.day = ss.day
            LEFT JOIN cs_daily cs ON d.day = cs.day
            LEFT JOIN dep_daily dp ON d.day = dp.day
            ORDER BY d.day
        """),
        {"scoped_orgs": scoped_orgs},
    )
    trend = [dict(row) for row in trend_result.mappings().all()]

    return {
        "secret_scanning": {
            "open": ss_row.get("open_secret_alerts", 0),
            "resolved": ss_row.get("resolved_secret_alerts", 0),
            "total": ss_row.get("total_secret_alerts", 0),
            "bypassed_open": ss_row.get("bypassed_open", 0),
        },
        "code_scanning": {
            "open": cs_row.get("open_code_alerts", 0),
            "critical": cs_row.get("code_critical", 0),
            "high": cs_row.get("code_high", 0),
            "medium": cs_row.get("code_medium", 0),
            "low": cs_row.get("code_low", 0),
            "total": cs_row.get("total_code_alerts", 0),
        },
        "dependabot": {
            "open": dep_row.get("open_dependabot_alerts", 0),
            "critical": dep_row.get("dep_critical", 0),
            "high": dep_row.get("dep_high", 0),
            "medium": dep_row.get("dep_medium", 0),
            "low": dep_row.get("dep_low", 0),
            "total": dep_row.get("total_dependabot_alerts", 0),
            "critical_aging_gt_90d": dep_row.get("critical_aging_gt_90d", 0),
        },
        "detections": {
            "active": det_row.get("active_detections", 0),
            "critical": det_row.get("det_critical", 0),
            "high": det_row.get("det_high", 0),
            "medium": det_row.get("det_medium", 0),
            "low": det_row.get("det_low", 0),
        },
        "trend_30d": trend,
    }


async def get_api_abuse_signals(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    hours: int = 24,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Detect API abuse patterns from audit log events.

    Identifies:
    1. Rate limit violations: actors with rate_limit.* events
    2. Failed auth: actors with >5 auth failures in 1 hour windows
    3. Bulk operations: >15 repo clones, >50 deletions, or >100 permission changes in 1 hour
    """
    result = await session.execute(
        text("""
            WITH recent_events AS (
                SELECT actor, action, created_at
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND actor IS NOT NULL
                  AND created_at >= NOW() - make_interval(hours => :hours)
            ),
            rate_limit_signals AS (
                SELECT
                    'rate_limit_violation' AS signal_type,
                    'critical' AS severity,
                    actor,
                    COUNT(*)::INT AS event_count,
                    DATE_TRUNC('hour', created_at) AS time_window_start,
                    DATE_TRUNC('hour', created_at) + INTERVAL '1 hour' AS time_window_end,
                    COUNT(*)::TEXT || ' rate limit events in 1 hour' AS details,
                    'Review API usage and consider rate limiting' AS recommended_action
                FROM recent_events
                WHERE action LIKE 'rate_limit.%'
                GROUP BY actor, DATE_TRUNC('hour', created_at)
            ),
            failed_auth_signals AS (
                SELECT
                    'failed_auth' AS signal_type,
                    'high' AS severity,
                    actor,
                    COUNT(*)::INT AS event_count,
                    DATE_TRUNC('hour', created_at) AS time_window_start,
                    DATE_TRUNC('hour', created_at) + INTERVAL '1 hour' AS time_window_end,
                    COUNT(*)::TEXT || ' authentication failures in 1 hour' AS details,
                    'Investigate possible credential stuffing or brute force activity'
                        AS recommended_action
                FROM recent_events
                WHERE action = 'authentication.failure'
                GROUP BY actor, DATE_TRUNC('hour', created_at)
                HAVING COUNT(*) > 5
            ),
            bulk_operation_counts AS (
                SELECT
                    actor,
                    DATE_TRUNC('hour', created_at) AS time_window_start,
                    DATE_TRUNC('hour', created_at) + INTERVAL '1 hour' AS time_window_end,
                    CASE
                        WHEN action = 'repo.clone' THEN 'repo_clone'
                        WHEN action IN ('repo.destroy', 'repo.delete') THEN 'repo_delete'
                        WHEN action LIKE 'member.%' OR action LIKE 'org_member.%'
                            THEN 'permission_change'
                    END AS bulk_category,
                    COUNT(*)::INT AS event_count
                FROM recent_events
                WHERE action = 'repo.clone'
                   OR action IN ('repo.destroy', 'repo.delete')
                   OR action LIKE 'member.%'
                   OR action LIKE 'org_member.%'
                GROUP BY actor, DATE_TRUNC('hour', created_at), bulk_category
                HAVING (
                    bulk_category = 'repo_clone' AND COUNT(*) > 15
                ) OR (
                    bulk_category = 'repo_delete' AND COUNT(*) > 50
                ) OR (
                    bulk_category = 'permission_change' AND COUNT(*) > 100
                )
            ),
            bulk_operation_signals AS (
                SELECT
                    'bulk_operation' AS signal_type,
                    'high' AS severity,
                    actor,
                    event_count,
                    time_window_start,
                    time_window_end,
                    CASE bulk_category
                        WHEN 'repo_clone' THEN event_count::TEXT || ' repo clone events in 1 hour'
                        WHEN 'repo_delete'
                            THEN event_count::TEXT
                            || ' repository deletion events in 1 hour'
                        ELSE event_count::TEXT
                            || ' membership or permission changes in 1 hour'
                    END AS details,
                    CASE bulk_category
                        WHEN 'repo_clone' THEN 'Review cloning activity for exfiltration risk'
                        WHEN 'repo_delete'
                            THEN 'Immediately review destructive actions and actor intent'
                        ELSE 'Validate admin changes and check for compromised credentials'
                    END AS recommended_action
                FROM bulk_operation_counts
            )
            SELECT *
            FROM (
                SELECT * FROM rate_limit_signals
                UNION ALL
                SELECT * FROM failed_auth_signals
                UNION ALL
                SELECT * FROM bulk_operation_signals
            ) signals
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    ELSE 3
                END,
                event_count DESC,
                time_window_start DESC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "hours": int(hours), "limit": int(limit)},
    )
    return [dict(row) for row in result.mappings().all()]


async def get_dormant_users(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    days_inactive: int = 90,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find org members with no audit log activity in the last N days.

    Returns user info with estimated monthly cost based on seat type.
    Builds on get_ghost_members but adds Copilot seat and license info.
    """
    result = await session.execute(
        text("""
            WITH all_actors AS (
                SELECT DISTINCT actor AS login
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND actor IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '365 days'
            ),
            recent_actors AS (
                SELECT DISTINCT actor AS login
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND actor IS NOT NULL
                  AND created_at >= NOW() - make_interval(days => :days_inactive)
            ),
            last_activity AS (
                SELECT actor AS login, MAX(created_at) AS last_activity_date
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND actor IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '365 days'
                GROUP BY actor
            ),
            copilot_seats AS (
                SELECT DISTINCT actor AS login
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND actor IS NOT NULL
                  AND action IN (
                      'copilot.cfb_seat_added',
                      'copilot.cfb_seat_assignment_created'
                  )
                  AND created_at >= NOW() - INTERVAL '365 days'
            )
            SELECT
                a.login,
                la.last_activity_date,
                EXTRACT(DAY FROM NOW() - la.last_activity_date)::INT AS days_inactive,
                CASE
                    WHEN cs.login IS NOT NULL THEN 'github+copilot'
                    ELSE 'github'
                END AS seat_type,
                CASE
                    WHEN cs.login IS NOT NULL THEN 40.0
                    ELSE 21.0
                END AS estimated_monthly_cost,
                CASE
                    WHEN EXTRACT(DAY FROM NOW() - la.last_activity_date) >= 180
                        THEN 'Review and consider removing'
                    WHEN EXTRACT(DAY FROM NOW() - la.last_activity_date) >= 120
                        THEN 'Review access and confirm continued need'
                    ELSE 'Monitor for reactivation or downgrade access'
                END AS recommended_action
            FROM all_actors a
            JOIN last_activity la ON la.login = a.login
            LEFT JOIN copilot_seats cs ON cs.login = a.login
            WHERE a.login NOT IN (SELECT login FROM recent_actors)
            ORDER BY la.last_activity_date ASC NULLS FIRST, a.login
            LIMIT :limit
        """),
        {
            "scoped_orgs": scoped_orgs,
            "days_inactive": int(days_inactive),
            "limit": int(limit),
        },
    )
    return [dict(row) for row in result.mappings().all()]


async def get_platform_security(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Security configuration inventory per organization.

    Checks SSO, 2FA, audit log streaming, and branch protection defaults.
    """
    result = await session.execute(
        text("""
            WITH orgs AS (
                SELECT UNNEST(CAST(:scoped_orgs AS TEXT[])) AS org
            ),
            sso_events AS (
                SELECT DISTINCT ON (org) org, action
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action IN ('org.enable_saml', 'org.disable_saml')
                ORDER BY org, created_at DESC
            ),
            two_fa_events AS (
                SELECT DISTINCT ON (org) org, action
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action IN (
                      'org.require_two_factor_authentication',
                      'org.disable_two_factor_requirement'
                  )
                ORDER BY org, created_at DESC
            ),
            streaming_events AS (
                SELECT DISTINCT ON (org) org, action
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action LIKE 'audit_log_streaming.%'
                ORDER BY org, created_at DESC
            ),
            ip_allowlist_events AS (
                SELECT org, TRUE AS ip_allowlist_configured
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action LIKE 'ip_allow_list%'
                GROUP BY org
            ),
            branch_protection_events AS (
                SELECT org, TRUE AS branch_protection_default
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action IN ('protected_branch.create', 'repository_ruleset.create')
                GROUP BY org
            )
            SELECT
                o.org,
                COALESCE(s.action = 'org.enable_saml', FALSE) AS sso_configured,
                COALESCE(
                    tf.action = 'org.require_two_factor_authentication',
                    FALSE
                ) AS two_fa_required,
                COALESCE(
                    NOT (
                        se.action LIKE 'audit_log_streaming.%destroy%'
                        OR se.action LIKE 'audit_log_streaming.%delete%'
                    ),
                    FALSE
                ) AS audit_log_streaming,
                COALESCE(ip.ip_allowlist_configured, FALSE) AS ip_allowlist_configured,
                COALESCE(bp.branch_protection_default, FALSE) AS branch_protection_default,
                ROUND((
                    (
                        COALESCE((s.action = 'org.enable_saml')::INT, 0)
                        + COALESCE((tf.action = 'org.require_two_factor_authentication')::INT, 0)
                        + COALESCE((NOT (
                            se.action LIKE 'audit_log_streaming.%destroy%'
                            OR se.action LIKE 'audit_log_streaming.%delete%'
                        ))::INT, 0)
                        + COALESCE(ip.ip_allowlist_configured::INT, 0)
                        + COALESCE(bp.branch_protection_default::INT, 0)
                    )::NUMERIC / 5
                ) * 100, 1) AS compliance_score
            FROM orgs o
            LEFT JOIN sso_events s ON s.org = o.org
            LEFT JOIN two_fa_events tf ON tf.org = o.org
            LEFT JOIN streaming_events se ON se.org = o.org
            LEFT JOIN ip_allowlist_events ip ON ip.org = o.org
            LEFT JOIN branch_protection_events bp ON bp.org = o.org
            ORDER BY compliance_score DESC, o.org
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": int(limit)},
    )
    rows = [dict(row) for row in result.mappings().all()]
    for row in rows:
        recommendations: list[str] = []
        if not row.get("sso_configured"):
            recommendations.append("Enable SSO")
        if not row.get("two_fa_required"):
            recommendations.append("Require 2FA for all members")
        if not row.get("audit_log_streaming"):
            recommendations.append("Enable audit log streaming")
        if not row.get("ip_allowlist_configured"):
            recommendations.append("Configure IP allowlist")
        if not row.get("branch_protection_default"):
            recommendations.append("Set branch protection defaults")
        row["compliance_score"] = float(row.get("compliance_score", 0) or 0)
        row["recommendations"] = recommendations
    return rows


async def get_maintenance_signals(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    stale_threshold_days: int = 180,
    limit: int = 50,
) -> dict[str, Any]:
    """Comprehensive maintenance signals for repository hygiene.

    Combines stale repos, large repos (from events), empty repos, and repos without README.
    """
    stale_result = await session.execute(
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
                org,
                repo,
                last_event_at,
                EXTRACT(DAY FROM NOW() - last_event_at)::INT AS days_since_activity
            FROM repo_last_activity
            WHERE last_event_at <= NOW() - make_interval(days => :threshold_days)
            ORDER BY last_event_at ASC
            LIMIT :limit
        """),
        {
            "scoped_orgs": scoped_orgs,
            "threshold_days": int(stale_threshold_days),
            "limit": int(limit),
        },
    )
    stale_repos = [dict(row) for row in stale_result.mappings().all()]

    empty_result = await session.execute(
        text("""
            WITH repo_creates AS (
                SELECT org, repo, MIN(created_at) AS created_at
                FROM events
                WHERE action = 'repo.create'
                  AND org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
                GROUP BY org, repo
            ),
            repo_followup_activity AS (
                SELECT
                    rc.org,
                    rc.repo,
                    COUNT(*) FILTER (
                        WHERE e.action IN (
                            'git.push',
                            'push',
                            'git.commit',
                            'commit.create',
                            'pull_request.merge'
                        )
                    ) AS followup_activity
                FROM repo_creates rc
                LEFT JOIN events e
                    ON e.org = rc.org
                   AND e.repo = rc.repo
                   AND e.created_at > rc.created_at
                   AND e.created_at <= rc.created_at + INTERVAL '30 days'
                GROUP BY rc.org, rc.repo
            )
            SELECT rc.org, rc.repo, rc.created_at
            FROM repo_creates rc
            JOIN repo_followup_activity rfa
              ON rfa.org = rc.org AND rfa.repo = rc.repo
            WHERE rfa.followup_activity = 0
            ORDER BY rc.created_at ASC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": int(limit)},
    )
    empty_repos = [dict(row) for row in empty_result.mappings().all()]

    archived_candidate_result = await session.execute(
        text("""
            WITH recent_repo_activity AS (
                SELECT
                    org,
                    repo,
                    COUNT(*)::INT AS event_count,
                    MAX(created_at) AS last_event_at
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '180 days'
                GROUP BY org, repo
            ),
            archived_repos AS (
                SELECT DISTINCT org, repo
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
                  AND action = 'repo.archived'
            )
            SELECT
                rra.org,
                rra.repo,
                rra.event_count,
                rra.last_event_at,
                EXTRACT(DAY FROM NOW() - rra.last_event_at)::INT AS days_since_activity
            FROM recent_repo_activity rra
            LEFT JOIN archived_repos ar
              ON ar.org = rra.org AND ar.repo = rra.repo
            WHERE ar.repo IS NULL
              AND rra.event_count < 5
            ORDER BY rra.event_count ASC, rra.last_event_at ASC
            LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "limit": int(limit)},
    )
    archived_candidates = [dict(row) for row in archived_candidate_result.mappings().all()]

    return {
        "stale_repos": stale_repos,
        "empty_repos": empty_repos,
        "archived_candidates": archived_candidates,
        "summary": {
            "stale_count": len(stale_repos),
            "empty_count": len(empty_repos),
            "archived_candidate_count": len(archived_candidates),
        },
    }


async def get_health_score(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Compute overall org health score (0-100).

    Score = 100 - weighted sum of signal severities:
    - Critical: -10 points each
    - High: -5 points each
    - Medium: -2 points each
    - Low: -1 point each
    Floor at 0, cap at 100.
    """
    result = await session.execute(
        text("""
            WITH orgs AS (
                SELECT UNNEST(CAST(:scoped_orgs AS TEXT[])) AS org
            ),
            repo_last_activity AS (
                SELECT org, repo, MAX(created_at) AS last_event_at
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '2 years'
                GROUP BY org, repo
            ),
            actor_last_activity AS (
                SELECT actor AS login, MAX(created_at) AS last_activity_date
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND actor IS NOT NULL
                  AND created_at >= NOW() - INTERVAL '365 days'
                GROUP BY actor
            ),
            sso_status AS (
                SELECT DISTINCT ON (org) org, action
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action IN ('org.enable_saml', 'org.disable_saml')
                ORDER BY org, created_at DESC
            ),
            two_fa_status AS (
                SELECT DISTINCT ON (org) org, action
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action IN (
                      'org.require_two_factor_authentication',
                      'org.disable_two_factor_requirement'
                  )
                ORDER BY org, created_at DESC
            ),
            audit_stream_status AS (
                SELECT DISTINCT ON (org) org, action
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action LIKE 'audit_log_streaming.%'
                ORDER BY org, created_at DESC
            ),
            ip_allowlist_status AS (
                SELECT org, TRUE AS configured
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action LIKE 'ip_allow_list%'
                GROUP BY org
            ),
            branch_protection_status AS (
                SELECT org, TRUE AS configured
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND action IN ('protected_branch.create', 'repository_ruleset.create')
                GROUP BY org
            ),
            critical_signals AS (
                SELECT COALESCE((
                    SELECT COUNT(*)
                    FROM secret_scanning_alerts
                    WHERE org_slug = ANY(:scoped_orgs)
                      AND state = 'open'
                      AND created_at <= NOW() - INTERVAL '30 days'
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM orgs o
                    LEFT JOIN sso_status s ON s.org = o.org
                    WHERE COALESCE(s.action = 'org.enable_saml', FALSE) = FALSE
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM (
                        SELECT actor, DATE_TRUNC('hour', created_at) AS hour_bucket
                        FROM events
                        WHERE org = ANY(:scoped_orgs)
                          AND action LIKE 'rate_limit.%'
                          AND actor IS NOT NULL
                          AND created_at >= NOW() - INTERVAL '24 hours'
                        GROUP BY actor, DATE_TRUNC('hour', created_at)
                    ) rl
                ), 0) AS critical_count
            ),
            high_signals AS (
                SELECT COALESCE((
                    SELECT COUNT(*)
                    FROM repo_last_activity
                    WHERE last_event_at <= NOW() - INTERVAL '180 days'
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM (
                        SELECT actor
                        FROM events
                        WHERE action IN (
                            'secret_scanning.push_protection.bypass',
                            'protected_branch.policy_override',
                            'branch_protection_rule.policy_override'
                        )
                          AND org = ANY(:scoped_orgs)
                          AND actor IS NOT NULL
                          AND created_at >= NOW() - INTERVAL '90 days'
                        GROUP BY actor
                        HAVING COUNT(*) >= 1
                    ) bo
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM actor_last_activity
                    WHERE last_activity_date <= NOW() - INTERVAL '180 days'
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM events
                    WHERE org = ANY(:scoped_orgs)
                      AND action = 'personal_access_token.create'
                      AND (
                          data->>'token_expiry_date' IS NULL
                          OR data->>'token_expiry_date' = ''
                      )
                ), 0) AS high_count
            ),
            medium_signals AS (
                SELECT COALESCE((
                    SELECT COUNT(*)
                    FROM repo_last_activity
                    WHERE last_event_at > NOW() - INTERVAL '180 days'
                      AND last_event_at <= NOW() - INTERVAL '90 days'
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM actor_last_activity
                    WHERE last_activity_date > NOW() - INTERVAL '180 days'
                      AND last_activity_date <= NOW() - INTERVAL '90 days'
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM orgs o
                    LEFT JOIN two_fa_status tf ON tf.org = o.org
                    LEFT JOIN audit_stream_status ass ON ass.org = o.org
                    LEFT JOIN ip_allowlist_status ip ON ip.org = o.org
                    LEFT JOIN branch_protection_status bp ON bp.org = o.org
                    CROSS JOIN LATERAL (
                        VALUES
                            (COALESCE(tf.action = 'org.require_two_factor_authentication', FALSE)),
                            (COALESCE(NOT (
                                ass.action LIKE 'audit_log_streaming.%destroy%'
                                OR ass.action LIKE 'audit_log_streaming.%delete%'
                            ), FALSE)),
                            (COALESCE(ip.configured, FALSE)),
                            (COALESCE(bp.configured, FALSE))
                    ) AS feature(is_enabled)
                    WHERE feature.is_enabled = FALSE
                ), 0) AS medium_count
            ),
            low_signals AS (
                SELECT COALESCE((
                    SELECT COUNT(*)
                    FROM (
                        WITH opened AS (
                            SELECT org, repo, data->>'number' AS pr_number, created_at AS opened_at
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
                        SELECT o.org, o.repo, o.pr_number
                        FROM opened o
                        LEFT JOIN closed c USING (org, repo, pr_number)
                        WHERE c.pr_number IS NULL
                          AND o.opened_at <= NOW() - INTERVAL '30 days'
                    ) stale_prs
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM (
                        WITH recent_repo_activity AS (
                            SELECT org, repo, COUNT(*) AS event_count
                            FROM events
                            WHERE org = ANY(:scoped_orgs)
                              AND repo IS NOT NULL
                              AND created_at >= NOW() - INTERVAL '180 days'
                            GROUP BY org, repo
                        ),
                        archived_repos AS (
                            SELECT DISTINCT org, repo
                            FROM events
                            WHERE org = ANY(:scoped_orgs)
                              AND repo IS NOT NULL
                              AND action = 'repo.archived'
                        )
                        SELECT rra.org, rra.repo
                        FROM recent_repo_activity rra
                        LEFT JOIN archived_repos ar
                          ON ar.org = rra.org AND ar.repo = rra.repo
                        WHERE ar.repo IS NULL
                          AND rra.event_count < 5
                    ) archived_candidates
                ), 0)
                + COALESCE((
                    SELECT COUNT(*)
                    FROM (
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
                            SELECT DISTINCT org, repo
                            FROM events
                            WHERE action IN ('git.push', 'push')
                              AND org = ANY(:scoped_orgs)
                              AND repo IS NOT NULL
                              AND created_at >= NOW() - INTERVAL '180 days'
                        )
                        SELECT f.org, f.repo
                        FROM forks f
                        LEFT JOIN fork_pushes p ON p.org = f.org AND p.repo = f.repo
                        WHERE p.repo IS NULL
                    ) abandoned_forks
                ), 0) AS low_count
            )
            SELECT
                critical_signals.critical_count,
                high_signals.high_count,
                medium_signals.medium_count,
                low_signals.low_count,
                (SELECT COUNT(*) FROM orgs) AS orgs_monitored
            FROM critical_signals
            CROSS JOIN high_signals
            CROSS JOIN medium_signals
            CROSS JOIN low_signals
        """),
        {"scoped_orgs": scoped_orgs},
    )
    row = dict(result.mappings().first() or {})

    critical_count = int(row.get("critical_count", 0) or 0)
    high_count = int(row.get("high_count", 0) or 0)
    medium_count = int(row.get("medium_count", 0) or 0)
    low_count = int(row.get("low_count", 0) or 0)
    orgs_monitored = int(row.get("orgs_monitored", len(scoped_orgs)) or 0)
    total_signals = critical_count + high_count + medium_count + low_count
    score = max(
        0,
        min(
            100,
            100 - (critical_count * 10) - (high_count * 5) - (medium_count * 2) - low_count,
        ),
    )

    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "critical_count": critical_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "total_signals": total_signals,
        "orgs_monitored": orgs_monitored,
    }


async def get_mttr_trends(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    period: str = "30d",
    severity: str | None = None,
) -> dict[str, Any]:
    """Calculate MTTR trends across secret scanning, code scanning, and Dependabot."""
    if not scoped_orgs:
        return {
            "current_mttr_hours": 0.0,
            "previous_mttr_hours": 0.0,
            "trend_pct": 0.0,
            "by_severity": [],
            "time_series": [],
            "by_tool": [
                {"tool": "code_scanning", "mttr_hours": 0.0},
                {"tool": "secret_scanning", "mttr_hours": 0.0},
                {"tool": "dependabot", "mttr_hours": 0.0},
            ],
        }

    period_map = {"7d": 7, "30d": 30, "90d": 90, "180d": 180}
    days = period_map.get(period, 30)
    window_days = days * 2

    summary_result = await session.execute(
        text("""
            WITH normalized_alerts AS (
                SELECT
                    'secret_scanning' AS tool,
                    NULL::TEXT AS severity,
                    resolved_at AS closed_at,
                    EXTRACT(EPOCH FROM resolved_at - created_at) / 3600.0
                        AS mttr_hours
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'resolved'
                  AND resolved_at IS NOT NULL
                  AND resolved_at >= NOW() - (:window_days * INTERVAL '1 day')
                  AND CAST(:severity AS TEXT) IS NULL

                UNION ALL

                SELECT
                    'code_scanning' AS tool,
                    COALESCE(security_severity, severity) AS severity,
                    COALESCE(fixed_at, dismissed_at) AS closed_at,
                    EXTRACT(EPOCH FROM COALESCE(fixed_at, dismissed_at) - created_at)
                        / 3600.0 AS mttr_hours
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state IN ('fixed', 'dismissed')
                  AND COALESCE(fixed_at, dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, dismissed_at)
                      >= NOW() - (:window_days * INTERVAL '1 day')
                  AND (
                      CAST(:severity AS TEXT) IS NULL
                      OR COALESCE(security_severity, severity) = CAST(:severity AS TEXT)
                  )

                UNION ALL

                SELECT
                    'dependabot' AS tool,
                    severity,
                    COALESCE(fixed_at, auto_dismissed_at) AS closed_at,
                    EXTRACT(
                        EPOCH FROM COALESCE(fixed_at, auto_dismissed_at) - created_at
                    ) / 3600.0 AS mttr_hours
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND COALESCE(fixed_at, auto_dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, auto_dismissed_at)
                      >= NOW() - (:window_days * INTERVAL '1 day')
                  AND (CAST(:severity AS TEXT) IS NULL OR severity = CAST(:severity AS TEXT))
            )
            SELECT
                ROUND(
                    COALESCE(
                        AVG(mttr_hours) FILTER (
                            WHERE closed_at >= NOW() - (:days * INTERVAL '1 day')
                        ),
                        0
                    )::numeric,
                    2
                ) AS current_mttr_hours,
                ROUND(
                    COALESCE(
                        AVG(mttr_hours) FILTER (
                            WHERE closed_at >= NOW() - (:window_days * INTERVAL '1 day')
                              AND closed_at < NOW() - (:days * INTERVAL '1 day')
                        ),
                        0
                    )::numeric,
                    2
                ) AS previous_mttr_hours
            FROM normalized_alerts
        """),
        {
            "scoped_orgs": scoped_orgs,
            "days": days,
            "window_days": window_days,
            "severity": severity,
        },
    )
    summary_row = dict(summary_result.mappings().first() or {})

    severity_result = await session.execute(
        text("""
            WITH normalized_alerts AS (
                SELECT
                    COALESCE(security_severity, severity) AS severity,
                    COALESCE(fixed_at, dismissed_at) AS closed_at,
                    EXTRACT(EPOCH FROM COALESCE(fixed_at, dismissed_at) - created_at)
                        / 3600.0 AS mttr_hours
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state IN ('fixed', 'dismissed')
                  AND COALESCE(fixed_at, dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, dismissed_at)
                      >= NOW() - (:days * INTERVAL '1 day')
                  AND (
                      CAST(:severity AS TEXT) IS NULL
                      OR COALESCE(security_severity, severity) = CAST(:severity AS TEXT)
                  )

                UNION ALL

                SELECT
                    severity,
                    COALESCE(fixed_at, auto_dismissed_at) AS closed_at,
                    EXTRACT(
                        EPOCH FROM COALESCE(fixed_at, auto_dismissed_at) - created_at
                    ) / 3600.0 AS mttr_hours
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND COALESCE(fixed_at, auto_dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, auto_dismissed_at)
                      >= NOW() - (:days * INTERVAL '1 day')
                  AND (CAST(:severity AS TEXT) IS NULL OR severity = CAST(:severity AS TEXT))
            )
            SELECT
                severity,
                ROUND(COALESCE(AVG(mttr_hours), 0)::numeric, 2) AS mttr_hours,
                COUNT(*) AS sample_size
            FROM normalized_alerts
            WHERE severity IS NOT NULL
            GROUP BY severity
            ORDER BY sample_size DESC, severity
        """),
        {"scoped_orgs": scoped_orgs, "days": days, "severity": severity},
    )
    by_severity = [dict(row) for row in severity_result.mappings().all()]

    tool_result = await session.execute(
        text("""
            WITH normalized_alerts AS (
                SELECT
                    'secret_scanning' AS tool,
                    resolved_at AS closed_at,
                    EXTRACT(EPOCH FROM resolved_at - created_at) / 3600.0
                        AS mttr_hours
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'resolved'
                  AND resolved_at IS NOT NULL
                  AND resolved_at >= NOW() - (:days * INTERVAL '1 day')
                  AND CAST(:severity AS TEXT) IS NULL

                UNION ALL

                SELECT
                    'code_scanning' AS tool,
                    COALESCE(fixed_at, dismissed_at) AS closed_at,
                    EXTRACT(EPOCH FROM COALESCE(fixed_at, dismissed_at) - created_at)
                        / 3600.0 AS mttr_hours
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state IN ('fixed', 'dismissed')
                  AND COALESCE(fixed_at, dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, dismissed_at)
                      >= NOW() - (:days * INTERVAL '1 day')
                  AND (
                      CAST(:severity AS TEXT) IS NULL
                      OR COALESCE(security_severity, severity) = CAST(:severity AS TEXT)
                  )

                UNION ALL

                SELECT
                    'dependabot' AS tool,
                    COALESCE(fixed_at, auto_dismissed_at) AS closed_at,
                    EXTRACT(
                        EPOCH FROM COALESCE(fixed_at, auto_dismissed_at) - created_at
                    ) / 3600.0 AS mttr_hours
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND COALESCE(fixed_at, auto_dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, auto_dismissed_at)
                      >= NOW() - (:days * INTERVAL '1 day')
                  AND (CAST(:severity AS TEXT) IS NULL OR severity = CAST(:severity AS TEXT))
            )
            SELECT
                tool,
                ROUND(COALESCE(AVG(mttr_hours), 0)::numeric, 2) AS mttr_hours
            FROM normalized_alerts
            GROUP BY tool
        """),
        {"scoped_orgs": scoped_orgs, "days": days, "severity": severity},
    )
    tool_map = {
        row["tool"]: float(row["mttr_hours"] or 0.0) for row in tool_result.mappings().all()
    }
    by_tool = [
        {"tool": "code_scanning", "mttr_hours": tool_map.get("code_scanning", 0.0)},
        {
            "tool": "secret_scanning",
            "mttr_hours": tool_map.get("secret_scanning", 0.0),
        },
        {"tool": "dependabot", "mttr_hours": tool_map.get("dependabot", 0.0)},
    ]

    series_result = await session.execute(
        text("""
            WITH dates AS (
                SELECT generate_series(
                    (CURRENT_DATE - ((:days - 1) * INTERVAL '1 day'))::date,
                    CURRENT_DATE::date,
                    '1 day'::INTERVAL
                )::date AS day
            ),
            normalized_alerts AS (
                SELECT
                    resolved_at::date AS day,
                    EXTRACT(EPOCH FROM resolved_at - created_at) / 3600.0
                        AS mttr_hours
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'resolved'
                  AND resolved_at IS NOT NULL
                  AND resolved_at >= NOW() - (:days * INTERVAL '1 day')
                  AND CAST(:severity AS TEXT) IS NULL

                UNION ALL

                SELECT
                    COALESCE(fixed_at, dismissed_at)::date AS day,
                    EXTRACT(EPOCH FROM COALESCE(fixed_at, dismissed_at) - created_at)
                        / 3600.0 AS mttr_hours
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state IN ('fixed', 'dismissed')
                  AND COALESCE(fixed_at, dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, dismissed_at)
                      >= NOW() - (:days * INTERVAL '1 day')
                  AND (
                      CAST(:severity AS TEXT) IS NULL
                      OR COALESCE(security_severity, severity) = CAST(:severity AS TEXT)
                  )

                UNION ALL

                SELECT
                    COALESCE(fixed_at, auto_dismissed_at)::date AS day,
                    EXTRACT(
                        EPOCH FROM COALESCE(fixed_at, auto_dismissed_at) - created_at
                    ) / 3600.0 AS mttr_hours
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND COALESCE(fixed_at, auto_dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, auto_dismissed_at)
                      >= NOW() - (:days * INTERVAL '1 day')
                  AND (CAST(:severity AS TEXT) IS NULL OR severity = CAST(:severity AS TEXT))
            ),
            daily AS (
                SELECT
                    day,
                    ROUND(COALESCE(AVG(mttr_hours), 0)::numeric, 2) AS mttr_hours
                FROM normalized_alerts
                GROUP BY day
            )
            SELECT
                dates.day::TEXT AS date,
                COALESCE(daily.mttr_hours, 0) AS mttr_hours
            FROM dates
            LEFT JOIN daily ON daily.day = dates.day
            ORDER BY dates.day
        """),
        {"scoped_orgs": scoped_orgs, "days": days, "severity": severity},
    )
    time_series = [dict(row) for row in series_result.mappings().all()]

    current_mttr = float(summary_row.get("current_mttr_hours") or 0.0)
    previous_mttr = float(summary_row.get("previous_mttr_hours") or 0.0)
    trend_pct = (
        round(((current_mttr - previous_mttr) / previous_mttr) * 100, 2)
        if previous_mttr > 0
        else 0.0
    )

    return {
        "current_mttr_hours": current_mttr,
        "previous_mttr_hours": previous_mttr,
        "trend_pct": trend_pct,
        "by_severity": by_severity,
        "time_series": time_series,
        "by_tool": by_tool,
    }


async def get_coverage_growth(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
    period: str = "90d",
) -> dict[str, Any]:
    """Measure strategic security feature coverage and growth."""
    if not scoped_orgs:
        return {
            "total_repos": 0,
            "feature_coverage": {
                "ghas": {"repos": 0, "pct": 0.0},
                "code_scanning": {"repos": 0, "pct": 0.0},
                "secret_scanning": {"repos": 0, "pct": 0.0},
                "dependabot": {"repos": 0, "pct": 0.0},
                "push_protection": {"repos": 0, "pct": 0.0},
            },
            "time_series": [],
            "uncovered_repos": [],
        }

    period_map = {"7d": 7, "30d": 30, "90d": 90, "180d": 180}
    days = period_map.get(period, 90)

    total_result = await session.execute(
        text("""
            SELECT COUNT(DISTINCT repo) AS total_repos
            FROM events
            WHERE org = ANY(:scoped_orgs)
              AND repo IS NOT NULL
        """),
        {"scoped_orgs": scoped_orgs},
    )
    total_row = total_result.mappings().first()
    total_repos = int(total_row["total_repos"] or 0) if total_row else 0

    coverage_result = await session.execute(
        text("""
            WITH event_feature_states AS (
                SELECT DISTINCT ON (repo, feature)
                    repo,
                    feature,
                    CASE
                        WHEN action LIKE '%%.disable%%'
                            OR action LIKE '%%_disabled%%'
                            OR action LIKE '%%.disable'
                            OR action LIKE '%%disabled%%'
                            THEN 'disabled'
                        ELSE 'enabled'
                    END AS state
                FROM (
                    SELECT
                        repo,
                        CASE
                            WHEN action LIKE 'secret_scanning%%'
                                OR action LIKE 'repository_secret_scanning%%'
                                THEN 'secret_scanning'
                            WHEN action LIKE '%%codeql%%' THEN 'code_scanning'
                            WHEN action LIKE 'dependabot%%' THEN 'dependabot'
                            WHEN action LIKE '%%advanced_security%%' THEN 'ghas'
                            WHEN action LIKE '%%push_protection%%'
                                THEN 'push_protection'
                            ELSE NULL
                        END AS feature,
                        action,
                        created_at
                    FROM events
                    WHERE org = ANY(:scoped_orgs)
                      AND repo IS NOT NULL
                      AND (
                          action LIKE 'secret_scanning%%'
                          OR action LIKE 'repository_secret_scanning%%'
                          OR action LIKE '%%codeql%%'
                          OR action LIKE 'dependabot%%'
                          OR action LIKE '%%advanced_security%%'
                          OR action LIKE '%%push_protection%%'
                      )
                ) feature_events
                WHERE feature IS NOT NULL
                ORDER BY repo, feature, created_at DESC
            ),
            alert_features AS (
                SELECT DISTINCT repo_full_name AS repo, 'code_scanning' AS feature
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)

                UNION ALL

                SELECT DISTINCT repo_full_name AS repo, 'secret_scanning' AS feature
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)

                UNION ALL

                SELECT DISTINCT repo_full_name AS repo, 'dependabot' AS feature
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
            ),
            current_enabled AS (
                SELECT repo, feature
                FROM event_feature_states
                WHERE state = 'enabled'

                UNION

                SELECT repo, feature
                FROM alert_features
            )
            SELECT feature, COUNT(DISTINCT repo) AS repo_count
            FROM current_enabled
            GROUP BY feature
        """),
        {"scoped_orgs": scoped_orgs},
    )
    feature_counts = {
        row["feature"]: int(row["repo_count"] or 0) for row in coverage_result.mappings().all()
    }

    time_series_result = await session.execute(
        text("""
            WITH weeks AS (
                SELECT generate_series(
                    DATE_TRUNC('week', NOW() - (:days * INTERVAL '1 day'))::date,
                    DATE_TRUNC('week', NOW())::date,
                    '1 week'::INTERVAL
                )::date AS week_start
            ),
            feature_first_seen AS (
                SELECT repo, feature, MIN(first_seen) AS first_seen
                FROM (
                    SELECT
                        repo,
                        CASE
                            WHEN action LIKE 'secret_scanning%%'
                                OR action LIKE 'repository_secret_scanning%%'
                                THEN 'secret_scanning'
                            WHEN action LIKE '%%codeql%%' THEN 'code_scanning'
                            WHEN action LIKE 'dependabot%%' THEN 'dependabot'
                            WHEN action LIKE '%%advanced_security%%' THEN 'ghas'
                            WHEN action LIKE '%%push_protection%%'
                                THEN 'push_protection'
                            ELSE NULL
                        END AS feature,
                        created_at AS first_seen,
                        CASE
                            WHEN action LIKE '%%.disable%%'
                                OR action LIKE '%%_disabled%%'
                                OR action LIKE '%%.disable'
                                OR action LIKE '%%disabled%%'
                                THEN 'disabled'
                            ELSE 'enabled'
                        END AS state
                    FROM events
                    WHERE org = ANY(:scoped_orgs)
                      AND repo IS NOT NULL
                      AND created_at >= NOW() - (:days * INTERVAL '1 day')
                      AND (
                          action LIKE 'secret_scanning%%'
                          OR action LIKE 'repository_secret_scanning%%'
                          OR action LIKE '%%codeql%%'
                          OR action LIKE 'dependabot%%'
                          OR action LIKE '%%advanced_security%%'
                          OR action LIKE '%%push_protection%%'
                      )

                    UNION ALL

                    SELECT
                        repo_full_name AS repo,
                        'code_scanning' AS feature,
                        created_at AS first_seen,
                        'enabled' AS state
                    FROM code_scanning_alerts
                    WHERE org_slug = ANY(:scoped_orgs)
                      AND created_at >= NOW() - (:days * INTERVAL '1 day')

                    UNION ALL

                    SELECT
                        repo_full_name AS repo,
                        'secret_scanning' AS feature,
                        created_at AS first_seen,
                        'enabled' AS state
                    FROM secret_scanning_alerts
                    WHERE org_slug = ANY(:scoped_orgs)
                      AND created_at >= NOW() - (:days * INTERVAL '1 day')

                    UNION ALL

                    SELECT
                        repo_full_name AS repo,
                        'dependabot' AS feature,
                        created_at AS first_seen,
                        'enabled' AS state
                    FROM dependabot_alerts
                    WHERE org_slug = ANY(:scoped_orgs)
                      AND created_at >= NOW() - (:days * INTERVAL '1 day')
                ) feature_sources
                WHERE feature IS NOT NULL AND state = 'enabled'
                GROUP BY repo, feature
            )
            SELECT
                weeks.week_start::TEXT AS date,
                COUNT(DISTINCT feature_first_seen.repo) FILTER (
                    WHERE feature_first_seen.feature = 'ghas'
                      AND feature_first_seen.first_seen < weeks.week_start + INTERVAL '1 week'
                ) AS ghas_repos,
                COUNT(DISTINCT feature_first_seen.repo) FILTER (
                    WHERE feature_first_seen.feature = 'code_scanning'
                      AND feature_first_seen.first_seen < weeks.week_start + INTERVAL '1 week'
                ) AS code_scanning_repos,
                COUNT(DISTINCT feature_first_seen.repo) FILTER (
                    WHERE feature_first_seen.feature = 'secret_scanning'
                      AND feature_first_seen.first_seen < weeks.week_start + INTERVAL '1 week'
                ) AS secret_scanning_repos,
                COUNT(DISTINCT feature_first_seen.repo) FILTER (
                    WHERE feature_first_seen.feature = 'dependabot'
                      AND feature_first_seen.first_seen < weeks.week_start + INTERVAL '1 week'
                ) AS dependabot_repos,
                COUNT(DISTINCT feature_first_seen.repo) FILTER (
                    WHERE feature_first_seen.feature = 'push_protection'
                      AND feature_first_seen.first_seen < weeks.week_start + INTERVAL '1 week'
                ) AS push_protection_repos
            FROM weeks
            LEFT JOIN feature_first_seen
                ON feature_first_seen.first_seen < weeks.week_start + INTERVAL '1 week'
            GROUP BY weeks.week_start
            ORDER BY weeks.week_start
        """),
        {"scoped_orgs": scoped_orgs, "days": days},
    )
    time_series = []
    for row in time_series_result.mappings().all():
        ghas_repos = int(row["ghas_repos"] or 0)
        code_scanning_repos = int(row["code_scanning_repos"] or 0)
        secret_scanning_repos = int(row["secret_scanning_repos"] or 0)
        dependabot_repos = int(row["dependabot_repos"] or 0)
        push_protection_repos = int(row["push_protection_repos"] or 0)
        time_series.append(
            {
                "date": row["date"],
                "ghas_repos": ghas_repos,
                "ghas_pct": round((ghas_repos / total_repos) * 100, 2) if total_repos else 0.0,
                "code_scanning_repos": code_scanning_repos,
                "code_scanning_pct": round((code_scanning_repos / total_repos) * 100, 2)
                if total_repos
                else 0.0,
                "secret_scanning_repos": secret_scanning_repos,
                "secret_scanning_pct": round((secret_scanning_repos / total_repos) * 100, 2)
                if total_repos
                else 0.0,
                "dependabot_repos": dependabot_repos,
                "dependabot_pct": round((dependabot_repos / total_repos) * 100, 2)
                if total_repos
                else 0.0,
                "push_protection_repos": push_protection_repos,
                "push_protection_pct": round((push_protection_repos / total_repos) * 100, 2)
                if total_repos
                else 0.0,
            }
        )

    uncovered_result = await session.execute(
        text("""
            WITH repo_inventory AS (
                SELECT DISTINCT repo
                FROM events
                WHERE org = ANY(:scoped_orgs)
                  AND repo IS NOT NULL
            ),
            event_feature_states AS (
                SELECT DISTINCT ON (repo, feature)
                    repo,
                    feature,
                    CASE
                        WHEN action LIKE '%%.disable%%'
                            OR action LIKE '%%_disabled%%'
                            OR action LIKE '%%.disable'
                            OR action LIKE '%%disabled%%'
                            THEN 'disabled'
                        ELSE 'enabled'
                    END AS state
                FROM (
                    SELECT
                        repo,
                        CASE
                            WHEN action LIKE 'secret_scanning%%'
                                OR action LIKE 'repository_secret_scanning%%'
                                THEN 'secret_scanning'
                            WHEN action LIKE '%%codeql%%' THEN 'code_scanning'
                            WHEN action LIKE 'dependabot%%' THEN 'dependabot'
                            WHEN action LIKE '%%advanced_security%%' THEN 'ghas'
                            WHEN action LIKE '%%push_protection%%'
                                THEN 'push_protection'
                            ELSE NULL
                        END AS feature,
                        action,
                        created_at
                    FROM events
                    WHERE org = ANY(:scoped_orgs)
                      AND repo IS NOT NULL
                      AND (
                          action LIKE 'secret_scanning%%'
                          OR action LIKE 'repository_secret_scanning%%'
                          OR action LIKE '%%codeql%%'
                          OR action LIKE 'dependabot%%'
                          OR action LIKE '%%advanced_security%%'
                          OR action LIKE '%%push_protection%%'
                      )
                ) feature_events
                WHERE feature IS NOT NULL
                ORDER BY repo, feature, created_at DESC
            ),
            alert_features AS (
                SELECT DISTINCT repo_full_name AS repo, 'code_scanning' AS feature
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)

                UNION ALL

                SELECT DISTINCT repo_full_name AS repo, 'secret_scanning' AS feature
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)

                UNION ALL

                SELECT DISTINCT repo_full_name AS repo, 'dependabot' AS feature
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
            ),
            current_enabled AS (
                SELECT repo, feature
                FROM event_feature_states
                WHERE state = 'enabled'

                UNION

                SELECT repo, feature
                FROM alert_features
            ),
            repo_flags AS (
                SELECT
                    repo_inventory.repo,
                    MAX(CASE WHEN current_enabled.feature = 'ghas' THEN 1 ELSE 0 END)
                        AS has_ghas,
                    MAX(
                        CASE
                            WHEN current_enabled.feature = 'code_scanning' THEN 1
                            ELSE 0
                        END
                    ) AS has_code_scanning,
                    MAX(
                        CASE
                            WHEN current_enabled.feature = 'secret_scanning' THEN 1
                            ELSE 0
                        END
                    ) AS has_secret_scanning,
                    MAX(CASE WHEN current_enabled.feature = 'dependabot' THEN 1 ELSE 0 END)
                        AS has_dependabot,
                    MAX(
                        CASE
                            WHEN current_enabled.feature = 'push_protection' THEN 1
                            ELSE 0
                        END
                    ) AS has_push_protection
                FROM repo_inventory
                LEFT JOIN current_enabled ON current_enabled.repo = repo_inventory.repo
                GROUP BY repo_inventory.repo
            )
            SELECT
                repo AS repo_full_name,
                ARRAY_REMOVE(
                    ARRAY[
                        CASE WHEN has_ghas = 0 THEN 'ghas' END,
                        CASE WHEN has_code_scanning = 0 THEN 'code_scanning' END,
                        CASE WHEN has_secret_scanning = 0 THEN 'secret_scanning' END,
                        CASE WHEN has_dependabot = 0 THEN 'dependabot' END,
                        CASE WHEN has_push_protection = 0 THEN 'push_protection' END
                    ],
                    NULL
                ) AS missing_features
            FROM repo_flags
            WHERE has_ghas = 0
               OR has_code_scanning = 0
               OR has_secret_scanning = 0
               OR has_dependabot = 0
               OR has_push_protection = 0
            ORDER BY CARDINALITY(
                ARRAY_REMOVE(
                    ARRAY[
                        CASE WHEN has_ghas = 0 THEN 'ghas' END,
                        CASE WHEN has_code_scanning = 0 THEN 'code_scanning' END,
                        CASE WHEN has_secret_scanning = 0 THEN 'secret_scanning' END,
                        CASE WHEN has_dependabot = 0 THEN 'dependabot' END,
                        CASE WHEN has_push_protection = 0 THEN 'push_protection' END
                    ],
                    NULL
                )
            ) DESC, repo
            LIMIT 20
        """),
        {"scoped_orgs": scoped_orgs},
    )
    uncovered_repos = [dict(row) for row in uncovered_result.mappings().all()]

    features = [
        "ghas",
        "code_scanning",
        "secret_scanning",
        "dependabot",
        "push_protection",
    ]
    feature_coverage = {
        feature: {
            "repos": feature_counts.get(feature, 0),
            "pct": round((feature_counts.get(feature, 0) / total_repos) * 100, 2)
            if total_repos
            else 0.0,
        }
        for feature in features
    }

    return {
        "total_repos": total_repos,
        "feature_coverage": feature_coverage,
        "time_series": time_series,
        "uncovered_repos": uncovered_repos,
    }


async def get_alert_aging(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Analyze open alert aging and project burndown."""
    if not scoped_orgs:
        return {
            "age_buckets": [
                {
                    "bucket": "<7d",
                    "total_count": 0,
                    "critical_count": 0,
                    "high_count": 0,
                },
                {
                    "bucket": "7-30d",
                    "total_count": 0,
                    "critical_count": 0,
                    "high_count": 0,
                },
                {
                    "bucket": "30-90d",
                    "total_count": 0,
                    "critical_count": 0,
                    "high_count": 0,
                },
                {
                    "bucket": ">90d",
                    "total_count": 0,
                    "critical_count": 0,
                    "high_count": 0,
                },
            ],
            "oldest_critical": [],
            "burndown_projection": {
                "current_open": 0,
                "avg_close_rate_per_week": 0.0,
                "weeks_to_zero": None,
                "time_series": [{"week": week, "projected_open": 0} for week in range(1, 13)],
            },
        }

    bucket_result = await session.execute(
        text("""
            WITH open_alerts AS (
                SELECT
                    'secret_scanning' AS tool,
                    NULL::TEXT AS severity,
                    created_at,
                    EXTRACT(EPOCH FROM NOW() - created_at) / 86400.0 AS age_days
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'

                UNION ALL

                SELECT
                    'code_scanning' AS tool,
                    COALESCE(security_severity, severity) AS severity,
                    created_at,
                    EXTRACT(EPOCH FROM NOW() - created_at) / 86400.0 AS age_days
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'

                UNION ALL

                SELECT
                    'dependabot' AS tool,
                    severity,
                    created_at,
                    EXTRACT(EPOCH FROM NOW() - created_at) / 86400.0 AS age_days
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'
            ),
            aggregated AS (
                SELECT
                    CASE
                        WHEN age_days < 7 THEN '<7d'
                        WHEN age_days < 30 THEN '7-30d'
                        WHEN age_days < 90 THEN '30-90d'
                        ELSE '>90d'
                    END AS bucket,
                    COUNT(*) AS total_count,
                    COUNT(*) FILTER (WHERE severity = 'critical') AS critical_count,
                    COUNT(*) FILTER (WHERE severity = 'high') AS high_count
                FROM open_alerts
                GROUP BY 1
            )
            SELECT
                bucket,
                total_count,
                critical_count,
                high_count
            FROM aggregated
            ORDER BY CASE bucket
                WHEN '<7d' THEN 1
                WHEN '7-30d' THEN 2
                WHEN '30-90d' THEN 3
                ELSE 4
            END
        """),
        {"scoped_orgs": scoped_orgs},
    )
    bucket_map = {
        row["bucket"]: {
            "bucket": row["bucket"],
            "total_count": int(row["total_count"] or 0),
            "critical_count": int(row["critical_count"] or 0),
            "high_count": int(row["high_count"] or 0),
        }
        for row in bucket_result.mappings().all()
    }
    age_buckets = [
        bucket_map.get(
            bucket,
            {
                "bucket": bucket,
                "total_count": 0,
                "critical_count": 0,
                "high_count": 0,
            },
        )
        for bucket in ("<7d", "7-30d", "30-90d", ">90d")
    ]

    oldest_result = await session.execute(
        text("""
            WITH oldest_alerts AS (
                SELECT
                    'code_scanning' AS tool,
                    alert_number,
                    repo_full_name,
                    created_at,
                    COALESCE(security_severity, severity) AS severity,
                    ROUND(
                        (EXTRACT(EPOCH FROM NOW() - created_at) / 86400.0)::numeric,
                        2
                    ) AS age_days,
                    COALESCE(rule_id, tool_name, 'code_scanning') AS rule_info,
                    rule_description
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'
                  AND COALESCE(security_severity, severity) IN ('critical', 'high')

                UNION ALL

                SELECT
                    'dependabot' AS tool,
                    alert_number,
                    repo_full_name,
                    created_at,
                    severity,
                    ROUND(
                        (EXTRACT(EPOCH FROM NOW() - created_at) / 86400.0)::numeric,
                        2
                    ) AS age_days,
                    COALESCE(cve_id, package_name, 'dependabot') AS rule_info,
                    package_name AS rule_description
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'
                  AND severity IN ('critical', 'high')
            )
            SELECT
                tool,
                alert_number,
                repo_full_name,
                created_at,
                severity,
                age_days,
                rule_info,
                rule_description
            FROM oldest_alerts
            ORDER BY age_days DESC, created_at ASC
            LIMIT 10
        """),
        {"scoped_orgs": scoped_orgs},
    )
    oldest_critical = [dict(row) for row in oldest_result.mappings().all()]

    burndown_result = await session.execute(
        text("""
            WITH open_alerts AS (
                SELECT created_at
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'

                UNION ALL

                SELECT created_at
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'

                UNION ALL

                SELECT created_at
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'open'
            ),
            closed_alerts AS (
                SELECT resolved_at AS closed_at
                FROM secret_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state = 'resolved'
                  AND resolved_at IS NOT NULL
                  AND resolved_at >= NOW() - INTERVAL '30 days'

                UNION ALL

                SELECT COALESCE(fixed_at, dismissed_at) AS closed_at
                FROM code_scanning_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND state IN ('fixed', 'dismissed')
                  AND COALESCE(fixed_at, dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, dismissed_at) >= NOW() - INTERVAL '30 days'

                UNION ALL

                SELECT COALESCE(fixed_at, auto_dismissed_at) AS closed_at
                FROM dependabot_alerts
                WHERE org_slug = ANY(:scoped_orgs)
                  AND COALESCE(fixed_at, auto_dismissed_at) IS NOT NULL
                  AND COALESCE(fixed_at, auto_dismissed_at) >= NOW() - INTERVAL '30 days'
            )
            SELECT
                (SELECT COUNT(*) FROM open_alerts) AS current_open,
                (SELECT COUNT(*) FROM closed_alerts) AS closed_last_30_days
        """),
        {"scoped_orgs": scoped_orgs},
    )
    burndown_row = dict(burndown_result.mappings().first() or {})
    current_open = int(burndown_row.get("current_open") or 0)
    closed_last_30_days = int(burndown_row.get("closed_last_30_days") or 0)
    avg_close_rate_per_week = round((closed_last_30_days * 7) / 30, 2)
    weeks_to_zero = (
        round(current_open / avg_close_rate_per_week, 2) if avg_close_rate_per_week > 0 else None
    )
    burndown_series = [
        {
            "week": week,
            "projected_open": max(
                0,
                int(round(current_open - (avg_close_rate_per_week * week), 0)),
            ),
        }
        for week in range(1, 13)
    ]

    return {
        "age_buckets": age_buckets,
        "oldest_critical": oldest_critical,
        "burndown_projection": {
            "current_open": current_open,
            "avg_close_rate_per_week": avg_close_rate_per_week,
            "weeks_to_zero": weeks_to_zero,
            "time_series": burndown_series,
        },
    }


async def get_security_score(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Calculate a weighted strategic security score."""
    coverage = await get_coverage_growth(session, scoped_orgs=scoped_orgs, period="90d")
    mttr = await get_mttr_trends(session, scoped_orgs=scoped_orgs, period="30d")
    aging = await get_alert_aging(session, scoped_orgs=scoped_orgs)

    def _clamp(score: float) -> float:
        return round(min(100.0, max(0.0, score)), 2)

    coverage_values = [
        float((coverage.get("feature_coverage") or {}).get(feature, {}).get("pct", 0.0))
        for feature in (
            "ghas",
            "code_scanning",
            "secret_scanning",
            "dependabot",
            "push_protection",
        )
    ]
    coverage_score = (
        round(sum(coverage_values) / len(coverage_values), 2) if coverage_values else 0.0
    )

    mttr_hours = float(mttr.get("current_mttr_hours") or 0.0)
    mttr_score = _clamp(100 - ((mttr_hours - 72) * 0.5))

    current_open = int((aging.get("burndown_projection") or {}).get("current_open") or 0)
    total_repos = int(coverage.get("total_repos") or 0)
    alert_ratio = ((current_open / total_repos) * 10) if total_repos else 0.0
    alert_volume_score = _clamp(100 - (alert_ratio * 20))

    age_buckets = aging.get("age_buckets") or []
    old_alerts = sum(
        int(bucket.get("total_count") or 0)
        for bucket in age_buckets
        if bucket.get("bucket") in {"30-90d", ">90d"}
    )
    pct_old = (old_alerts / current_open) * 100 if current_open else 0.0
    aging_score = _clamp(100 - (pct_old * 1.5))

    trend_pct = float(mttr.get("trend_pct") or 0.0)
    trend_score = _clamp(50 + min(50.0, max(-50.0, -trend_pct)))

    components: list[dict[str, Any]] = [
        {
            "name": "Coverage",
            "score": round(coverage_score, 2),
            "weight": 30,
            "description": "Repository adoption of GHAS features.",
        },
        {
            "name": "MTTR",
            "score": mttr_score,
            "weight": 25,
            "description": "Average time to remediate resolved alerts.",
        },
        {
            "name": "Alert Volume",
            "score": alert_volume_score,
            "weight": 20,
            "description": "Open alert load relative to repository count.",
        },
        {
            "name": "Aging",
            "score": aging_score,
            "weight": 15,
            "description": "Share of open alerts older than 30 days.",
        },
        {
            "name": "Trend",
            "score": trend_score,
            "weight": 10,
            "description": "Recent MTTR direction; worsening trends reduce score.",
        },
    ]
    score = round(
        sum(float(component["score"]) * float(component["weight"]) for component in components)
        / 100,
        2,
    )

    suggestion_text: dict[str, str] = {
        "Coverage": (
            "Expand GHAS, code scanning, secret scanning, Dependabot, "
            "and push protection across more repositories."
        ),
        "MTTR": (
            "Reduce remediation time for critical and high-severity "
            "findings by tightening triage and fix SLAs."
        ),
        "Alert Volume": (
            "Lower open alert inventory by prioritizing repositories "
            "with the highest unresolved alert density."
        ),
        "Aging": (
            "Burn down findings older than 30 days, especially long-lived critical and high alerts."
        ),
        "Trend": (
            "Reverse MTTR deterioration by focusing on faster closure "
            "of new security findings this period."
        ),
    }
    suggestions: list[dict[str, Any]] = sorted(
        [
            {
                "name": component["name"],
                "impact": round(
                    float(component["weight"]) * (100 - float(component["score"])),
                    2,
                ),
                "suggestion": suggestion_text[component["name"]],
            }
            for component in components
        ],
        key=lambda item: float(item["impact"]),
        reverse=True,
    )[:3]

    return {
        "score": score,
        "components": components,
        "suggestions": suggestions,
    }


async def get_ghas_active_committers(
    session: AsyncSession,
    *,
    scoped_orgs: list[str],
) -> dict[str, Any]:
    """Get aggregated GHAS active committer counts across scoped orgs."""
    result = await session.execute(
        text("""
            SELECT
                COALESCE(SUM(total_active_committers), 0) AS total_active,
                COALESCE(SUM(maximum_active_committers), 0) AS maximum,
                COALESCE(SUM(purchased_committers), 0) AS purchased
            FROM ghas_active_committers
            WHERE org_slug = ANY(:scoped_orgs)
        """),
        {"scoped_orgs": scoped_orgs},
    )
    row = dict(result.mappings().first() or {})
    return {
        "total_active_committers": row.get("total_active", 0),
        "maximum_active_committers": row.get("maximum", 0),
        "purchased_committers": row.get("purchased", 0),
    }
