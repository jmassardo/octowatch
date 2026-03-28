"""Threat intelligence domain lookup service."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any
from urllib.parse import urlparse

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def is_malicious_domain(
    session: AsyncSession,
    url: str,
) -> tuple[bool, str | None]:
    """Check if a URL's domain matches any known-malicious entry."""
    parsed = urlparse(url)
    domain = parsed.hostname
    if not domain:
        return False, None

    result = await session.execute(
        text("""
            SELECT domain, source, confidence
            FROM threat_intel_domains
            WHERE active = TRUE
              AND (expires_at IS NULL OR expires_at > NOW())
        """)
    )

    for row in result.mappings().all():
        if fnmatch(domain, row["domain"]):
            logger.info(
                "threat_intel.match",
                domain=domain,
                pattern=row["domain"],
                source=row["source"],
            )
            return True, row["source"]

    return False, None


async def get_domain_list(
    session: AsyncSession,
    *,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    """Return threat intel domains."""
    if active_only:
        result = await session.execute(
            text("""
                SELECT id, domain, source, confidence, active,
                       added_at, added_by, expires_at, notes
                FROM threat_intel_domains
                WHERE active = TRUE
                ORDER BY added_at DESC
            """)
        )
    else:
        result = await session.execute(
            text("""
                SELECT id, domain, source, confidence, active,
                       added_at, added_by, expires_at, notes
                FROM threat_intel_domains
                ORDER BY added_at DESC
            """)
        )
    return [dict(row) for row in result.mappings().all()]
