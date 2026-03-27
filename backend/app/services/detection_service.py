"""Detection engine service: 8-step evaluation pipeline."""

from __future__ import annotations

import fnmatch
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.detection import (
    Detection,
    DetectionSuppression,
    RuleDefinition,
    SeverityConfig,
)
from app.services.geoip_service import haversine_km, is_impossible_travel

logger = structlog.get_logger(__name__)


# ─── Confidence scoring ───────────────────────────────────────────────────────


def compute_confidence_score(
    base_confidence: float,
    *,
    observed_count: int = 0,
    threshold: int = 0,
    distinct_ips: int = 1,
    actor_has_baseline: bool = False,
    is_proxy: bool = False,
    z_score: float | None = None,
    z_threshold: float | None = None,
    is_sequence_complete: bool = False,
    is_cold_start: bool = False,
    is_growing_history: bool = False,
    is_service_account: bool = False,
    is_marginal_threshold: bool = False,
    one_ip_is_vpn: bool = False,
) -> tuple[float, str]:
    """Compute final confidence score and tier using the documented formula.

    Returns (score 0.0-1.0, tier 'high'|'medium'|'low')
    """
    score = base_confidence
    positive = 1.0
    negative = 1.0

    # Positive factors
    if threshold > 0 and observed_count >= 2 * threshold:
        positive *= 1.20
    if is_proxy:
        positive *= 1.15
    if distinct_ips >= 2:
        positive *= 1.10
    if actor_has_baseline:
        positive *= 1.10
    if z_score is not None and z_threshold is not None and z_score >= 2 * z_threshold:
        positive *= 1.15
    if is_sequence_complete:
        positive *= 1.10

    # Negative factors
    if is_service_account:
        negative *= 0.85
    if is_marginal_threshold and observed_count > 0 and threshold > 0:
        if abs(observed_count - threshold) / threshold < 0.10:
            negative *= 0.90
    if is_cold_start:
        negative *= 0.75
    if is_growing_history:
        negative *= 0.75
    if one_ip_is_vpn:
        negative *= 0.70

    # Clamp to [0.0, 1.0]
    final = max(0.0, min(1.0, score * positive * negative))

    if final >= 0.75:
        tier = "high"
    elif final >= 0.45:
        tier = "medium"
    else:
        tier = "low"

    return final, tier


# ─── Severity resolution ─────────────────────────────────────────────────────


async def resolve_severity(
    session: AsyncSession,
    action: str,
    default_severity: str,
) -> str:
    """Resolve final severity: exact match > namespace wildcard > global fallback."""
    namespace = action.split(".")[0]
    candidates = [action, f"{namespace}.*", "*"]

    stmt = select(SeverityConfig).where(SeverityConfig.action_pattern.in_(candidates))
    result = await session.execute(stmt)
    configs = {c.action_pattern: c for c in result.scalars().all()}

    for pattern in candidates:
        if pattern in configs:
            cfg = configs[pattern]
            return cfg.custom_severity or cfg.default_severity

    return default_severity


# ─── Suppression check ────────────────────────────────────────────────────────


async def check_suppression(
    session: AsyncSession,
    rule_id: int,
    actor: str | None,
    org: str | None,
    repo: str | None,
) -> DetectionSuppression | None:
    """Check suppression rules in documented precedence order (§2g).

    Returns the first matching suppression, or None if not suppressed.
    """
    now = datetime.now(UTC)

    # Fetch all potentially matching suppressions in one query
    # (active=True AND not expired)
    stmt = select(DetectionSuppression).where(
        DetectionSuppression.active.is_(True),
        or_(
            DetectionSuppression.expires_at.is_(None),
            DetectionSuppression.expires_at > now,
        ),
        or_(
            DetectionSuppression.rule_id == rule_id,
            DetectionSuppression.rule_id.is_(None),
        ),
    )
    result = await session.execute(stmt)
    suppressions = result.scalars().all()

    # Apply precedence order in Python (as documented)
    # Check 3: Rule-level global suppression (rule matches, no scope)
    for s in suppressions:
        if (
            s.rule_id == rule_id
            and s.suppress_actor is None
            and s.suppress_org is None
            and s.suppress_repo is None
        ):
            return s

    # Check 4: Rule + actor
    for s in suppressions:
        if s.rule_id == rule_id and s.suppress_actor == actor and actor is not None:
            return s

    # Check 5: Rule + org
    for s in suppressions:
        if s.rule_id == rule_id and s.suppress_org == org and org is not None:
            return s

    # Check 6: Rule + repo
    for s in suppressions:
        if s.rule_id == rule_id and s.suppress_repo == repo and repo is not None:
            return s

    # Check 7: Global actor suppression (cross-rule)
    for s in suppressions:
        if s.rule_id is None and s.suppress_actor == actor and actor is not None:
            return s

    # Check 8: Global org suppression (cross-rule)
    for s in suppressions:
        if s.rule_id is None and s.suppress_org == org and org is not None:
            return s

    # Check 9: Global repo suppression (cross-rule)
    for s in suppressions:
        if s.rule_id is None and s.suppress_repo == repo and repo is not None:
            return s

    return None


# ─── Detection dedup ─────────────────────────────────────────────────────────


async def find_existing_detection(
    session: AsyncSession,
    rule_id: int,
    aggregation_key_value: str,
    time_window_minutes: int,
) -> Detection | None:
    """Check Step 2 of suppression: existing OPEN/INVESTIGATING detection in window."""
    cutoff = datetime.now(UTC) - timedelta(minutes=time_window_minutes)
    stmt = select(Detection).where(
        Detection.rule_id == rule_id,
        Detection.actor == aggregation_key_value,
        Detection.status.in_(["open", "investigating"]),
        Detection.triggered_at >= cutoff,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ─── Rule evaluation pipeline ─────────────────────────────────────────────────


def evaluate_field_condition(event: AuditEvent, condition: dict[str, Any]) -> bool:
    """Evaluate a single field_condition against an event.

    Supports: eq, ne, gt, gte, lt, lte, in, not_in, contains, not_contains,
    exists, not_exists, matches_glob, scope_contains operators.
    """
    field_path: str = condition["field"]
    operator: str = condition["operator"]
    expected = condition.get("value")

    # Resolve field value
    if field_path.startswith("data."):
        key = field_path[5:]
        actual = event.data.get(key) if event.data else None
    else:
        actual = getattr(event, field_path, None)

    # Operator dispatch
    match operator:
        case "eq":
            return actual == expected
        case "ne":
            return actual != expected
        case "gt":
            return actual is not None and actual > expected
        case "gte":
            return actual is not None and actual >= expected
        case "lt":
            return actual is not None and actual < expected
        case "lte":
            return actual is not None and actual <= expected
        case "in":
            return actual in expected if expected else False
        case "not_in":
            return actual not in expected if expected else True
        case "contains":
            return expected in str(actual) if actual is not None else False
        case "not_contains":
            return expected not in str(actual) if actual is not None else True
        case "exists":
            return actual is not None
        case "not_exists":
            return actual is None
        case "matches_glob":
            return fnmatch.fnmatch(str(actual or ""), str(expected or ""))
        case "scope_contains":
            if actual is None:
                return False
            tokens = {t.strip() for t in str(actual).replace(",", " ").split()}
            return str(expected) in tokens
        case _:
            logger.warning("detection.unknown_operator", operator=operator)
            return False


def event_matches_rule(event: AuditEvent, rule: RuleDefinition) -> bool:
    """Return True if an event passes action_filters AND all field_conditions."""
    config = rule.logic_config

    # Step 3: Action filter pass
    action_filters: list[str] = config.get("action_filters", [])
    if action_filters and not any(fnmatch.fnmatch(event.action, pat) for pat in action_filters):
        return False

    # Step 4: Field conditions (AND logic)
    field_conditions: list[dict[str, Any]] = config.get("field_conditions", [])
    for cond in field_conditions:
        if not evaluate_field_condition(event, cond):
            return False

    return True


# Columns safe to embed in aggregation-scope SQL filters (from trusted rule config)
_SAFE_AGG_COLUMNS: frozenset[str] = frozenset({"actor", "repo", "org"})

# Extended whitelist for distinct-count and aggregation-key validation (§2.1)
_SAFE_DISTINCT_COLUMNS: frozenset[str] = frozenset(
    {
        "actor",
        "org",
        "repo",
        "source_ip",
        "user_agent",
        "geo_country_code",
        "action",
    }
)


async def evaluate_threshold_rule(
    session: AsyncSession,
    rule: RuleDefinition,
    events: list[AuditEvent],
    scoped_orgs: list[str],
) -> list[dict[str, Any]]:
    """Evaluate a threshold rule. Returns list of matching aggregation_key_value hits."""
    config = rule.logic_config
    threshold: int = config.get("threshold", 1)
    window_minutes: int = config.get("time_window_minutes", 60)
    agg_key: str = config.get("aggregation_key", "actor")
    action_filters: list[str] = config.get("action_filters", [])

    # §1.6: Validate aggregation_key against whitelist
    if not agg_key.startswith("data.") and agg_key not in _SAFE_DISTINCT_COLUMNS:
        raise ValueError(f"aggregation_key '{agg_key}' is not a permitted column.")

    # §1.3: Validate distinct_count_field against whitelist
    distinct_count_field: str | None = config.get("distinct_count_field")
    if distinct_count_field is not None and distinct_count_field not in _SAFE_DISTINCT_COLUMNS:
        raise ValueError(
            f"distinct_count_field '{distinct_count_field}' is not a permitted column."
        )

    # §1.4: When action_filters is empty, skip evaluation entirely
    cleaned_actions = [a for a in action_filters if a != "*"]
    if not cleaned_actions:
        return []

    # Get distinct aggregation key values from matching events
    matching = [e for e in events if event_matches_rule(e, rule)]
    if not matching:
        return []

    # Collect unique agg key values
    agg_values: set[str] = set()
    for ev in matching:
        if agg_key.startswith("data."):
            val = ev.data.get(agg_key[5:]) if ev.data else None
        else:
            val = getattr(ev, agg_key, None)
        if val is not None:
            agg_values.add(str(val))

    results = []
    window_start = datetime.now(UTC) - timedelta(minutes=window_minutes)

    for agg_value in agg_values:
        # §1.2: Build aggregation key filter clause for SQL
        # Column names are validated against a whitelist to prevent SQL injection
        if agg_key in _SAFE_DISTINCT_COLUMNS:
            agg_filter_clause = "AND " + agg_key + " = :agg_value "
        elif agg_key.startswith("data."):
            sub_key = agg_key[5:]
            if not re.match(r"^[a-zA-Z0-9_]+$", sub_key):
                logger.warning("detection.invalid_agg_key", agg_key=agg_key)
                continue
            agg_filter_clause = "AND data->>'" + sub_key + "' = :agg_value "
        else:
            # Should not reach here due to early validation, but guard anyway
            logger.warning("detection.unsupported_agg_key", agg_key=agg_key)
            continue

        # §1.3: Count expression — raw count or distinct column values
        count_expr = (
            "COUNT(DISTINCT " + distinct_count_field + ")" if distinct_count_field else "COUNT(*)"
        )

        # Build SQL query — column names are from _SAFE_DISTINCT_COLUMNS whitelist
        query_sql = (
            "SELECT " + count_expr + " AS cnt "
            "FROM events "
            "WHERE created_at >= :window_start " + agg_filter_clause + " AND action = ANY(:actions)"
            " AND org = ANY(:scoped_orgs)"
        )

        result = await session.execute(
            text(query_sql),
            {
                "window_start": window_start,
                "agg_value": agg_value,
                "actions": cleaned_actions,
                "scoped_orgs": scoped_orgs if scoped_orgs else [""],
            },
        )
        row = result.fetchone()
        count = row[0] if row else 0

        if count >= threshold:
            results.append(
                {
                    "aggregation_key_value": agg_value,
                    "count": count,
                    "threshold": threshold,
                    "window_start": window_start,
                    "window_end": datetime.now(UTC),
                    "event_ids": [e.id for e in matching],
                }
            )

    return results


async def evaluate_impossible_travel(
    session: AsyncSession,
    rule: RuleDefinition,
    events: list[AuditEvent],
    scoped_orgs: list[str],
) -> list[dict[str, Any]]:
    """Evaluate impossible travel sub-engine (§2f)."""
    config = rule.logic_config
    x_config = config.get("x_config", {})
    window_minutes: int = config.get("time_window_minutes", 60)
    distance_threshold = float(x_config.get("distance_threshold_km", 500))
    speed_threshold = float(x_config.get("speed_threshold_kmh", 900))
    suppress_proxy = x_config.get("suppress_proxy_ips", True)

    # Filter matching events
    candidates = [e for e in events if event_matches_rule(e, rule)]
    if not candidates:
        return []

    # Group by actor
    actor_events: dict[str, list[AuditEvent]] = {}
    for ev in candidates:
        if ev.actor and ev.source_ip:
            actor_events.setdefault(ev.actor, []).append(ev)

    results = []

    for actor, actor_evs in actor_events.items():
        # Pre-check: actor_is_bot
        if any(e.actor_is_bot for e in actor_evs):
            continue

        # Fetch all events for this actor in window
        window_start = datetime.now(UTC) - timedelta(minutes=window_minutes)
        stmt = text("""
            SELECT id, created_at, source_ip,
                   geo_latitude, geo_longitude, geo_is_proxy
            FROM events
            WHERE actor = :actor
              AND created_at >= :window_start
              AND source_ip IS NOT NULL
              AND geo_latitude IS NOT NULL
              AND geo_longitude IS NOT NULL
            ORDER BY created_at ASC
        """)
        result = await session.execute(stmt, {"actor": actor, "window_start": window_start})
        recent_rows = result.fetchall()

        if len(recent_rows) < 2:
            continue

        # Check all consecutive pairs
        for i in range(len(recent_rows) - 1):
            e_a = recent_rows[i]
            e_b = recent_rows[i + 1]

            # Skip if same IP
            if str(e_a.source_ip) == str(e_b.source_ip):
                continue

            # Skip proxy/VPN IPs
            if suppress_proxy and (e_a.geo_is_proxy or e_b.geo_is_proxy):
                continue

            lat1, lon1 = e_a.geo_latitude, e_a.geo_longitude
            lat2, lon2 = e_b.geo_latitude, e_b.geo_longitude

            time_delta = (e_b.created_at - e_a.created_at).total_seconds()

            if is_impossible_travel(
                lat1,
                lon1,
                lat2,
                lon2,
                time_delta,
                distance_threshold_km=distance_threshold,
                speed_threshold_kmh=speed_threshold,
            ):
                distance = haversine_km(lat1, lon1, lat2, lon2)
                speed = distance / max(time_delta / 3600.0, 1 / 3600.0)

                results.append(
                    {
                        "aggregation_key_value": actor,
                        "context_data": {
                            "ip_a": str(e_a.source_ip),
                            "geo_a": {"lat": lat1, "lon": lon1},
                            "ip_b": str(e_b.source_ip),
                            "geo_b": {"lat": lat2, "lon": lon2},
                            "distance_km": round(distance, 1),
                            "time_delta_seconds": int(time_delta),
                            "implied_speed_kmh": round(speed, 1),
                            "event_id_a": e_a.id,
                            "event_id_b": e_b.id,
                        },
                        "event_ids": [e_a.id, e_b.id],
                        "window_start": window_start,
                        "window_end": datetime.now(UTC),
                    }
                )

    return results


async def run_detection_pipeline(
    session: AsyncSession,
    event_ids: list[int],
    scoped_orgs: list[str] | None = None,
) -> int:
    """Run the full 8-step detection pipeline for a batch of event IDs.

    Returns the number of new detections written.
    """
    if not event_ids:
        return 0

    # Step 1: Fetch events
    stmt = (
        select(AuditEvent).where(AuditEvent.id.in_(event_ids)).order_by(AuditEvent.created_at.asc())
    )
    result = await session.execute(stmt)
    events = list(result.scalars().all())
    if not events:
        return 0

    # Step 2: Load active rules
    rules_stmt = select(RuleDefinition).where(
        RuleDefinition.enabled.is_(True),
        RuleDefinition.status == "active",
    )
    rules_result = await session.execute(rules_stmt)
    rules = list(rules_result.scalars().all())

    if not rules:
        return 0

    orgs = scoped_orgs or list({e.org for e in events if e.org})
    detections_written = 0

    for rule in rules:
        config = rule.logic_config
        x_config = config.get("x_config", {})
        engine = x_config.get("engine", "")

        try:
            if rule.logic_type == "pattern":
                # Every matching event fires a detection
                for event in events:
                    if not event_matches_rule(event, rule):
                        continue
                    await _write_detection_for_event(session, rule, event, orgs)
                    detections_written += 1

            elif rule.logic_type == "threshold":
                hits = await evaluate_threshold_rule(session, rule, events, orgs)
                for hit in hits:
                    written = await _write_threshold_detection(session, rule, hit, orgs)
                    if written:
                        detections_written += 1

            elif rule.logic_type == "statistical" and engine == "impossible_travel":
                hits = await evaluate_impossible_travel(session, rule, events, orgs)
                for hit in hits:
                    written = await _write_impossible_travel_detection(session, rule, hit, orgs)
                    if written:
                        detections_written += 1

            elif rule.logic_type == "sequence":
                # Sequence evaluation is handled separately per-actor
                await _evaluate_sequence_rule(session, rule, events, orgs)

        except Exception as exc:
            logger.error(
                "detection.pipeline_error",
                rule_id=rule.id,
                rule_slug=rule.slug,
                error=str(exc),
            )

    return detections_written


async def _write_detection_for_event(
    session: AsyncSession,
    rule: RuleDefinition,
    event: AuditEvent,
    orgs: list[str],
) -> None:
    """Write a pattern-rule detection for a single matching event."""
    # Step 5: Suppression check
    suppression = await check_suppression(session, rule.id, event.actor, event.org, event.repo)
    if suppression:
        logger.debug(
            "detection.suppressed",
            rule_id=rule.id,
            suppression_id=suppression.id,
        )
        return

    # Step 6: Severity and confidence
    severity = await resolve_severity(session, event.action, rule.default_severity)
    base_conf = rule.logic_config.get("confidence", 0.5)
    score, tier = compute_confidence_score(float(base_conf))

    # Step 7: Write detection
    detection = Detection(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=severity,
        confidence=tier,
        confidence_score=score,
        title=f"{rule.name} — {event.actor or 'unknown'}",
        description=rule.description or rule.name,
        actor=event.actor,
        org=event.org,
        repo=event.repo,
        source_ip=str(event.source_ip) if event.source_ip else None,
        event_ids=[event.id],
        context_data={"action": event.action, "event_id": event.id},
        window_start=event.created_at,
        window_end=event.created_at,
    )
    session.add(detection)
    await session.flush()

    logger.info(
        "detection.written",
        rule_id=rule.id,
        detection_id=detection.id,
        severity=severity,
        confidence=tier,
    )


async def _write_threshold_detection(
    session: AsyncSession,
    rule: RuleDefinition,
    hit: dict[str, Any],
    orgs: list[str],
) -> bool:
    """Write or update a threshold detection. Returns True if new detection written."""
    agg_value = hit["aggregation_key_value"]
    config = rule.logic_config
    window_minutes: int = config.get("time_window_minutes", 60)

    # Suppression check
    suppression = await check_suppression(session, rule.id, agg_value, None, None)
    if suppression:
        return False

    # Dedup: check for existing open detection
    existing = await find_existing_detection(session, rule.id, agg_value, window_minutes)
    if existing:
        # Update existing detection (append event IDs, extend window)
        new_ids = list(set(existing.event_ids + hit.get("event_ids", [])))
        await session.execute(
            update(Detection)
            .where(Detection.id == existing.id)
            .values(
                event_ids=new_ids,
                window_end=hit.get("window_end", datetime.now(UTC)),
                updated_at=datetime.now(UTC),
            )
        )
        return False

    # New detection
    severity = await resolve_severity(
        session, config.get("action_filters", ["*"])[0], rule.default_severity
    )
    base_conf = float(config.get("confidence", 0.5))
    threshold = config.get("threshold", 1)
    observed = hit.get("count", 0)

    score, tier = compute_confidence_score(
        base_conf,
        observed_count=observed,
        threshold=threshold,
        is_marginal_threshold=observed < threshold * 1.1,
    )

    detection = Detection(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=severity,
        confidence=tier,
        confidence_score=score,
        title=f"{rule.name} — {agg_value}",
        description=(
            f"{rule.description or rule.name}\n\n"
            f"Observed {observed} events (threshold: {threshold}) "
            f"within {config.get('time_window_minutes', 60)} minutes."
        ),
        actor=agg_value,
        org=orgs[0] if orgs else None,
        event_ids=hit.get("event_ids", []),
        context_data={
            "aggregation_key_value": agg_value,
            "count": observed,
            "threshold": threshold,
        },
        window_start=hit.get("window_start"),
        window_end=hit.get("window_end"),
    )
    session.add(detection)
    await session.flush()
    return True


async def _write_impossible_travel_detection(
    session: AsyncSession,
    rule: RuleDefinition,
    hit: dict[str, Any],
    orgs: list[str],
) -> bool:
    """Write an impossible travel detection."""
    actor = hit["aggregation_key_value"]
    ctx = hit.get("context_data", {})
    config = rule.logic_config

    suppression = await check_suppression(session, rule.id, actor, None, None)
    if suppression:
        return False

    window_minutes = config.get("time_window_minutes", 60)
    existing = await find_existing_detection(session, rule.id, actor, window_minutes)
    if existing:
        return False

    severity = await resolve_severity(session, "geo.impossible_travel", rule.default_severity)
    base_conf = float(config.get("confidence", 0.65))
    one_ip_vpn = ctx.get("one_ip_is_vpn", False)
    score, tier = compute_confidence_score(base_conf, distinct_ips=2, one_ip_is_vpn=one_ip_vpn)

    detection = Detection(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=severity,
        confidence=tier,
        confidence_score=score,
        title=f"Impossible Travel — {actor}",
        description=(
            f"Actor {actor} accessed GitHub from two locations "
            f"{ctx.get('distance_km', 0):.0f} km apart within "
            f"{ctx.get('time_delta_seconds', 0) // 60} minutes.\n\n"
            f"IP A: {ctx.get('ip_a')} | IP B: {ctx.get('ip_b')}"
        ),
        actor=actor,
        org=orgs[0] if orgs else None,
        source_ip=ctx.get("ip_b"),
        event_ids=hit.get("event_ids", []),
        context_data=ctx,
        window_start=hit.get("window_start"),
        window_end=hit.get("window_end"),
    )
    session.add(detection)
    await session.flush()
    return True


async def _evaluate_sequence_rule(
    session: AsyncSession,
    rule: RuleDefinition,
    events: list[AuditEvent],
    orgs: list[str],
) -> None:
    """Evaluate a sequence rule by checking ordered event type occurrence per actor."""
    config = rule.logic_config
    steps: list[dict[str, Any]] = config.get("sequence_steps", [])
    if not steps:
        return

    window_minutes: int = config.get("time_window_minutes", 60)
    agg_key: str = config.get("aggregation_key", "actor")
    action_filters: list[str] = config.get("action_filters", [])

    candidates = [e for e in events if event_matches_rule(e, rule)]
    if not candidates:
        return

    # Get unique agg key values
    agg_values: set[str] = set()
    for ev in candidates:
        val = (
            getattr(ev, agg_key, None)
            if not agg_key.startswith("data.")
            else (ev.data or {}).get(agg_key[5:])
        )
        if val:
            agg_values.add(str(val))

    for agg_value in agg_values:
        window_start = datetime.now(UTC) - timedelta(minutes=window_minutes)

        # Fetch ordered events for this aggregation key
        seq_stmt = text("""
            SELECT id, action, created_at
            FROM events
            WHERE :agg_col = :agg_value
              AND action = ANY(:actions)
              AND created_at >= :window_start
            ORDER BY created_at ASC
        """)
        # We can't use dynamic column names safely, so use actor as agg key
        if agg_key == "actor":
            seq_stmt = text("""
                SELECT id, action, created_at
                FROM events
                WHERE actor = :agg_value
                  AND action = ANY(:actions)
                  AND created_at >= :window_start
                ORDER BY created_at ASC
            """)
        else:
            # For data.* aggregation keys, we skip sequence evaluation
            # (requires JSONB extraction; not implemented for beta)
            continue

        result = await session.execute(
            seq_stmt,
            {
                "agg_value": agg_value,
                "actions": [s["action"] for s in steps],
                "window_start": window_start,
            },
        )
        seq_events = result.fetchall()

        # Validate sequence: each step must appear in chronological order
        matched_ids: list[int] = []
        step_idx = 0
        for ev_row in seq_events:
            if step_idx >= len(steps):
                break
            if ev_row.action == steps[step_idx]["action"]:
                matched_ids.append(ev_row.id)
                step_idx += 1

        if step_idx < len(steps):
            continue  # Sequence incomplete

        # All steps matched
        suppression = await check_suppression(session, rule.id, agg_value, None, None)
        if suppression:
            continue

        existing = await find_existing_detection(session, rule.id, agg_value, window_minutes)
        if existing:
            continue

        severity = await resolve_severity(
            session, action_filters[0] if action_filters else "*", rule.default_severity
        )
        base_conf = float(config.get("confidence", 0.5))
        score, tier = compute_confidence_score(base_conf, is_sequence_complete=True)

        detection = Detection(
            rule_id=rule.id,
            rule_version=rule.version,
            severity=severity,
            confidence=tier,
            confidence_score=score,
            title=f"{rule.name} — {agg_value}",
            description=rule.description or rule.name,
            actor=agg_value if agg_key == "actor" else None,
            org=orgs[0] if orgs else None,
            event_ids=matched_ids,
            context_data={
                "sequence_steps": [s["action"] for s in steps],
                "aggregation_key_value": agg_value,
            },
            window_start=window_start,
            window_end=datetime.now(UTC),
        )
        session.add(detection)
        await session.flush()
