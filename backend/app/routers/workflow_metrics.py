"""Workflow failure and timeout metrics router.

Provides endpoints for identifying persistently failing or timing-out
GitHub Actions workflows using a window-function approach over the
``events`` hypertable.  Results are cached in Valkey for 5 minutes.

Action patterns handled:
- ``workflow_run.{conclusion}``  — written by the GitHub API sync worker
- ``workflows.completed_workflow_run`` — written by the audit-log ingestor

Data fields accessed from the JSONB ``data`` column:
- ``workflow_name`` (sync worker) / ``name`` (audit ingestor)
- ``run_id``
- ``conclusion``
- ``run_started_at``
- ``duration_seconds``
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, get_valkey

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/workflow-metrics", tags=["workflow-metrics"])

_CACHE_TTL = 300  # 5 minutes

# ── SQL ───────────────────────────────────────────────────────────────────────

# Both action patterns:
#   - workflow_run.{conclusion}         (github_sync_worker)
#   - workflows.completed_workflow_run  (audit log ingestor)
#
# Workflow name: COALESCE prefers 'workflow_name' (sync worker) then 'name'
# (audit log ingestor).
#
# Two variants of the query: one with an org filter, one without.
# Using separate SQL strings avoids runtime string formatting (S608).

_ALWAYS_FAILING_SQL = """
WITH ranked_runs AS (
    SELECT
        org,
        repo,
        COALESCE(
            NULLIF(data->>'workflow_name', ''),
            NULLIF(data->>'name', ''),
            'unknown'
        ) AS workflow_name,
        data->>'conclusion' AS conclusion,
        created_at,
        data->>'run_id' AS run_id,
        ROW_NUMBER() OVER (
            PARTITION BY
                org,
                repo,
                COALESCE(
                    NULLIF(data->>'workflow_name', ''),
                    NULLIF(data->>'name', ''),
                    'unknown'
                )
            ORDER BY created_at DESC
        ) AS rn
    FROM events
    WHERE (
        action LIKE 'workflow_run.%%'
        OR action = 'workflows.completed_workflow_run'
    )
      AND data->>'conclusion' NOT IN ('cancelled', 'skipped')
      AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
),
windowed AS (
    SELECT *
    FROM ranked_runs
    WHERE rn <= :threshold
),
failing_workflows AS (
    SELECT
        org,
        repo,
        workflow_name,
        COUNT(*) AS run_count,
        COUNT(*) FILTER (WHERE conclusion = :target_conclusion) AS fail_count,
        MAX(created_at) AS last_run_at
    FROM windowed
    GROUP BY org, repo, workflow_name
    HAVING
        COUNT(*) = :threshold
        AND COUNT(*) FILTER (WHERE conclusion = :target_conclusion) = :threshold
)
SELECT org, repo, workflow_name, run_count, last_run_at
FROM failing_workflows
ORDER BY last_run_at DESC
"""

_ALWAYS_FAILING_SQL_WITH_ORG = """
WITH ranked_runs AS (
    SELECT
        org,
        repo,
        COALESCE(
            NULLIF(data->>'workflow_name', ''),
            NULLIF(data->>'name', ''),
            'unknown'
        ) AS workflow_name,
        data->>'conclusion' AS conclusion,
        created_at,
        data->>'run_id' AS run_id,
        ROW_NUMBER() OVER (
            PARTITION BY
                org,
                repo,
                COALESCE(
                    NULLIF(data->>'workflow_name', ''),
                    NULLIF(data->>'name', ''),
                    'unknown'
                )
            ORDER BY created_at DESC
        ) AS rn
    FROM events
    WHERE (
        action LIKE 'workflow_run.%%'
        OR action = 'workflows.completed_workflow_run'
    )
      AND data->>'conclusion' NOT IN ('cancelled', 'skipped')
      AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
      AND org = :org
),
windowed AS (
    SELECT *
    FROM ranked_runs
    WHERE rn <= :threshold
),
failing_workflows AS (
    SELECT
        org,
        repo,
        workflow_name,
        COUNT(*) AS run_count,
        COUNT(*) FILTER (WHERE conclusion = :target_conclusion) AS fail_count,
        MAX(created_at) AS last_run_at
    FROM windowed
    GROUP BY org, repo, workflow_name
    HAVING
        COUNT(*) = :threshold
        AND COUNT(*) FILTER (WHERE conclusion = :target_conclusion) = :threshold
)
SELECT org, repo, workflow_name, run_count, last_run_at
FROM failing_workflows
ORDER BY last_run_at DESC
"""

_RUN_HISTORY_SQL = """
SELECT
    data->>'run_id'                    AS run_id,
    created_at                         AS started_at,
    data->>'conclusion'                AS conclusion,
    (data->>'duration_seconds')::int   AS duration_seconds
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND org = :org
  AND repo = :repo
  AND COALESCE(
      NULLIF(data->>'workflow_name', ''),
      NULLIF(data->>'name', ''),
      'unknown'
  ) = :workflow_name
  AND created_at >= NOW() - MAKE_INTERVAL(days => :lookback_days)
ORDER BY created_at DESC
LIMIT :limit
"""


# ── Pydantic models ───────────────────────────────────────────────────────────


class WorkflowFailureSummary(BaseModel):
    """A single workflow that has been consistently failing or timing out."""

    org: str
    repo: str
    workflow_name: str
    consecutive_count: int
    last_run_at: datetime
    last_conclusion: str


class WorkflowRunRecord(BaseModel):
    """A single workflow run record."""

    run_id: str | None
    started_at: datetime
    conclusion: str
    duration_seconds: int | None


class AlwaysFailingResponse(BaseModel):
    """Response for the always-failing and always-timing-out endpoints."""

    items: list[WorkflowFailureSummary]
    total: int
    threshold: int
    lookback_days: int
    cached_at: datetime | None = None


class RunHistoryResponse(BaseModel):
    """Run history for a specific workflow."""

    org: str
    repo: str
    workflow_name: str
    runs: list[WorkflowRunRecord]


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _query_failing_workflows(
    db: AsyncSession,
    target_conclusion: str,
    threshold: int,
    lookback_days: int,
    org: str | None,
) -> list[dict[str, Any]]:
    """Execute the window-function query and return raw result rows.

    Uses separate SQL strings for the org-scoped vs. all-orgs variant to avoid
    runtime string formatting (which would trigger S608 SQL-injection warnings
    even though org values are passed as bound parameters).
    """
    if org:
        sql = _ALWAYS_FAILING_SQL_WITH_ORG
        params: dict[str, Any] = {
            "lookback_days": lookback_days,
            "threshold": threshold,
            "target_conclusion": target_conclusion,
            "org": org,
        }
    else:
        sql = _ALWAYS_FAILING_SQL
        params = {
            "lookback_days": lookback_days,
            "threshold": threshold,
            "target_conclusion": target_conclusion,
        }

    result = await db.execute(text(sql), params)
    rows = result.fetchall()
    return [
        {
            "org": row[0],
            "repo": row[1],
            "workflow_name": row[2],
            "consecutive_count": row[3],
            "last_run_at": row[4],
            "last_conclusion": target_conclusion,
        }
        for row in rows
    ]


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/always-failing", response_model=AlwaysFailingResponse)
async def always_failing(
    threshold: int = Query(default=5, ge=2, le=20),
    lookback_days: int = Query(default=30, ge=1, le=90),
    org: str | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    valkey: aioredis.Redis = Depends(get_valkey),
) -> AlwaysFailingResponse:
    """Return workflows whose last N consecutive runs all ended in failure.

    Cancelled and skipped runs are excluded from the window so they don't
    mask real failures.  Results are Valkey-cached for 5 minutes.
    """
    cache_key = f"wfm:v1:failing:{org or 'all'}:{lookback_days}:{threshold}"
    cached_raw = await valkey.get(cache_key)
    if cached_raw:
        try:
            data = json.loads(cached_raw)
            return AlwaysFailingResponse.model_validate(data)
        except Exception:
            logger.warning("workflow_metrics.cache_parse_error", key=cache_key)

    rows = await _query_failing_workflows(
        db,
        target_conclusion="failure",
        threshold=threshold,
        lookback_days=lookback_days,
        org=org,
    )

    response = AlwaysFailingResponse(
        items=[WorkflowFailureSummary(**r) for r in rows],
        total=len(rows),
        threshold=threshold,
        lookback_days=lookback_days,
        cached_at=datetime.now(UTC),
    )

    try:
        await valkey.setex(
            cache_key,
            _CACHE_TTL,
            json.dumps(response.model_dump(mode="json")),
        )
    except Exception:
        logger.warning("workflow_metrics.cache_write_error", key=cache_key)

    return response


@router.get("/always-timing-out", response_model=AlwaysFailingResponse)
async def always_timing_out(
    threshold: int = Query(default=3, ge=2, le=10),
    lookback_days: int = Query(default=30, ge=1, le=90),
    org: str | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    valkey: aioredis.Redis = Depends(get_valkey),
) -> AlwaysFailingResponse:
    """Return workflows whose last N consecutive runs all ended in timeout.

    Cancelled and skipped runs are excluded from the window.
    Results are Valkey-cached for 5 minutes.
    """
    cache_key = f"wfm:v1:timing_out:{org or 'all'}:{lookback_days}:{threshold}"
    cached_raw = await valkey.get(cache_key)
    if cached_raw:
        try:
            data = json.loads(cached_raw)
            return AlwaysFailingResponse.model_validate(data)
        except Exception:
            logger.warning("workflow_metrics.cache_parse_error", key=cache_key)

    rows = await _query_failing_workflows(
        db,
        target_conclusion="timed_out",
        threshold=threshold,
        lookback_days=lookback_days,
        org=org,
    )

    response = AlwaysFailingResponse(
        items=[WorkflowFailureSummary(**r) for r in rows],
        total=len(rows),
        threshold=threshold,
        lookback_days=lookback_days,
        cached_at=datetime.now(UTC),
    )

    try:
        await valkey.setex(
            cache_key,
            _CACHE_TTL,
            json.dumps(response.model_dump(mode="json")),
        )
    except Exception:
        logger.warning("workflow_metrics.cache_write_error", key=cache_key)

    return response


@router.get("/run-history", response_model=RunHistoryResponse)
async def run_history(
    org: str = Query(...),
    repo: str = Query(...),
    workflow_name: str = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    lookback_days: int = Query(default=90, ge=1, le=365),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RunHistoryResponse:
    """Return recent run history for a specific workflow.

    Not cached — the scope is narrow (single workflow) so queries are fast.
    """
    result = await db.execute(
        text(_RUN_HISTORY_SQL),
        {
            "org": org,
            "repo": repo,
            "workflow_name": workflow_name,
            "lookback_days": lookback_days,
            "limit": limit,
        },
    )
    rows = result.fetchall()

    runs = [
        WorkflowRunRecord(
            run_id=row[0],
            started_at=row[1],
            conclusion=row[2] or "unknown",
            duration_seconds=row[3],
        )
        for row in rows
    ]

    return RunHistoryResponse(
        org=org,
        repo=repo,
        workflow_name=workflow_name,
        runs=runs,
    )
