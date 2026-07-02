"""Dev activity router: API & Git usage statistics.

Provides aggregated usage stats for git operations (clone, push, fetch) and
API request events, plus bot-vs-human breakdown.  All queries enforce RBAC
via ``rbac_service.get_scoped_orgs``.

**Performance:** Queries read from ``cagg_events_daily`` /
``cagg_events_daily_repo`` (TimescaleDB continuous aggregates) instead of
scanning the raw ``events`` hypertable.  Responses are cached in Valkey
with a scope-aware key so repeated loads are sub-second.
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, get_valkey
from app.services import rbac_service
from app.services.cache_service import (
    _build_cache_key,
    cache_get,
    cache_set,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dev-activity", tags=["dev-activity"])

# Cache TTL for dev-activity endpoints (seconds)
_CACHE_TTL = 300


async def _resolve_orgs(
    db: AsyncSession,
    current_user: AuthenticatedUser,
) -> list[str]:
    """Resolve RBAC-scoped orgs and raise 403 when the list is empty.

    Global (sys_admin) users with no orgs yet get an empty list (no data)
    rather than 403, since it means no events/orgs have been synced yet.
    """
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs and current_user.scope_type != "global":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No org access",
        )
    return scoped_orgs


# ── Continuous-aggregate backed helpers ──────────────────────────────────


async def _git_action_counts(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
) -> dict[str, int]:
    """Count git.clone, git.push, git.fetch from the daily CAGG."""
    result = await db.execute(
        text("""
            SELECT action, SUM(event_count)::bigint AS cnt
            FROM cagg_events_daily
            WHERE action IN ('git.clone', 'git.push', 'git.fetch')
              AND org = ANY(:scoped_orgs)
              AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
            GROUP BY action
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days},
    )
    counts: dict[str, int] = {}
    for row in result.fetchall():
        counts[row[0]] = row[1]
    return counts


async def _top_cloners(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Top actors for git.clone from the daily CAGG."""
    result = await db.execute(
        text("""
            SELECT actor,
                   SUM(event_count)::bigint AS cnt,
                   actor LIKE :bot_suffix AS is_bot
            FROM cagg_events_daily
            WHERE action = 'git.clone'
              AND org = ANY(:scoped_orgs)
              AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
              AND actor IS NOT NULL AND actor != ''
            GROUP BY actor ORDER BY cnt DESC LIMIT :limit
        """),
        {
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "limit": limit,
            "bot_suffix": "%[bot]",
        },
    )
    return [{"actor": row[0], "count": row[1], "is_bot": bool(row[2])} for row in result.fetchall()]


async def _top_pushers(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Top actors for git.push with distinct repo count from repo CAGG."""
    result = await db.execute(
        text("""
            SELECT actor,
                   SUM(event_count)::bigint AS cnt,
                   COUNT(DISTINCT repo) FILTER (WHERE repo IS NOT NULL) AS repo_count
            FROM cagg_events_daily_repo
            WHERE action = 'git.push'
              AND org = ANY(:scoped_orgs)
              AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
              AND actor IS NOT NULL AND actor != ''
            GROUP BY actor ORDER BY cnt DESC LIMIT :limit
        """),
        {
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "limit": limit,
        },
    )
    return [
        {
            "actor": row[0],
            "count": row[1],
            "repos": [],  # Not fetching full list from CAGG for performance
            "repo_count": row[2],
        }
        for row in result.fetchall()
    ]


async def _daily_git_trend(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
) -> list[dict[str, Any]]:
    """Daily git event counts from the daily CAGG."""
    result = await db.execute(
        text("""
            SELECT bucket::date AS day,
                   SUM(event_count) FILTER (WHERE action = 'git.clone')::bigint AS clones,
                   SUM(event_count) FILTER (WHERE action = 'git.push')::bigint AS pushes,
                   SUM(event_count) FILTER (WHERE action = 'git.fetch')::bigint AS fetches
            FROM cagg_events_daily
            WHERE action IN ('git.clone', 'git.push', 'git.fetch')
              AND org = ANY(:scoped_orgs)
              AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
            GROUP BY day ORDER BY day
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days},
    )
    return [
        {
            "date": str(row[0]),
            "clones": row[1] or 0,
            "pushes": row[2] or 0,
            "fetches": row[3] or 0,
        }
        for row in result.fetchall()
    ]


async def _api_stats(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
    limit: int,
) -> dict[str, Any]:
    """API usage stats from the daily CAGG."""
    # Total API request count
    count_result = await db.execute(
        text("""
            SELECT COALESCE(SUM(event_count), 0)::bigint
            FROM cagg_events_daily
            WHERE action LIKE 'api.%'
              AND org = ANY(:scoped_orgs)
              AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days},
    )
    total_requests = count_result.scalar() or 0

    if total_requests == 0:
        return {
            "total_requests": 0,
            "top_users": [],
            "top_endpoints": [],
            "daily_trend": [],
            "available": False,
        }

    # Top API users
    users_result = await db.execute(
        text("""
            SELECT actor, SUM(event_count)::bigint AS cnt
            FROM cagg_events_daily
            WHERE action LIKE 'api.%'
              AND org = ANY(:scoped_orgs)
              AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
              AND actor IS NOT NULL AND actor != ''
            GROUP BY actor ORDER BY cnt DESC LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days, "limit": limit},
    )
    top_users = [{"actor": row[0], "count": row[1]} for row in users_result.fetchall()]

    # Top endpoints — requires raw events for JSONB extraction; keep but
    # narrow the scan to api.* actions only (a small fraction of events).
    endpoints_result = await db.execute(
        text("""
            SELECT COALESCE(
                       data->>'operation_type',
                       (data->>'request_method') || ' ' || (data->>'request_path'),
                       action
                   ) AS endpoint,
                   COUNT(*) AS cnt
            FROM events
            WHERE action LIKE 'api.%'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
            GROUP BY endpoint ORDER BY cnt DESC LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days, "limit": limit},
    )
    top_endpoints = [{"endpoint": row[0], "count": row[1]} for row in endpoints_result.fetchall()]

    # Daily API trend
    trend_result = await db.execute(
        text("""
            SELECT bucket::date AS day,
                   SUM(event_count)::bigint AS requests
            FROM cagg_events_daily
            WHERE action LIKE 'api.%'
              AND org = ANY(:scoped_orgs)
              AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
            GROUP BY day ORDER BY day
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days},
    )
    daily_trend = [{"date": str(row[0]), "requests": row[1]} for row in trend_result.fetchall()]

    return {
        "total_requests": total_requests,
        "top_users": top_users,
        "top_endpoints": top_endpoints,
        "daily_trend": daily_trend,
        "available": True,
    }


async def _bot_vs_human(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
) -> dict[str, Any]:
    """Bot vs human breakdown from the daily CAGG."""
    result = await db.execute(
        text("""
            SELECT actor_is_bot,
                   SUM(event_count)::bigint AS cnt
            FROM cagg_events_daily
            WHERE action IN ('git.clone', 'git.push', 'git.fetch')
              AND org = ANY(:scoped_orgs)
              AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
              AND actor IS NOT NULL AND actor != ''
            GROUP BY actor_is_bot
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days},
    )

    bot_events = 0
    human_events = 0

    for row in result.fetchall():
        if row[0]:
            bot_events = row[1]
        else:
            human_events = row[1]

    return {
        "bot_events": bot_events,
        "human_events": human_events,
        "bot_actors": [],  # Omitted for performance; use actors endpoint
        "human_actors": [],
    }


async def _developer_stats(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Aggregate per-developer activity from the daily CAGG.

    Repo-related actions include ``git.push``, ``pull_request.*``,
    ``pull_request_review*``, and ``repo.*``.  Weekly counts are built
    from daily buckets grouped into 7-day windows.
    """
    result = await db.execute(
        text("""
            WITH dev_totals AS (
                SELECT
                    actor,
                    SUM(event_count)::bigint AS event_count,
                    SUM(event_count) FILTER (
                        WHERE action LIKE 'pull_request.%'
                    )::bigint AS pr_count,
                    SUM(event_count) FILTER (
                        WHERE action LIKE 'pull_request_review%'
                    )::bigint AS review_count,
                    MAX(last_seen) AS last_active,
                    SUM(event_count) FILTER (
                        WHERE bucket >= NOW() - INTERVAL '7 days'
                    )::bigint AS w6,
                    SUM(event_count) FILTER (
                        WHERE bucket >= NOW() - INTERVAL '14 days'
                          AND bucket < NOW() - INTERVAL '7 days'
                    )::bigint AS w5,
                    SUM(event_count) FILTER (
                        WHERE bucket >= NOW() - INTERVAL '21 days'
                          AND bucket < NOW() - INTERVAL '14 days'
                    )::bigint AS w4,
                    SUM(event_count) FILTER (
                        WHERE bucket >= NOW() - INTERVAL '28 days'
                          AND bucket < NOW() - INTERVAL '21 days'
                    )::bigint AS w3,
                    SUM(event_count) FILTER (
                        WHERE bucket >= NOW() - INTERVAL '35 days'
                          AND bucket < NOW() - INTERVAL '28 days'
                    )::bigint AS w2,
                    SUM(event_count) FILTER (
                        WHERE bucket >= NOW() - INTERVAL '42 days'
                          AND bucket < NOW() - INTERVAL '35 days'
                    )::bigint AS w1,
                    SUM(event_count) FILTER (
                        WHERE bucket < NOW() - INTERVAL '42 days'
                    )::bigint AS w0
                FROM cagg_events_daily
                WHERE actor IS NOT NULL AND actor != ''
                  AND (
                      action = 'git.push'
                      OR action LIKE 'pull_request%'
                      OR action LIKE 'repo.%'
                  )
                  AND org = ANY(:scoped_orgs)
                  AND bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                GROUP BY actor
                ORDER BY event_count DESC
                LIMIT :limit
            )
            SELECT d.*,
                   COALESCE(r.repo_count, 0) AS repo_count,
                   r.top_repos
            FROM dev_totals d
            LEFT JOIN LATERAL (
                SELECT COUNT(DISTINCT repo)::int AS repo_count,
                       ARRAY(
                           SELECT repo FROM cagg_events_daily_repo rr
                           WHERE rr.actor = d.actor
                             AND rr.org = ANY(:scoped_orgs)
                             AND rr.bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                             AND rr.repo IS NOT NULL
                             AND (rr.action = 'git.push' OR rr.action LIKE 'pull_request%'
                                  OR rr.action LIKE 'repo.%')
                           GROUP BY repo
                           ORDER BY SUM(event_count) DESC
                           LIMIT 5
                       ) AS top_repos
                FROM cagg_events_daily_repo r2
                WHERE r2.actor = d.actor
                  AND r2.org = ANY(:scoped_orgs)
                  AND r2.bucket >= NOW() - MAKE_INTERVAL(days => :lookback_days)
                  AND r2.repo IS NOT NULL
                  AND (r2.action = 'git.push' OR r2.action LIKE 'pull_request%'
                       OR r2.action LIKE 'repo.%')
            ) r ON true
            ORDER BY d.event_count DESC
        """),
        {
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "limit": limit,
        },
    )

    developers: list[dict[str, Any]] = []
    for row in result.fetchall():
        developers.append(
            {
                "login": row[0],
                "event_count": row[1],
                "pr_count": row[2] or 0,
                "review_count": row[3] or 0,
                "top_repos": list(row[13]) if row[13] else [],
                "repo_count": row[12] or 0,
                "last_active": row[4].isoformat() if row[4] else None,
                "weekly_counts": [
                    row[11] or 0,
                    row[10] or 0,
                    row[9] or 0,
                    row[8] or 0,
                    row[7] or 0,
                    row[6] or 0,
                    row[5] or 0,
                ],
            }
        )
    return developers


# ── Route handlers ───────────────────────────────────────────────────────


@router.get("/developers", response_model=dict[str, Any])
async def list_developers(
    lookback_days: int = Query(default=90, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    valkey: aioredis.Redis = Depends(get_valkey),
) -> dict[str, Any]:
    """Return per-developer activity stats based on repo-related audit events.

    Only considers actions that represent real repository work:
    ``git.push``, ``pull_request.*``, ``pull_request_review*``, ``repo.*``.
    """
    scoped_orgs = await _resolve_orgs(db, current_user)

    cache_key = _build_cache_key(
        "dev-activity.developers", scoped_orgs, {"lookback_days": lookback_days}
    )
    cached = await cache_get(valkey, cache_key)
    if cached is not None:
        return cached

    developers = await _developer_stats(db, scoped_orgs, lookback_days, limit=50)
    result = {"developers": developers, "lookback_days": lookback_days}
    await cache_set(valkey, cache_key, result, _CACHE_TTL)
    return result


@router.get("/usage-stats", response_model=dict[str, Any])
async def usage_stats(
    lookback_days: int = Query(default=30, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    valkey: aioredis.Redis = Depends(get_valkey),
) -> dict[str, Any]:
    """Return aggregated API and Git usage statistics for the Dev Activity page."""
    scoped_orgs = await _resolve_orgs(db, current_user)

    cache_key = _build_cache_key(
        "dev-activity.usage-stats", scoped_orgs, {"lookback_days": lookback_days}
    )
    cached = await cache_get(valkey, cache_key)
    if cached is not None:
        return cached

    limit = 15

    git_counts = await _git_action_counts(db, scoped_orgs, lookback_days)
    top_cloners = await _top_cloners(db, scoped_orgs, lookback_days, limit)
    top_pushers = await _top_pushers(db, scoped_orgs, lookback_days, limit)
    daily_trend = await _daily_git_trend(db, scoped_orgs, lookback_days)
    api = await _api_stats(db, scoped_orgs, lookback_days, limit)
    bot_human = await _bot_vs_human(db, scoped_orgs, lookback_days)

    result = {
        "git_stats": {
            "total_clones": git_counts.get("git.clone", 0),
            "total_pushes": git_counts.get("git.push", 0),
            "total_fetches": git_counts.get("git.fetch", 0),
            "top_cloners": top_cloners,
            "top_pushers": top_pushers,
            "daily_trend": daily_trend,
        },
        "api_stats": api,
        "bot_vs_human": bot_human,
    }
    await cache_set(valkey, cache_key, result, _CACHE_TTL)
    return result
