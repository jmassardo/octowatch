"""Threat intelligence domain and IP lookup service with feed management."""

from __future__ import annotations

import ipaddress
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


async def is_malicious_ip(
    session: AsyncSession,
    ip_str: str,
) -> tuple[bool, str | None]:
    """Check if an IP address matches any known-malicious IP indicator.

    Supports exact IP match and CIDR range matching.
    """
    try:
        target_ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, None

    result = await session.execute(
        text("""
            SELECT value, source, confidence
            FROM threat_intel_indicators
            WHERE active = TRUE
              AND indicator_type = 'ip'
              AND (expires_at IS NULL OR expires_at > NOW())
        """)
    )

    for row in result.mappings().all():
        indicator_value = row["value"]
        try:
            if "/" in indicator_value:
                # CIDR range
                network = ipaddress.ip_network(indicator_value, strict=False)
                if target_ip in network:
                    logger.info(
                        "threat_intel.ip_match",
                        ip=ip_str,
                        network=indicator_value,
                        source=row["source"],
                    )
                    return True, row["source"]
            else:
                # Exact IP match
                if target_ip == ipaddress.ip_address(indicator_value):
                    logger.info(
                        "threat_intel.ip_match",
                        ip=ip_str,
                        match=indicator_value,
                        source=row["source"],
                    )
                    return True, row["source"]
        except ValueError:
            continue

    return False, None


async def is_malicious_indicator(
    session: AsyncSession,
    value: str,
    indicator_type: str = "domain",
) -> tuple[bool, str | None]:
    """Unified check: dispatch to domain or IP matching based on type."""
    if indicator_type == "ip":
        return await is_malicious_ip(session, value)
    if indicator_type == "domain":
        return await is_malicious_domain(session, value)
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


async def get_indicators(
    session: AsyncSession,
    *,
    indicator_type: str | None = None,
    active_only: bool = True,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Return threat intel indicators with filtering and pagination.

    Returns (items, total_count).
    """
    conditions = []
    params: dict[str, Any] = {}

    if active_only:
        conditions.append("active = TRUE")
    if indicator_type:
        conditions.append("indicator_type = :indicator_type")
        params["indicator_type"] = indicator_type
    if search:
        conditions.append("value ILIKE :search")
        params["search"] = f"%{search}%"

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    # Count query
    count_result = await session.execute(
        # SECURITY: static clause fragments only, not user input
        text(f"SELECT COUNT(*) AS cnt FROM threat_intel_indicators WHERE {where_clause}"),
        params,
    )
    total = count_result.scalar_one()

    # Data query
    offset = (page - 1) * page_size
    params["limit"] = page_size
    params["offset"] = offset

    result = await session.execute(
        # SECURITY: static clause fragments only, not user input
        text(f"""
            SELECT id, indicator_type, value, source, confidence, active,
                   added_at, added_by, expires_at, notes, feed_id, metadata_json
            FROM threat_intel_indicators
            WHERE {where_clause}
            ORDER BY added_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    items = [dict(row) for row in result.mappings().all()]
    return items, int(total)


async def create_indicator(
    session: AsyncSession,
    *,
    indicator_type: str,
    value: str,
    source: str,
    confidence: float = 0.80,
    added_by: str,
    expires_at: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a new threat intel indicator."""
    params: dict[str, Any] = {
        "indicator_type": indicator_type,
        "value": value,
        "source": source,
        "confidence": confidence,
        "added_by": added_by,
        "expires_at": expires_at,
        "notes": notes,
    }
    result = await session.execute(
        text("""
            INSERT INTO threat_intel_indicators
                (indicator_type, value, source, confidence, added_by, expires_at, notes)
            VALUES
                (:indicator_type, :value, :source, :confidence, :added_by,
                 :expires_at::timestamptz, :notes)
            RETURNING id, indicator_type, value, source, confidence, active,
                      added_at, added_by, expires_at, notes
        """),
        params,
    )
    row = result.mappings().fetchone()
    await session.commit()
    return dict(row) if row else {}


async def update_indicator(
    session: AsyncSession,
    indicator_id: int,
    *,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update an existing indicator. Returns updated row or None if not found."""
    set_clauses = []
    params: dict[str, Any] = {"id": indicator_id}

    allowed_fields = {"value", "source", "confidence", "active", "expires_at", "notes"}
    for field_name, field_value in updates.items():
        if field_name in allowed_fields:
            set_clauses.append(f"{field_name} = :{field_name}")
            params[field_name] = field_value

    if not set_clauses:
        return None

    set_sql = ", ".join(set_clauses)
    result = await session.execute(
        # SECURITY: static clause fragments only, not user input
        text(f"""
            UPDATE threat_intel_indicators
            SET {set_sql}
            WHERE id = :id
            RETURNING id, indicator_type, value, source, confidence, active,
                      added_at, added_by, expires_at, notes
        """),
        params,
    )
    row = result.mappings().fetchone()
    await session.commit()
    return dict(row) if row else None


async def soft_delete_indicator(
    session: AsyncSession,
    indicator_id: int,
) -> bool:
    """Soft-delete an indicator by setting active=false. Returns True if found."""
    result = await session.execute(
        text("""
            UPDATE threat_intel_indicators
            SET active = FALSE
            WHERE id = :id AND active = TRUE
            RETURNING id
        """),
        {"id": indicator_id},
    )
    deleted = result.fetchone() is not None
    await session.commit()
    return deleted


async def get_feeds(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Return all configured threat intel feeds."""
    result = await session.execute(
        text("""
            SELECT id, name, url, feed_type, enabled, refresh_interval_minutes,
                   last_fetched_at, last_fetch_status, last_indicator_count,
                   created_by, created_at, updated_at, is_default
            FROM threat_intel_feeds
            ORDER BY created_at DESC
        """)
    )
    return [dict(row) for row in result.mappings().all()]


async def create_feed(
    session: AsyncSession,
    *,
    name: str,
    url: str,
    feed_type: str = "domain",
    refresh_interval_minutes: int = 1440,
    created_by: str,
) -> dict[str, Any]:
    """Create a new threat intel feed configuration."""
    result = await session.execute(
        text("""
            INSERT INTO threat_intel_feeds
                (name, url, feed_type, refresh_interval_minutes, created_by)
            VALUES
                (:name, :url, :feed_type, :refresh_interval_minutes, :created_by)
            RETURNING id, name, url, feed_type, enabled, refresh_interval_minutes,
                      last_fetched_at, last_fetch_status, last_indicator_count,
                      created_by, created_at, updated_at, is_default
        """),
        {
            "name": name,
            "url": url,
            "feed_type": feed_type,
            "refresh_interval_minutes": refresh_interval_minutes,
            "created_by": created_by,
        },
    )
    row = result.mappings().fetchone()
    await session.commit()
    return dict(row) if row else {}


async def fetch_feed_indicators(
    session: AsyncSession,
    feed_id: int,
    content: str,
    feed_type: str,
    added_by: str,
) -> int:
    """Parse feed content and upsert indicators. Returns count of indicators processed."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("#")]
    count = 0

    for line in lines:
        # Skip comments and empty lines
        if not line or line.startswith("//"):
            continue

        indicator_type = feed_type if feed_type in ("domain", "ip") else "domain"
        value = line.split(",")[0].strip() if "," in line else line.strip()

        if not value:
            continue

        await session.execute(
            text("""
                INSERT INTO threat_intel_indicators
                    (indicator_type, value, source, confidence, added_by, feed_id)
                VALUES
                    (:indicator_type, :value, :source, 0.70, :added_by, :feed_id)
                ON CONFLICT (indicator_type, value) DO UPDATE SET
                    active = TRUE,
                    feed_id = EXCLUDED.feed_id
            """),
            {
                "indicator_type": indicator_type,
                "value": value,
                "source": f"feed:{feed_id}",
                "added_by": added_by,
                "feed_id": feed_id,
            },
        )
        count += 1

    # Update feed status
    await session.execute(
        text("""
            UPDATE threat_intel_feeds
            SET last_fetched_at = NOW(),
                last_fetch_status = 'success',
                last_indicator_count = :count,
                updated_at = NOW()
            WHERE id = :feed_id
        """),
        {"feed_id": feed_id, "count": count},
    )
    await session.commit()
    return count


async def update_feed(
    session: AsyncSession,
    feed_id: int,
    *,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update an existing feed. Returns updated row or None if not found."""
    set_clauses = []
    params: dict[str, Any] = {"id": feed_id}

    allowed_fields = {"name", "url", "feed_type", "refresh_interval_minutes", "enabled"}
    for field_name, field_value in updates.items():
        if field_name in allowed_fields:
            set_clauses.append(f"{field_name} = :{field_name}")
            params[field_name] = field_value

    if not set_clauses:
        return None

    set_clauses.append("updated_at = NOW()")
    set_sql = ", ".join(set_clauses)
    result = await session.execute(
        text(f"""
            UPDATE threat_intel_feeds
            SET {set_sql}
            WHERE id = :id
            RETURNING id, name, url, feed_type, enabled, refresh_interval_minutes,
                      last_fetched_at, last_fetch_status, last_indicator_count,
                      created_by, created_at, updated_at, is_default
        """),
        params,
    )
    row = result.mappings().fetchone()
    await session.commit()
    return dict(row) if row else None


async def delete_feed(
    session: AsyncSession,
    feed_id: int,
) -> bool:
    """Delete a feed and its associated indicators. Returns True if found."""
    await session.execute(
        text("DELETE FROM threat_intel_indicators WHERE feed_id = :feed_id"),
        {"feed_id": feed_id},
    )
    result = await session.execute(
        text("DELETE FROM threat_intel_feeds WHERE id = :id RETURNING id"),
        {"id": feed_id},
    )
    deleted = result.fetchone() is not None
    await session.commit()
    return deleted


async def bulk_create_indicators(
    session: AsyncSession,
    *,
    indicators: list[dict[str, Any]],
    added_by: str,
) -> dict[str, int]:
    """Bulk create indicators. Returns counts of created, duplicates, errors."""
    created = 0
    duplicates = 0
    errors = 0

    for ind in indicators:
        try:
            result = await session.execute(
                text("""
                    INSERT INTO threat_intel_indicators
                        (indicator_type, value, source, confidence, added_by)
                    VALUES
                        (:indicator_type, :value, :source, :confidence, :added_by)
                    ON CONFLICT (indicator_type, value) DO NOTHING
                    RETURNING id
                """),
                {
                    "indicator_type": ind["indicator_type"],
                    "value": ind["value"],
                    "source": ind.get("source", "manual-bulk"),
                    "confidence": ind.get("confidence", 0.80),
                    "added_by": added_by,
                },
            )
            row = result.fetchone()
            if row:
                created += 1
            else:
                duplicates += 1
        except Exception:
            logger.warning("threat_intel.bulk_create_error", value=ind.get("value"))
            errors += 1

    await session.commit()
    return {"created": created, "duplicates": duplicates, "errors": errors}


async def get_matches(
    session: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int, int, int, str | None]:
    """Get detections that matched threat intel indicators.

    Returns (items, total, total_24h, unique_indicators, top_feed).
    Matches are detections whose context_data has threat_intel_match info,
    or whose source_ip / actor matches an indicator. For simplicity, we
    return recent detections that have context_data containing 'threat_intel'.
    """
    count_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM detections
            WHERE context_data::text ILIKE '%threat_intel%'
               OR context_data::text ILIKE '%malicious%'
        """)
    )
    total = int(count_result.scalar_one())

    count_24h_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM detections
            WHERE (context_data::text ILIKE '%threat_intel%'
               OR context_data::text ILIKE '%malicious%')
              AND triggered_at > NOW() - INTERVAL '24 hours'
        """)
    )
    total_24h = int(count_24h_result.scalar_one())

    offset = (page - 1) * page_size
    result = await session.execute(
        text("""
            SELECT id AS detection_id, title, severity, status,
                   actor, org, repo, triggered_at
            FROM detections
            WHERE context_data::text ILIKE '%threat_intel%'
               OR context_data::text ILIKE '%malicious%'
            ORDER BY triggered_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": page_size, "offset": offset},
    )
    items = [dict(row) for row in result.mappings().all()]

    return items, total, total_24h, 0, None


async def get_analytics(
    session: AsyncSession,
) -> dict[str, Any]:
    """Get aggregate threat intel analytics."""
    feeds_result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_feeds,
                COUNT(*) FILTER (WHERE enabled = TRUE) AS active_feeds
            FROM threat_intel_feeds
        """)
    )
    feeds_row = feeds_result.mappings().fetchone()
    total_feeds = int(feeds_row["total_feeds"]) if feeds_row else 0
    active_feeds = int(feeds_row["active_feeds"]) if feeds_row else 0

    indicators_result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total_indicators,
                COUNT(*) FILTER (WHERE active = TRUE) AS active_indicators
            FROM threat_intel_indicators
        """)
    )
    ind_row = indicators_result.mappings().fetchone()
    total_indicators = int(ind_row["total_indicators"]) if ind_row else 0
    active_indicators = int(ind_row["active_indicators"]) if ind_row else 0

    matches_result = await session.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM detections
            WHERE (context_data::text ILIKE '%threat_intel%'
               OR context_data::text ILIKE '%malicious%')
              AND triggered_at > NOW() - INTERVAL '30 days'
        """)
    )
    matches_30d = int(matches_result.scalar_one())

    coverage_score = round(active_indicators / total_indicators, 2) if total_indicators > 0 else 0.0

    mot_result = await session.execute(
        text("""
            SELECT DATE(triggered_at) AS date, COUNT(*) AS count
            FROM detections
            WHERE (context_data::text ILIKE '%threat_intel%'
               OR context_data::text ILIKE '%malicious%')
              AND triggered_at > NOW() - INTERVAL '30 days'
            GROUP BY DATE(triggered_at)
            ORDER BY date
        """)
    )
    matches_over_time = [
        {"date": str(row["date"]), "count": int(row["count"])}
        for row in mot_result.mappings().all()
    ]

    mbf_result = await session.execute(
        text("""
            SELECT source, COUNT(*) AS count
            FROM threat_intel_indicators
            WHERE active = TRUE
            GROUP BY source
            ORDER BY count DESC
            LIMIT 10
        """)
    )
    matches_by_feed = [
        {"name": row["source"], "count": int(row["count"])} for row in mbf_result.mappings().all()
    ]

    itd_result = await session.execute(
        text("""
            SELECT indicator_type, COUNT(*) AS count
            FROM threat_intel_indicators
            WHERE active = TRUE
            GROUP BY indicator_type
            ORDER BY count DESC
        """)
    )
    indicator_type_distribution = [
        {"type": row["indicator_type"], "count": int(row["count"])}
        for row in itd_result.mappings().all()
    ]

    return {
        "total_feeds": total_feeds,
        "active_feeds": active_feeds,
        "total_indicators": total_indicators,
        "active_indicators": active_indicators,
        "matches_30d": matches_30d,
        "coverage_score": coverage_score,
        "matches_over_time": matches_over_time,
        "matches_by_feed": matches_by_feed,
        "indicator_type_distribution": indicator_type_distribution,
    }


async def refresh_feed(
    session: AsyncSession,
    feed_id: int,
) -> dict[str, Any] | None:
    """Mark a feed as needing refresh and return its basic info."""
    result = await session.execute(
        text("""
            UPDATE threat_intel_feeds
            SET last_fetch_status = 'refreshing',
                updated_at = NOW()
            WHERE id = :id
            RETURNING id, name, last_indicator_count
        """),
        {"id": feed_id},
    )
    row = result.mappings().fetchone()
    await session.commit()
    if row is None:
        return None
    return dict(row)
