"""Copilot session analytics service: overview stats and session detail.

Only the overview and detail read paths are implemented here per #508 (part
of #387, Phase 2 API). The other 10 endpoints from #387 are deliberately out
of scope — see the follow-up issue filed for them. No ingestion or detection
logic lives in this module; that is #507 and #509 respectively.

All queries are org-scoped via ``scoped_orgs`` resolved by
``rbac_service.get_scoped_orgs`` in the router layer, consistent with
``team_health_service`` and ``enrichment_service.get_delivery_timeline_stats``.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Number of top models/editors to surface in the overview.
_TOP_N = 5


async def get_copilot_sessions_overview(
    db: AsyncSession,
    scoped_orgs: list[str],
    days: int = 30,
) -> dict[str, Any]:
    """Return aggregated Copilot session overview stats for the scoped orgs.

    Args:
        db: Async database session.
        scoped_orgs: RBAC-scoped list of orgs to include. An empty list
            yields an empty overview rather than an unfiltered query.
        days: Lookback window in days (default 30).

    Returns:
        Dict with total session count, average duration, and the top models
        and editors by session count.
    """
    empty: dict[str, Any] = {
        "total_sessions": 0,
        "avg_duration_seconds": None,
        "top_models": [],
        "top_editors": [],
        "lookback_days": days,
    }
    if not scoped_orgs:
        return empty

    params: dict[str, Any] = {"scoped_orgs": scoped_orgs, "days": days}

    stats_result = await db.execute(
        text("""
            SELECT
                COUNT(*) AS total_sessions,
                ROUND(AVG(duration_seconds)::numeric, 2) AS avg_duration_seconds
            FROM copilot_sessions
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :days)
        """),
        params,
    )
    stats_row = stats_result.mappings().first()

    if stats_row is None or stats_row["total_sessions"] == 0:
        return empty

    models_result = await db.execute(
        text("""
            SELECT model, COUNT(*) AS session_count
            FROM copilot_sessions
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :days)
              AND model IS NOT NULL
            GROUP BY model
            ORDER BY session_count DESC, model ASC
            LIMIT :top_n
        """),
        {**params, "top_n": _TOP_N},
    )
    top_models = [
        {"model": row["model"], "count": row["session_count"]}
        for row in models_result.mappings().all()
    ]

    editors_result = await db.execute(
        text("""
            SELECT editor, COUNT(*) AS session_count
            FROM copilot_sessions
            WHERE org = ANY(:scoped_orgs)
              AND created_at >= NOW() - MAKE_INTERVAL(days => :days)
              AND editor IS NOT NULL
            GROUP BY editor
            ORDER BY session_count DESC, editor ASC
            LIMIT :top_n
        """),
        {**params, "top_n": _TOP_N},
    )
    top_editors = [
        {"editor": row["editor"], "count": row["session_count"]}
        for row in editors_result.mappings().all()
    ]

    return {
        "total_sessions": stats_row["total_sessions"],
        "avg_duration_seconds": (
            float(stats_row["avg_duration_seconds"])
            if stats_row["avg_duration_seconds"] is not None
            else None
        ),
        "top_models": top_models,
        "top_editors": top_editors,
        "lookback_days": days,
    }


async def get_copilot_session_detail(
    db: AsyncSession,
    scoped_orgs: list[str],
    session_id: str,
) -> dict[str, Any] | None:
    """Return a single Copilot session with all of its turns.

    Args:
        db: Async database session.
        scoped_orgs: RBAC-scoped list of orgs to include. An empty list
            always yields ``None`` (no access).
        session_id: The session's ``session_id`` (not the internal bigint
            primary key).

    Returns:
        Dict with session fields and a ``turns`` list, or ``None`` if the
        session does not exist or is outside the caller's org scope.
    """
    if not scoped_orgs:
        return None

    session_result = await db.execute(
        text("""
            SELECT
                id, session_id, created_at, enterprise, org, actor, actor_id,
                editor, editor_version, copilot_version, model, language,
                repository, turn_count, tool_call_count, total_tokens_in,
                total_tokens_out, duration_seconds, started_at, ended_at
            FROM copilot_sessions
            WHERE session_id = :session_id
              AND org = ANY(:scoped_orgs)
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"session_id": session_id, "scoped_orgs": scoped_orgs},
    )
    session_row = session_result.mappings().first()
    if session_row is None:
        return None

    # ``copilot_session_turns.session_id`` is not a database-enforced FK (see
    # the 0073 migration docstring), so defensively re-scope by the parent
    # session's org as well as the session_id match.
    turns_result = await db.execute(
        text("""
            SELECT
                turn_index, created_at, prompt_text, prompt_tokens,
                response_text, response_tokens, model, finish_reason,
                latency_ms, tool_calls, references, annotations
            FROM copilot_session_turns
            WHERE session_id = :session_id
              AND (org = :org OR org IS NULL)
            ORDER BY turn_index ASC NULLS LAST, created_at ASC
        """),
        {"session_id": session_id, "org": session_row["org"]},
    )
    turns = [dict(row) for row in turns_result.mappings().all()]

    session = dict(session_row)
    session["turns"] = turns
    return session
