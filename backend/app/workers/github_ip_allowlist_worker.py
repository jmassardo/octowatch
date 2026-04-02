"""Celery task to refresh the GitHub IP allowlist.

Runs every 6 hours via Celery beat. Fetches the latest CIDRs from
GitHub's ``/meta`` endpoint and caches them in Valkey.
"""

from __future__ import annotations

import asyncio

import structlog
from celery import Task

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _refresh_async() -> int:
    """Async implementation — creates its own Valkey connection."""
    import redis.asyncio as aioredis

    from app.config import settings
    from app.services.github_ip_allowlist import GitHubIPAllowlist

    valkey = aioredis.Redis.from_url(
        settings.VALKEY_URL,
        decode_responses=True,
        max_connections=5,
    )
    try:
        count = await GitHubIPAllowlist.refresh(valkey)
        return count
    finally:
        await valkey.aclose()


@celery_app.task(
    name="app.workers.github_ip_allowlist_worker.refresh_github_ip_allowlist",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def refresh_github_ip_allowlist(self: Task) -> dict[str, object]:
    """Refresh GitHub IP allowlist CIDRs from /meta endpoint."""
    try:
        count = asyncio.run(_refresh_async())
        logger.info("github_ip_allowlist.celery_refresh_complete", count=count)
        return {"status": "ok", "network_count": count}
    except Exception as exc:
        logger.error("github_ip_allowlist.celery_refresh_failed", error=str(exc))
        raise self.retry(exc=exc) from exc
