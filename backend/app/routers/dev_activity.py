"""Dev activity router: API & Git usage statistics.

Provides aggregated usage stats for git operations (clone, push, fetch) and
API request events, plus bot-vs-human breakdown. All queries enforce RBAC
via ``rbac_service.get_scoped_orgs``.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.services import rbac_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dev-activity", tags=["dev-activity"])


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


async def _git_action_counts(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
) -> dict[str, int]:
    """Count git.clone, git.push, git.fetch events in the lookback window."""
    result = await db.execute(
        text("""
            SELECT action, COUNT(*) AS cnt
            FROM events
            WHERE action IN ('git.clone', 'git.push', 'git.fetch')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
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
    """Return top actors for git.clone events."""
    result = await db.execute(
        text("""
            SELECT actor, COUNT(*) AS cnt,
                   actor LIKE :bot_suffix AS is_bot
            FROM events
            WHERE action = 'git.clone'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
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
    """Return top actors for git.push events with distinct repos."""
    result = await db.execute(
        text("""
            SELECT actor, COUNT(*) AS cnt,
                   ARRAY_AGG(DISTINCT repo) FILTER (WHERE repo IS NOT NULL) AS repos
            FROM events
            WHERE action = 'git.push'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
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
            "repos": list(row[2]) if row[2] else [],
        }
        for row in result.fetchall()
    ]


async def _daily_git_trend(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
) -> list[dict[str, Any]]:
    """Return daily git event counts over the lookback window."""
    result = await db.execute(
        text("""
            SELECT DATE(created_at) AS day,
                   COUNT(*) FILTER (WHERE action = 'git.clone') AS clones,
                   COUNT(*) FILTER (WHERE action = 'git.push') AS pushes,
                   COUNT(*) FILTER (WHERE action = 'git.fetch') AS fetches
            FROM events
            WHERE action IN ('git.clone', 'git.push', 'git.fetch')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
            GROUP BY day ORDER BY day
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days},
    )
    return [
        {
            "date": str(row[0]),
            "clones": row[1],
            "pushes": row[2],
            "fetches": row[3],
        }
        for row in result.fetchall()
    ]


async def _api_stats(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
    limit: int,
) -> dict[str, Any]:
    """Return API usage stats. Returns available=False when no api.* events exist."""
    # Check if any api events exist
    count_result = await db.execute(
        text("""
            SELECT COUNT(*) FROM events
            WHERE action LIKE 'api.%'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
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
            SELECT actor, COUNT(*) AS cnt
            FROM events
            WHERE action LIKE 'api.%'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
              AND actor IS NOT NULL AND actor != ''
            GROUP BY actor ORDER BY cnt DESC LIMIT :limit
        """),
        {"scoped_orgs": scoped_orgs, "lookback_days": lookback_days, "limit": limit},
    )
    top_users = [{"actor": row[0], "count": row[1]} for row in users_result.fetchall()]

    # Top endpoints
    endpoints_result = await db.execute(
        text("""
            SELECT COALESCE(
                       data->>'operation_type',
                       data->>'request_method' || ' ' || data->>'request_path',
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
            SELECT DATE(created_at) AS day, COUNT(*) AS requests
            FROM events
            WHERE action LIKE 'api.%'
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
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
    """Return bot vs human breakdown for git events."""
    result = await db.execute(
        text("""
            SELECT
              actor LIKE :bot_suffix AS is_bot,
              COUNT(*) AS cnt,
              ARRAY_AGG(DISTINCT actor) AS actors
            FROM events
            WHERE action IN ('git.clone', 'git.push', 'git.fetch')
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
              AND actor IS NOT NULL AND actor != ''
            GROUP BY is_bot
        """),
        {
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "bot_suffix": "%[bot]",
        },
    )

    bot_events = 0
    human_events = 0
    bot_actors: list[str] = []
    human_actors: list[str] = []

    for row in result.fetchall():
        is_bot = bool(row[0])
        count = row[1]
        actors = list(row[2]) if row[2] else []
        if is_bot:
            bot_events = count
            bot_actors = actors
        else:
            human_events = count
            human_actors = actors

    return {
        "bot_events": bot_events,
        "human_events": human_events,
        "bot_actors": bot_actors,
        "human_actors": human_actors,
    }


async def _developer_stats(
    db: AsyncSession,
    scoped_orgs: list[str],
    lookback_days: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Aggregate per-developer activity from repo-related audit events.

    Repo-related actions include ``git.push``, ``pull_request.*``,
    ``pull_request_review*``, and ``repo.*``.  Weekly counts are divided
    into seven 7-day buckets (oldest → most recent) for the mini bar chart.
    """
    result = await db.execute(
        text("""
            SELECT
                actor,
                COUNT(*) AS event_count,
                COUNT(*) FILTER (WHERE action LIKE :pr_only) AS pr_count,
                COUNT(*) FILTER (WHERE action LIKE :review) AS review_count,
                ARRAY_AGG(DISTINCT repo) FILTER (WHERE repo IS NOT NULL) AS repos,
                MAX(created_at) AS last_active,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS w6,
                COUNT(*) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '14 days'
                      AND created_at < NOW() - INTERVAL '7 days'
                ) AS w5,
                COUNT(*) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '21 days'
                      AND created_at < NOW() - INTERVAL '14 days'
                ) AS w4,
                COUNT(*) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '28 days'
                      AND created_at < NOW() - INTERVAL '21 days'
                ) AS w3,
                COUNT(*) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '35 days'
                      AND created_at < NOW() - INTERVAL '28 days'
                ) AS w2,
                COUNT(*) FILTER (
                    WHERE created_at >= NOW() - INTERVAL '42 days'
                      AND created_at < NOW() - INTERVAL '35 days'
                ) AS w1,
                COUNT(*) FILTER (
                    WHERE created_at < NOW() - INTERVAL '42 days'
                ) AS w0
            FROM events
            WHERE actor IS NOT NULL AND actor != ''
              AND (
                  action = 'git.push'
                  OR action LIKE :any_pr
                  OR action LIKE :repo_action
              )
              AND org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
            GROUP BY actor
            ORDER BY event_count DESC
            LIMIT :limit
        """),
        {
            "scoped_orgs": scoped_orgs,
            "lookback_days": lookback_days,
            "limit": limit,
            "any_pr": "pull_request%",
            "pr_only": "pull_request.%",
            "review": "pull_request_review%",
            "repo_action": "repo.%",
        },
    )

    developers: list[dict[str, Any]] = []
    for row in result.fetchall():
        all_repos = list(row[4]) if row[4] else []
        developers.append(
            {
                "login": row[0],
                "event_count": row[1],
                "pr_count": row[2],
                "review_count": row[3],
                "top_repos": all_repos[:5],
                "repo_count": len(all_repos),
                "last_active": row[5].isoformat() if row[5] else None,
                "weekly_counts": [
                    row[12],
                    row[11],
                    row[10],
                    row[9],
                    row[8],
                    row[7],
                    row[6],
                ],
            }
        )
    return developers


@router.get("/developers", response_model=dict[str, Any])
async def list_developers(
    lookback_days: int = Query(default=90, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return per-developer activity stats based on repo-related audit events.

    Only considers actions that represent real repository work:
    ``git.push``, ``pull_request.*``, ``pull_request_review*``, ``repo.*``.
    """
    scoped_orgs = await _resolve_orgs(db, current_user)
    developers = await _developer_stats(db, scoped_orgs, lookback_days, limit=50)
    return {"developers": developers, "lookback_days": lookback_days}


@router.get("/usage-stats", response_model=dict[str, Any])
async def usage_stats(
    lookback_days: int = Query(default=30, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return aggregated API and Git usage statistics for the Dev Activity page."""
    scoped_orgs = await _resolve_orgs(db, current_user)
    limit = 15

    git_counts = await _git_action_counts(db, scoped_orgs, lookback_days)
    top_cloners = await _top_cloners(db, scoped_orgs, lookback_days, limit)
    top_pushers = await _top_pushers(db, scoped_orgs, lookback_days, limit)
    daily_trend = await _daily_git_trend(db, scoped_orgs, lookback_days)
    api = await _api_stats(db, scoped_orgs, lookback_days, limit)
    bot_human = await _bot_vs_human(db, scoped_orgs, lookback_days)

    return {
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
