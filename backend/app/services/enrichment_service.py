"""Enrichment service: link PRs to issues and CI runs for delivery timelines.

This service processes merged pull request events and enriches them with:
- Linked issue numbers (parsed from closing keywords in PR body/title)
- Phase durations across the delivery lifecycle
- Related CI workflow run completions
"""

from __future__ import annotations

import re
from datetime import datetime

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery_timeline import DeliveryTimeline

logger = structlog.get_logger(__name__)

# Pattern matches: fixes #123, closes #456, resolves #789
# Also matches org/repo#123 style references
_CLOSING_KEYWORD_PATTERN = re.compile(
    r"(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+"
    r"(?:[\w\-]+/[\w\-]+)?#(\d+)",
    re.IGNORECASE,
)


def parse_linked_issues(text_content: str) -> list[int]:
    """Extract linked issue numbers from PR body/title using closing keywords.

    Parses GitHub closing keyword patterns like:
    - fixes #123
    - closes #456
    - resolves org/repo#789

    Args:
        text_content: PR body or title text to parse.

    Returns:
        Deduplicated list of issue numbers found.
    """
    if not text_content:
        return []
    matches = _CLOSING_KEYWORD_PATTERN.findall(text_content)
    return sorted({int(m) for m in matches})


def compute_hours_between(start: datetime | None, end: datetime | None) -> float | None:
    """Compute hours between two timestamps, returning None if either is missing."""
    if start is None or end is None:
        return None
    delta = end - start
    return round(delta.total_seconds() / 3600.0, 2)


async def enrich_pr_merge_event(
    session: AsyncSession,
    *,
    org: str,
    repo: str,
    pr_number: int,
    pr_body: str | None,
    pr_title: str | None,
    pr_merged_at: datetime,
    merge_commit_sha: str | None,
) -> DeliveryTimeline:
    """Enrich a merged PR event with linked issues and phase durations.

    Looks up related events in the audit log to compute delivery phase timings:
    - backlog_hours: earliest linked issue created → first issue assigned
    - dev_hours: first issue assigned → PR opened
    - review_hours: PR opened → PR merged
    - deploy_hours: PR merged → CI workflow run completed

    Args:
        session: Async database session.
        org: GitHub organization name.
        repo: Repository name (without org prefix).
        pr_number: Pull request number.
        pr_body: PR body text (may contain closing keywords).
        pr_title: PR title text (may contain closing keywords).
        pr_merged_at: Timestamp when the PR was merged.
        merge_commit_sha: SHA of the merge commit.

    Returns:
        The created or updated DeliveryTimeline record.
    """
    # Parse linked issues from title and body
    combined_text = f"{pr_title or ''}\n{pr_body or ''}"
    issue_numbers = parse_linked_issues(combined_text)

    logger.info(
        "enrichment.processing_pr",
        org=org,
        repo=repo,
        pr_number=pr_number,
        linked_issues=issue_numbers,
    )

    # Look up issue lifecycle timestamps from audit events
    issue_created_at: datetime | None = None
    issue_assigned_at: datetime | None = None

    if issue_numbers:
        issue_created_at = await _find_earliest_issue_event(
            session, org=org, repo=repo, issue_numbers=issue_numbers, action="issues.opened"
        )
        issue_assigned_at = await _find_earliest_issue_event(
            session,
            org=org,
            repo=repo,
            issue_numbers=issue_numbers,
            action="issues.assigned",
        )

    # Look up PR opened timestamp
    pr_opened_at = await _find_pr_opened_at(session, org=org, repo=repo, pr_number=pr_number)

    # Look up CI completion after merge
    ci_completed_at = await _find_ci_completion(
        session, org=org, repo=repo, merge_commit_sha=merge_commit_sha
    )

    # Compute phase durations
    backlog_hours = compute_hours_between(issue_created_at, issue_assigned_at)
    dev_hours = compute_hours_between(issue_assigned_at or issue_created_at, pr_opened_at)
    review_hours = compute_hours_between(pr_opened_at, pr_merged_at)
    deploy_hours = compute_hours_between(pr_merged_at, ci_completed_at)

    # Compute total (sum of non-None phases)
    phase_values = [
        v for v in [backlog_hours, dev_hours, review_hours, deploy_hours] if v is not None
    ]
    total_hours = round(sum(phase_values), 2) if phase_values else None

    # Upsert the delivery timeline record
    stmt = pg_insert(DeliveryTimeline).values(
        org=org,
        repo=repo,
        pr_number=pr_number,
        issue_numbers=issue_numbers,
        backlog_hours=backlog_hours,
        dev_hours=dev_hours,
        review_hours=review_hours,
        deploy_hours=deploy_hours,
        total_hours=total_hours,
        merge_commit_sha=merge_commit_sha,
        pr_merged_at=pr_merged_at,
        ci_completed_at=ci_completed_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["org", "repo", "pr_number"],
        set_={
            "issue_numbers": stmt.excluded.issue_numbers,
            "backlog_hours": stmt.excluded.backlog_hours,
            "dev_hours": stmt.excluded.dev_hours,
            "review_hours": stmt.excluded.review_hours,
            "deploy_hours": stmt.excluded.deploy_hours,
            "total_hours": stmt.excluded.total_hours,
            "merge_commit_sha": stmt.excluded.merge_commit_sha,
            "pr_merged_at": stmt.excluded.pr_merged_at,
            "ci_completed_at": stmt.excluded.ci_completed_at,
        },
    )
    await session.execute(stmt)
    await session.flush()

    # Fetch the record to return
    result = await session.execute(
        select(DeliveryTimeline).where(
            DeliveryTimeline.org == org,
            DeliveryTimeline.repo == repo,
            DeliveryTimeline.pr_number == pr_number,
        )
    )
    timeline = result.scalar_one()

    logger.info(
        "enrichment.timeline_created",
        org=org,
        repo=repo,
        pr_number=pr_number,
        total_hours=total_hours,
    )

    return timeline


async def get_delivery_timeline_stats(
    session: AsyncSession,
    *,
    orgs: list[str],
    repo: str | None = None,
    days: int = 30,
) -> dict[str, object]:
    """Get aggregated delivery timeline statistics for given orgs.

    Args:
        session: Async database session.
        orgs: List of organizations to include (RBAC-scoped).
        repo: Optional repository filter.
        days: Number of days to look back (default 30).

    Returns:
        Dictionary with aggregated metrics including averages, percentiles,
        and per-repo breakdowns.
    """
    if not orgs:
        return {
            "total_prs": 0,
            "avg_backlog_hours": None,
            "avg_dev_hours": None,
            "avg_review_hours": None,
            "avg_deploy_hours": None,
            "avg_total_hours": None,
            "timelines": [],
        }

    # Build parameterized query for aggregated stats
    org_placeholders = ", ".join(f":org_{i}" for i in range(len(orgs)))
    params: dict[str, object] = {f"org_{i}": org for i, org in enumerate(orgs)}
    params["days"] = days

    where_clause = (
        f"org IN ({org_placeholders}) AND created_at >= NOW() - make_interval(days => :days)"
    )
    if repo:
        where_clause += " AND repo = :repo"
        params["repo"] = repo

    # Aggregated stats
    stats_sql = text(f"""
        SELECT
            COUNT(*) AS total_prs,
            ROUND(AVG(backlog_hours)::numeric, 2) AS avg_backlog_hours,
            ROUND(AVG(dev_hours)::numeric, 2) AS avg_dev_hours,
            ROUND(AVG(review_hours)::numeric, 2) AS avg_review_hours,
            ROUND(AVG(deploy_hours)::numeric, 2) AS avg_deploy_hours,
            ROUND(AVG(total_hours)::numeric, 2) AS avg_total_hours,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_hours)::numeric, 2)
                AS median_total_hours,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_hours)::numeric, 2)
                AS p95_total_hours
        FROM delivery_timelines
        WHERE {where_clause}
    """)  # noqa: S608 - params are bound via SQLAlchemy, not string-interpolated user input

    result = await session.execute(stats_sql, params)
    row = result.mappings().first()

    if row is None or row["total_prs"] == 0:
        return {
            "total_prs": 0,
            "avg_backlog_hours": None,
            "avg_dev_hours": None,
            "avg_review_hours": None,
            "avg_deploy_hours": None,
            "avg_total_hours": None,
            "timelines": [],
        }

    # Recent timelines (last 20)
    timelines_sql = text(f"""
        SELECT id, pr_number, repo, org, issue_numbers,
               backlog_hours, dev_hours, review_hours, deploy_hours,
               total_hours, pr_merged_at, created_at
        FROM delivery_timelines
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT 20
    """)  # noqa: S608

    timelines_result = await session.execute(timelines_sql, params)
    timelines = [dict(r) for r in timelines_result.mappings().all()]

    return {
        "total_prs": row["total_prs"],
        "avg_backlog_hours": float(row["avg_backlog_hours"])
        if row["avg_backlog_hours"] is not None
        else None,
        "avg_dev_hours": float(row["avg_dev_hours"]) if row["avg_dev_hours"] is not None else None,
        "avg_review_hours": float(row["avg_review_hours"])
        if row["avg_review_hours"] is not None
        else None,
        "avg_deploy_hours": float(row["avg_deploy_hours"])
        if row["avg_deploy_hours"] is not None
        else None,
        "avg_total_hours": float(row["avg_total_hours"])
        if row["avg_total_hours"] is not None
        else None,
        "median_total_hours": float(row["median_total_hours"])
        if row["median_total_hours"] is not None
        else None,
        "p95_total_hours": float(row["p95_total_hours"])
        if row["p95_total_hours"] is not None
        else None,
        "timelines": timelines,
    }


async def _find_earliest_issue_event(
    session: AsyncSession,
    *,
    org: str,
    repo: str,
    issue_numbers: list[int],
    action: str,
) -> datetime | None:
    """Find the earliest event timestamp for any of the linked issues.

    Searches the events table for matching issue events by action type
    and issue number stored in the event data payload.
    """
    if not issue_numbers:
        return None

    # Build issue number match against data->'issue'->'number'
    issue_placeholders = ", ".join(f":issue_{i}" for i in range(len(issue_numbers)))
    params: dict[str, object] = {f"issue_{i}": num for i, num in enumerate(issue_numbers)}
    params["org"] = org
    params["repo"] = repo
    params["action"] = action

    sql = text(f"""
        SELECT MIN(created_at) AS earliest
        FROM events
        WHERE org = :org
          AND repo = :repo
          AND action = :action
          AND (data->'issue'->>'number')::int IN ({issue_placeholders})
    """)  # noqa: S608

    result = await session.execute(sql, params)
    row = result.mappings().first()
    if row and row["earliest"]:
        result_val: datetime = row["earliest"]
        return result_val
    return None


async def _find_pr_opened_at(
    session: AsyncSession,
    *,
    org: str,
    repo: str,
    pr_number: int,
) -> datetime | None:
    """Find when a PR was opened by looking at pull_request.opened events."""
    sql = text("""
        SELECT MIN(created_at) AS opened_at
        FROM events
        WHERE org = :org
          AND repo = :repo
          AND action = 'pull_request.opened'
          AND (data->'pull_request'->>'number')::int = :pr_number
    """)
    result = await session.execute(sql, {"org": org, "repo": repo, "pr_number": pr_number})
    row = result.mappings().first()
    if row and row["opened_at"]:
        result_val: datetime = row["opened_at"]
        return result_val
    return None


async def _find_ci_completion(
    session: AsyncSession,
    *,
    org: str,
    repo: str,
    merge_commit_sha: str | None,
) -> datetime | None:
    """Find CI workflow run completion after a merge commit.

    Looks for workflow_run.completed events triggered by the merge commit SHA.
    """
    if not merge_commit_sha:
        return None

    sql = text("""
        SELECT MAX(created_at) AS completed_at
        FROM events
        WHERE org = :org
          AND repo = :repo
          AND action = 'workflow_run.completed'
          AND data->'workflow_run'->>'head_sha' = :sha
    """)
    result = await session.execute(sql, {"org": org, "repo": repo, "sha": merge_commit_sha})
    row = result.mappings().first()
    if row and row["completed_at"]:
        result_val: datetime = row["completed_at"]
        return result_val
    return None
