"""Retroactive scanner: scan recent events against newly-ingested campaign IOCs.

When new threat intel indicators arrive, this worker scans recent audit log
events for matches that occurred before the IOCs were known.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from celery import Task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)

# Processing constraints
BATCH_SIZE = 1000
DEFAULT_LOOKBACK_DAYS = 7


@celery_app.task(
    name="app.workers.retro_scan_worker.retro_scan_campaign",
    bind=True,
    max_retries=2,
)
def retro_scan_campaign_task(
    self: Task,
    campaign_id: int,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> dict[str, object]:
    """Celery task: scan recent events against a campaign's feed-derived rules."""
    try:
        result = asyncio.run(_retro_scan(campaign_id, lookback_days))
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error(
            "retro_scan.task_failed",
            campaign_id=campaign_id,
            error=str(exc),
        )
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _retro_scan(
    campaign_id: int,
    lookback_days: int,
) -> dict[str, object]:
    """Core retro scan logic.

    1. Load feed-derived rules for this campaign
    2. Query recent events matching rule action_filters in batches
    3. Evaluate each event against each rule (action match + x_config engine)
    4. Write detections with retroactive flag, skipping duplicates
    """
    from app.services.detection_service import (
        _check_x_config_engine,
        event_matches_rule,
    )

    scan_started_at = datetime.now(UTC).isoformat()
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)

    total_events_scanned = 0
    detections_created = 0
    duplicates_skipped = 0

    async with AsyncSessionLocal() as session:
        # Step 1: Load feed-derived rules for this campaign
        rules = await _load_campaign_rules(session, campaign_id)
        if not rules:
            logger.info(
                "retro_scan.no_rules",
                campaign_id=campaign_id,
            )
            return {
                "campaign_id": campaign_id,
                "events_scanned": 0,
                "detections_created": 0,
            }

        # Collect action filters across all rules for efficient event querying
        action_filters = _collect_action_filters(rules)

        logger.info(
            "retro_scan.started",
            campaign_id=campaign_id,
            lookback_days=lookback_days,
            rule_count=len(rules),
            action_filters=action_filters,
        )

        # Step 2: Scan events in batches
        last_id = 0
        while True:
            event_rows = await _fetch_event_batch(
                session,
                action_filters=action_filters,
                cutoff=cutoff,
                after_id=last_id,
                batch_size=BATCH_SIZE,
            )

            if not event_rows:
                break

            total_events_scanned += len(event_rows)

            # Step 3: Evaluate each event against each rule
            for event in event_rows:
                for rule in rules:
                    if not event_matches_rule(event, rule):
                        continue

                    # Check x_config engine match
                    if not await _check_x_config_engine(event, rule, session):
                        continue

                    # Step 4: Dedup — skip if detection already exists
                    already_detected = await _detection_exists(session, rule.id, event.id)
                    if already_detected:
                        duplicates_skipped += 1
                        continue

                    # Write detection with retroactive flag
                    det_id = await _write_retro_detection(
                        session,
                        rule=rule,
                        event=event,
                        scan_started_at=scan_started_at,
                    )
                    if det_id is not None:
                        detections_created += 1

            last_id = event_rows[-1].id
            await session.commit()

        # Final commit for any remaining work
        await session.commit()

        # Step 5: Send summary notification if matches found
        if detections_created > 0:
            await _send_retro_scan_notification(
                session,
                campaign_id=campaign_id,
                detections_created=detections_created,
                events_scanned=total_events_scanned,
            )
            await session.commit()

    logger.info(
        "retro_scan.completed",
        campaign_id=campaign_id,
        events_scanned=total_events_scanned,
        detections_created=detections_created,
        duplicates_skipped=duplicates_skipped,
    )

    return {
        "campaign_id": campaign_id,
        "events_scanned": total_events_scanned,
        "detections_created": detections_created,
        "duplicates_skipped": duplicates_skipped,
    }


async def _load_campaign_rules(
    session: AsyncSession,
    campaign_id: int,
) -> list[Any]:
    """Load active feed-derived rules for a campaign."""
    from sqlalchemy import select

    from app.models.detection import RuleDefinition

    stmt = select(RuleDefinition).where(
        RuleDefinition.campaign_id == campaign_id,
        RuleDefinition.source == "feed",
        RuleDefinition.enabled.is_(True),
        RuleDefinition.status == "active",
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _collect_action_filters(rules: list[Any]) -> list[str]:
    """Collect unique action filter patterns across all rules."""
    filters: set[str] = set()
    for rule in rules:
        action_filters = rule.logic_config.get("action_filters", [])
        filters.update(action_filters)
    return sorted(filters)


async def _fetch_event_batch(
    session: AsyncSession,
    *,
    action_filters: list[str],
    cutoff: datetime,
    after_id: int,
    batch_size: int,
) -> list[Any]:
    """Fetch a batch of events matching action filters since cutoff.

    Uses cursor-based pagination (after_id) for efficient batching.
    Wildcard '*' in action_filters means all events are eligible.
    """
    from sqlalchemy import select

    from app.models.audit_event import AuditEvent

    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.created_at >= cutoff,
            AuditEvent.id > after_id,
        )
        .order_by(AuditEvent.id.asc())
        .limit(batch_size)
    )

    # If no wildcard, filter by specific actions
    if "*" not in action_filters:
        # Use LIKE patterns for fnmatch-style wildcards
        from sqlalchemy import or_

        action_conditions = []
        for pattern in action_filters:
            if "*" in pattern or "?" in pattern:
                # Convert fnmatch to SQL LIKE
                sql_pattern = pattern.replace("*", "%").replace("?", "_")
                action_conditions.append(AuditEvent.action.like(sql_pattern))
            else:
                action_conditions.append(AuditEvent.action == pattern)

        if action_conditions:
            stmt = stmt.where(or_(*action_conditions))

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _detection_exists(
    session: AsyncSession,
    rule_id: int,
    event_id: int,
) -> bool:
    """Check if a detection already exists for this rule + event combo."""
    result = await session.execute(
        text("""
            SELECT 1 FROM detections
            WHERE rule_id = :rule_id
              AND :event_id = ANY(event_ids)
            LIMIT 1
        """),
        {"rule_id": rule_id, "event_id": event_id},
    )
    return result.fetchone() is not None


async def _write_retro_detection(
    session: AsyncSession,
    *,
    rule: Any,
    event: Any,
    scan_started_at: str,
) -> int | None:
    """Write a detection with retroactive metadata flag.

    Uses the same suppression/severity logic as the main pipeline but
    adds retroactive markers to context_data.
    """
    from app.models.detection import Detection
    from app.services.detection_service import (
        check_suppression,
        compute_confidence_score,
        resolve_severity,
    )

    # Suppression check
    suppression = await check_suppression(session, rule.id, event.actor, event.org, event.repo)
    if suppression:
        return None

    severity = await resolve_severity(session, event.action, rule.default_severity)
    base_conf = rule.logic_config.get("confidence", 0.5)
    score, tier = compute_confidence_score(float(base_conf))

    x_config = rule.logic_config.get("x_config", {})
    campaign_id = x_config.get("campaign_id")

    ctx: dict[str, Any] = {
        "action": event.action,
        "event_id": event.id,
        "retroactive": True,
        "scan_initiated_at": scan_started_at,
    }

    detection = Detection(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=severity,
        confidence=tier,
        confidence_score=score,
        title=f"[Retro] {rule.name} — {event.actor or 'unknown'}",
        description=rule.description or rule.name,
        actor=event.actor,
        org=event.org,
        repo=event.repo,
        source_ip=str(event.source_ip) if event.source_ip else None,
        event_ids=[event.id],
        context_data=ctx,
        window_start=event.created_at,
        window_end=event.created_at,
        campaign_id=int(campaign_id) if campaign_id else None,
    )
    session.add(detection)
    await session.flush()

    logger.info(
        "retro_scan.detection_written",
        rule_id=rule.id,
        detection_id=detection.id,
        event_id=event.id,
        severity=severity,
    )

    return detection.id


async def _send_retro_scan_notification(
    session: AsyncSession,
    *,
    campaign_id: int,
    detections_created: int,
    events_scanned: int,
) -> None:
    """Log a summary notification about retro scan results.

    Individual retro detections trigger their own notifications through
    the standard detection notification pipeline. This logs the aggregate
    summary for operational visibility.
    """
    result = await session.execute(
        text("SELECT name FROM threat_intel_campaigns WHERE id = :cid"),
        {"cid": campaign_id},
    )
    row = result.fetchone()
    campaign_name = row[0] if row else f"Campaign #{campaign_id}"

    logger.info(
        "retro_scan.summary",
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        detections_created=detections_created,
        events_scanned=events_scanned,
        message=(
            f"Retro scan for '{campaign_name}' found "
            f"{detections_created} historical matches "
            f"across {events_scanned:,} events."
        ),
    )
