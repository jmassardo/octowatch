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


# ── Audit log REST enrichment ────────────────────────────────────────────────


@celery_app.task(
    name="app.workers.enrichment_worker.enrich_audit_log_events",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def enrich_audit_log_events(self: Task) -> dict[str, object]:
    """Fetch audit log events via the REST API and enrich stored HEC events.

    This task reads events from the GitHub Enterprise audit log REST API
    (which includes fields like previous_value, current_value that the
    streaming/HEC payload omits) and merges those fields into the `data`
    JSONB column of existing events in the database.

    Only runs if:
    - audit_log_enrichment_enabled is "true" in app_settings
    - An enterprise PAT is configured (required for audit log REST access)
    """
    return asyncio.run(_enrich_audit_log_events_async())


async def _enrich_audit_log_events_async() -> dict[str, object]:
    """Async implementation of audit log enrichment."""
    import json
    from datetime import timedelta

    import httpx
    from sqlalchemy import text

    from app.services.settings_service import get_setting

    async with AsyncSessionLocal() as session:
        # Check if enrichment is enabled
        enabled = await get_setting(session, "audit_log_enrichment_enabled")
        if not enabled or enabled.lower() != "true":
            return {"status": "skipped", "reason": "disabled"}

        # Check if enough time has passed since last run (interval gating)
        interval_raw = await get_setting(session, "audit_log_enrichment_interval_minutes")
        interval_minutes = int(interval_raw) if interval_raw else 60
        last_run_raw = await get_setting(session, "audit_log_enrichment_last_run_at")

        if last_run_raw:
            try:
                last_run_at = datetime.fromisoformat(last_run_raw)
                elapsed = (datetime.now(UTC) - last_run_at).total_seconds() / 60
                if elapsed < interval_minutes:
                    return {"status": "skipped", "reason": "interval_not_elapsed"}
            except ValueError:
                pass

        # Get enterprise PAT
        enterprise_pat = await get_setting(session, "enterprise_pat")
        if not enterprise_pat:
            logger.warning("enrichment.no_enterprise_pat")
            return {"status": "skipped", "reason": "no_enterprise_pat"}

        # Get the enterprise slug from the most recent event
        slug_result = await session.execute(
            text(
                "SELECT DISTINCT data->>'business' FROM events "
                "WHERE data->>'business' IS NOT NULL "
                "ORDER BY 1 LIMIT 1"
            )
        )
        slug_row = slug_result.fetchone()
        if not slug_row or not slug_row[0]:
            logger.warning("enrichment.no_enterprise_slug")
            return {"status": "skipped", "reason": "no_enterprise_slug"}

        enterprise_slug = slug_row[0]

        # Determine time window: look back from now to last_run_at (or 2 hours default)
        if last_run_raw:
            try:
                lookback_start = datetime.fromisoformat(last_run_raw)
            except ValueError:
                lookback_start = datetime.now(UTC) - timedelta(hours=2)
        else:
            lookback_start = datetime.now(UTC) - timedelta(hours=2)

        # Fetch events from GitHub REST API
        enriched_count = 0
        after_cursor = None
        pages_fetched = 0
        max_pages = 50  # Safety cap

        async with httpx.AsyncClient(timeout=30) as client:
            while pages_fetched < max_pages:
                params: dict[str, str] = {
                    "per_page": "100",
                    "order": "asc",
                    "include": "web",
                }
                # Use phrase filter for time range
                phrase = f"created:>={lookback_start.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                params["phrase"] = phrase
                if after_cursor:
                    params["after"] = after_cursor

                resp = await client.get(
                    f"https://api.github.com/enterprises/{enterprise_slug}/audit-log",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {enterprise_pat}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )

                if resp.status_code == 401:
                    logger.error("enrichment.pat_unauthorized")
                    return {"status": "failed", "reason": "pat_unauthorized"}
                if resp.status_code == 403:
                    logger.error("enrichment.pat_forbidden")
                    return {"status": "failed", "reason": "pat_forbidden"}
                resp.raise_for_status()

                events = resp.json()
                if not events:
                    break

                pages_fetched += 1

                # Merge enrichment data into existing events
                for event in events:
                    doc_id = event.get("_document_id")
                    if not doc_id:
                        continue

                    # Collect REST-only fields not present in HEC payload
                    enrichment_fields = {}
                    for field in (
                        "previous_value",
                        "current_value",
                        "config_was",
                        "config_is",
                        "explanation",
                        "team",
                        "name",
                        "visibility",
                        "old_permission",
                        "permission",
                        "transport_protocol_name",
                        "deploy_key_fingerprint",
                        "read_only",
                    ):
                        if field in event and event[field] is not None:
                            enrichment_fields[field] = event[field]

                    if not enrichment_fields:
                        continue

                    # Merge into existing event's data JSONB
                    result = await session.execute(
                        text(
                            "UPDATE events SET data = data || :patch "
                            "WHERE document_id = :doc_id "
                            "AND NOT (data ? :check_key)"
                        ),
                        {
                            "patch": json.dumps(enrichment_fields),
                            "doc_id": doc_id,
                            "check_key": list(enrichment_fields.keys())[0],
                        },
                    )
                    if result.rowcount and result.rowcount > 0:
                        enriched_count += 1

                # Pagination — check Link header or use last event cursor
                after_cursor = None
                link_header = resp.headers.get("Link", "")
                if 'rel="next"' in link_header:
                    # Extract after param from next link
                    import re

                    match = re.search(r"after=([^&>]+)", link_header)
                    if match:
                        after_cursor = match.group(1)

                if not after_cursor:
                    break

        # Update last_run timestamp
        from app.services.settings_service import set_setting

        now = datetime.now(UTC)
        await set_setting(
            session,
            "audit_log_enrichment_last_run_at",
            now.isoformat(),
            category="sync",
            sensitivity="config",
            description="Last audit log enrichment run timestamp",
            changed_by="system",
        )
        await session.commit()

        logger.info(
            "enrichment.audit_log_completed",
            enriched=enriched_count,
            pages=pages_fetched,
            lookback_start=lookback_start.isoformat(),
        )

        return {
            "status": "completed",
            "enriched_count": enriched_count,
            "pages_fetched": pages_fetched,
        }
