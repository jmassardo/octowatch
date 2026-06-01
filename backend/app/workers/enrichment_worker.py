"""Enrichment Celery worker: process PR merge events and build delivery timelines."""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.enrichment_worker.enrich_pr_merge",
    bind=True,
    max_retries=3,
)
def enrich_pr_merge_task(
    self: Task,
    *,
    org: str,
    repo: str,
    pr_number: int,
    pr_body: str | None = None,
    pr_title: str | None = None,
    pr_merged_at_iso: str,
    merge_commit_sha: str | None = None,
) -> dict[str, object]:
    """Enrich a merged PR event with linked issues and delivery phase durations.

    This task is triggered when a pull_request.closed (merged) event is ingested.
    It parses closing keywords, looks up related events, and computes the
    delivery timeline phases.

    Args:
        org: GitHub organization name.
        repo: Repository name.
        pr_number: Pull request number.
        pr_body: PR body text.
        pr_title: PR title text.
        pr_merged_at_iso: ISO timestamp when the PR was merged.
        merge_commit_sha: SHA of the merge commit.

    Returns:
        Dictionary with enrichment result status and timeline ID.
    """
    try:
        result = asyncio.run(
            _enrich_pr(
                org=org,
                repo=repo,
                pr_number=pr_number,
                pr_body=pr_body,
                pr_title=pr_title,
                pr_merged_at_iso=pr_merged_at_iso,
                merge_commit_sha=merge_commit_sha,
            )
        )
        return {"status": "ok", "pr_number": pr_number, **result}
    except Exception as exc:
        logger.error(
            "enrichment_worker.task_failed",
            org=org,
            repo=repo,
            pr_number=pr_number,
            error=str(exc),
        )
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _enrich_pr(
    *,
    org: str,
    repo: str,
    pr_number: int,
    pr_body: str | None,
    pr_title: str | None,
    pr_merged_at_iso: str,
    merge_commit_sha: str | None,
) -> dict[str, object]:
    """Async wrapper that performs the actual enrichment."""
    from app.services.enrichment_service import enrich_pr_merge_event

    pr_merged_at = datetime.fromisoformat(pr_merged_at_iso).replace(tzinfo=UTC)

    async with AsyncSessionLocal() as session:
        timeline = await enrich_pr_merge_event(
            session,
            org=org,
            repo=repo,
            pr_number=pr_number,
            pr_body=pr_body,
            pr_title=pr_title,
            pr_merged_at=pr_merged_at,
            merge_commit_sha=merge_commit_sha,
        )
        await session.commit()

        return {
            "timeline_id": str(timeline.id),
            "total_hours": timeline.total_hours,
            "linked_issues": timeline.issue_numbers,
        }
