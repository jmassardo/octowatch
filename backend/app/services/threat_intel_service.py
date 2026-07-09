"""Threat intelligence domain and IP lookup service with feed management."""

from __future__ import annotations

import ipaddress
import json
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
                   created_by, created_at, updated_at, is_default,
                   parser_type, parser_config, auto_rule_generation, default_campaign_id
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
    parser_type: str = "plaintext",
    parser_config: dict[str, Any] | None = None,
    auto_rule_generation: bool = True,
    default_campaign_id: int | None = None,
) -> dict[str, Any]:
    """Create a new threat intel feed configuration."""
    result = await session.execute(
        text("""
            INSERT INTO threat_intel_feeds
                (name, url, feed_type, refresh_interval_minutes, created_by,
                 parser_type, parser_config, auto_rule_generation, default_campaign_id)
            VALUES
                (:name, :url, :feed_type, :refresh_interval_minutes, :created_by,
                 :parser_type, :parser_config, :auto_rule_generation, :default_campaign_id)
            RETURNING id, name, url, feed_type, enabled, refresh_interval_minutes,
                      last_fetched_at, last_fetch_status, last_indicator_count,
                      created_by, created_at, updated_at, is_default,
                      parser_type, parser_config, auto_rule_generation, default_campaign_id
        """),
        {
            "name": name,
            "url": url,
            "feed_type": feed_type,
            "refresh_interval_minutes": refresh_interval_minutes,
            "created_by": created_by,
            "parser_type": parser_type,
            "parser_config": json.dumps(parser_config) if parser_config else None,
            "auto_rule_generation": auto_rule_generation,
            "default_campaign_id": default_campaign_id,
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
    *,
    parser_type: str = "plaintext",
    parser_config: dict[str, Any] | None = None,
    default_campaign_id: int | None = None,
) -> int:
    """Parse feed content using the appropriate parser and upsert indicators."""
    from app.services.feed_parsers import get_parser

    config = dict(parser_config or {})
    # Plaintext parser needs indicator_type from feed_type
    if parser_type == "plaintext" and "indicator_type" not in config:
        config["indicator_type"] = feed_type if feed_type in ("domain", "ip") else "domain"

    parser = get_parser(parser_type)
    parse_result = parser.parse(content, config)

    for warning in parse_result.warnings:
        logger.warning("threat_intel.parse_warning", feed_id=feed_id, warning=warning)

    # Upsert campaign if the parser extracted one
    campaign_id = default_campaign_id
    if parse_result.campaign_name:
        campaign_id = await _upsert_campaign(
            session,
            feed_id=feed_id,
            name=parse_result.campaign_name,
            description=parse_result.campaign_description,
            severity=parse_result.campaign_severity or "critical",
            references=parse_result.campaign_references,
            mitre_attack=parse_result.campaign_mitre_attack,
        )

    count = 0
    for ind in parse_result.indicators:
        ind_campaign_id = campaign_id
        # If the indicator specifies a different campaign, resolve it
        if ind.campaign_name and ind.campaign_name != parse_result.campaign_name:
            ind_campaign_id = await _upsert_campaign(
                session,
                feed_id=feed_id,
                name=ind.campaign_name,
            )

        metadata = ind.metadata or {}
        if ind.suggested_action_filters:
            metadata["suggested_action_filters"] = ind.suggested_action_filters

        await session.execute(
            text("""
                INSERT INTO threat_intel_indicators
                    (indicator_type, value, source, confidence, added_by,
                     feed_id, campaign_id, expires_at, notes, metadata_json)
                VALUES
                    (:indicator_type, :value, :source, :confidence, :added_by,
                     :feed_id, :campaign_id, :expires_at, :notes, :metadata_json)
                ON CONFLICT (indicator_type, value) DO UPDATE SET
                    active = TRUE,
                    confidence = GREATEST(
                        threat_intel_indicators.confidence,
                        EXCLUDED.confidence
                    ),
                    feed_id = EXCLUDED.feed_id,
                    campaign_id = COALESCE(
                        EXCLUDED.campaign_id,
                        threat_intel_indicators.campaign_id
                    ),
                    expires_at = EXCLUDED.expires_at,
                    metadata_json = COALESCE(
                        EXCLUDED.metadata_json,
                        threat_intel_indicators.metadata_json
                    )
            """),
            {
                "indicator_type": ind.indicator_type,
                "value": ind.value,
                "source": f"feed:{feed_id}",
                "confidence": ind.confidence,
                "added_by": added_by,
                "feed_id": feed_id,
                "campaign_id": ind_campaign_id,
                "expires_at": ind.expires_at,
                "notes": ind.source_reference,
                "metadata_json": json.dumps(metadata) if metadata else None,
            },
        )
        count += 1

    # Determine feed status
    status = "success"
    if parse_result.warnings and count == 0:
        status = "failed"
    elif parse_result.warnings:
        status = f"partial ({parse_result.skipped_count} skipped)"

    await session.execute(
        text("""
            UPDATE threat_intel_feeds
            SET last_fetched_at = NOW(),
                last_fetch_status = :status,
                last_indicator_count = :count,
                updated_at = NOW()
            WHERE id = :feed_id
        """),
        {"feed_id": feed_id, "count": count, "status": status},
    )
    await session.commit()
    return count


async def _upsert_campaign(
    session: AsyncSession,
    *,
    feed_id: int,
    name: str,
    description: str | None = None,
    severity: str = "critical",
    references: list[str] | None = None,
    mitre_attack: list[str] | None = None,
) -> int:
    """Insert or update a campaign, returning its ID."""
    import re as _re

    slug = _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    metadata: dict[str, Any] = {}
    if references:
        metadata["references"] = references
    if mitre_attack:
        metadata["mitre_attack"] = mitre_attack

    result = await session.execute(
        text("""
            INSERT INTO threat_intel_campaigns
                (name, slug, description, severity, source_feed_id, metadata_json)
            VALUES
                (:name, :slug, :description, :severity, :source_feed_id, :metadata_json)
            ON CONFLICT (name) DO UPDATE SET
                last_updated = NOW(),
                description = COALESCE(
                    EXCLUDED.description,
                    threat_intel_campaigns.description
                ),
                metadata_json = COALESCE(
                    EXCLUDED.metadata_json,
                    threat_intel_campaigns.metadata_json
                )
            RETURNING id
        """),
        {
            "name": name,
            "slug": slug,
            "description": description,
            "severity": severity,
            "source_feed_id": feed_id,
            "metadata_json": json.dumps(metadata) if metadata else None,
        },
    )
    row = result.fetchone()
    return row[0]  # type: ignore[index]


async def update_feed(
    session: AsyncSession,
    feed_id: int,
    *,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update an existing feed. Returns updated row or None if not found."""
    set_clauses = []
    params: dict[str, Any] = {"id": feed_id}

    allowed_fields = {
        "name",
        "url",
        "feed_type",
        "refresh_interval_minutes",
        "enabled",
        "parser_type",
        "auto_rule_generation",
        "default_campaign_id",
    }
    for field_name, field_value in updates.items():
        if field_name in allowed_fields:
            set_clauses.append(f"{field_name} = :{field_name}")
            params[field_name] = field_value
        elif field_name == "parser_config":
            set_clauses.append("parser_config = :parser_config")
            params["parser_config"] = json.dumps(field_value) if field_value else None

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
                      created_by, created_at, updated_at, is_default,
                      parser_type, parser_config, auto_rule_generation, default_campaign_id
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
