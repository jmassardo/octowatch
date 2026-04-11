"""Detection engine service: 8-step evaluation pipeline."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.detection import (
    BehavioralBaseline,
    Detection,
    DetectionSuppression,
    RuleDefinition,
    SeverityConfig,
)
from app.models.github_sync import (
    EnterpriseOrg,
    RepoBranchProtection,
    Repository,
)
from app.services.geoip_service import haversine_km, is_impossible_travel

logger = structlog.get_logger(__name__)


@dataclass
class PipelineResult:
    """Result of a detection pipeline run."""

    detections_written: int = 0
    detection_ids: list[int] = field(default_factory=list)
    failed_rules: list[int] = field(default_factory=list)


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
    org: str | None = None,
) -> Detection | None:
    """Check Step 2 of suppression: existing OPEN/INVESTIGATING detection in window."""
    cutoff = datetime.now(UTC) - timedelta(minutes=time_window_minutes)
    conditions = [
        Detection.rule_id == rule_id,
        Detection.actor == aggregation_key_value,
        Detection.status.in_(["open", "investigating"]),
        Detection.triggered_at >= cutoff,
    ]
    if org is not None:
        conditions.append(Detection.org == org)
    stmt = select(Detection).where(*conditions)
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

    # §1.2: Build group column expression for batched SQL
    # Column names are validated against a whitelist to prevent SQL injection
    if agg_key in _SAFE_DISTINCT_COLUMNS:
        group_col = agg_key
    elif agg_key.startswith("data."):
        sub_key = agg_key[5:]
        if not re.match(r"^[a-zA-Z0-9_]+$", sub_key):
            logger.warning("detection.invalid_agg_key", agg_key=agg_key)
            return []
        group_col = f"data->>'{sub_key}'"
    else:
        # Should not reach here due to early validation, but guard anyway
        logger.warning("detection.unsupported_agg_key", agg_key=agg_key)
        return []

    # §1.3: Count expression — raw count or distinct column values
    count_expr = (
        "COUNT(DISTINCT " + distinct_count_field + ")" if distinct_count_field else "COUNT(*)"
    )

    # Batch query: count per aggregation key value in one query
    batch_sql = (
        "SELECT " + group_col + " AS agg_val, " + count_expr + " AS cnt "
        "FROM events "
        "WHERE created_at >= :window_start "
        "AND " + group_col + " = ANY(:agg_values) "
        "AND action = ANY(:actions) "
        "AND org = ANY(:scoped_orgs) "
        "GROUP BY " + group_col
    )

    batch_result = await session.execute(
        text(batch_sql),
        {
            "window_start": window_start,
            "agg_values": list(agg_values),
            "actions": cleaned_actions,
            "scoped_orgs": scoped_orgs if scoped_orgs else [""],
        },
    )
    counts_by_agg = {row.agg_val: row.cnt for row in batch_result.fetchall()}

    for agg_value in agg_values:
        count = counts_by_agg.get(agg_value, 0)

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

        # Fetch all events for this actor in window (scoped to orgs)
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
              AND (:no_org_filter OR org = ANY(:scoped_orgs))
            ORDER BY created_at ASC
        """)
        result = await session.execute(
            stmt,
            {
                "actor": actor,
                "window_start": window_start,
                "no_org_filter": not scoped_orgs,
                "scoped_orgs": scoped_orgs if scoped_orgs else [""],
            },
        )
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


# ─── Off-hours anomaly detection ─────────────────────────────────────────────


async def _load_baseline(
    session: AsyncSession,
    baseline_type: str,
    scope_key: str,
    metric_name: str,
) -> BehavioralBaseline | None:
    """Load the latest baseline row for a given type/scope/metric."""
    stmt = (
        select(BehavioralBaseline)
        .where(
            BehavioralBaseline.baseline_type == baseline_type,
            BehavioralBaseline.scope_key == scope_key,
            BehavioralBaseline.metric_name == metric_name,
        )
        .order_by(BehavioralBaseline.window_end.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def evaluate_off_hours_anomaly(
    session: AsyncSession,
    rule: RuleDefinition,
    events: list[AuditEvent],
    scoped_orgs: list[str],
) -> list[dict[str, Any]]:
    """Evaluate off-hours anomaly: flag events outside actor's active hour range.

    If the event hour is outside (mean ± 2*stddev) of the actor's
    ``active_hours`` baseline, it is flagged. Falls back to org-level baseline
    if no actor baseline exists.
    """
    config = rule.logic_config
    z_multiplier = float(config.get("x_config", {}).get("z_multiplier", 2.0))

    candidates = [e for e in events if event_matches_rule(e, rule)]
    if not candidates:
        return []

    results: list[dict[str, Any]] = []

    for event in candidates:
        if not event.actor or not event.created_at:
            continue

        event_hour = float(event.created_at.hour)
        org = event.org or (scoped_orgs[0] if scoped_orgs else "")

        # Try actor-level baseline first
        actor_scope = f"actor:{event.actor}:org:{org}"
        baseline = await _load_baseline(session, "actor", actor_scope, "active_hours")

        # Fall back to org-level baseline
        if baseline is None and org:
            org_scope = f"org:{org}"
            baseline = await _load_baseline(session, "org", org_scope, "active_hours")

        if baseline is None:
            continue

        mean_hour = baseline.mean
        stddev_hour = baseline.stddev if baseline.stddev > 0 else 1.0

        # Check if event hour is outside normal range
        lower_bound = mean_hour - z_multiplier * stddev_hour
        upper_bound = mean_hour + z_multiplier * stddev_hour

        if lower_bound <= event_hour <= upper_bound:
            continue

        # Compute z-score for the event hour
        z_score = abs(event_hour - mean_hour) / stddev_hour

        results.append(
            {
                "aggregation_key_value": event.actor,
                "context_data": {
                    "event_hour": int(event_hour),
                    "baseline_mean_hour": round(mean_hour, 2),
                    "baseline_stddev_hour": round(stddev_hour, 2),
                    "z_score": round(z_score, 2),
                    "z_multiplier": z_multiplier,
                    "lower_bound": round(lower_bound, 2),
                    "upper_bound": round(upper_bound, 2),
                    "baseline_type": baseline.baseline_type,
                    "baseline_scope": baseline.scope_key,
                    "event_action": event.action,
                },
                "event_ids": [event.id],
                "window_start": event.created_at,
                "window_end": event.created_at,
                "org": org,
            }
        )

    return results


async def _write_off_hours_detection(
    session: AsyncSession,
    rule: RuleDefinition,
    hit: dict[str, Any],
    orgs: list[str],
) -> int | None:
    """Write an off-hours anomaly detection. Returns detection ID if new, else None."""
    actor = hit["aggregation_key_value"]
    ctx = hit.get("context_data", {})
    config = rule.logic_config

    suppression = await check_suppression(session, rule.id, actor, hit.get("org"), None)
    if suppression:
        return None

    window_minutes = config.get("time_window_minutes", 60)
    existing = await find_existing_detection(session, rule.id, actor, window_minutes)
    if existing:
        return None

    severity = await resolve_severity(session, "baseline.off_hours", rule.default_severity)
    base_conf = float(config.get("confidence", 0.55))
    z_score = ctx.get("z_score", 0.0)
    score, tier = compute_confidence_score(
        base_conf,
        actor_has_baseline=True,
        z_score=z_score,
        z_threshold=2.0,
    )

    detection = Detection(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=severity,
        confidence=tier,
        confidence_score=score,
        title=f"Off-Hours Activity — {actor}",
        description=(
            f"Actor {actor} performed action '{ctx.get('event_action', 'unknown')}' "
            f"at hour {ctx.get('event_hour', '?')} UTC, outside their normal "
            f"active hours (mean={ctx.get('baseline_mean_hour', 0):.1f}, "
            f"stddev={ctx.get('baseline_stddev_hour', 0):.1f}, "
            f"z-score={z_score:.1f})."
        ),
        actor=actor,
        org=hit.get("org") or (orgs[0] if orgs else None),
        event_ids=hit.get("event_ids", []),
        context_data=ctx,
        window_start=hit.get("window_start"),
        window_end=hit.get("window_end"),
    )
    session.add(detection)
    await session.flush()
    return detection.id


async def _adjust_threshold_with_baseline(
    session: AsyncSession,
    rule: RuleDefinition,
    agg_value: str,
    org: str | None,
    static_threshold: int,
) -> int:
    """If baseline_comparison is enabled, adjust threshold using the actor's baseline.

    Returns the dynamically adjusted threshold (or the original static value
    if no baseline is found).
    """
    config = rule.logic_config
    if not config.get("baseline_comparison", False):
        return static_threshold

    metric_name = config.get("baseline_metric", "daily_events")
    z_threshold = float(config.get("baseline_z_threshold", 3.0))

    # Try actor-level baseline
    scope_key = f"actor:{agg_value}:org:{org}" if org else f"actor:{agg_value}"
    baseline = await _load_baseline(session, "actor", scope_key, metric_name)

    # Fall back to org-level
    if baseline is None and org:
        baseline = await _load_baseline(session, "org", f"org:{org}", metric_name)

    if baseline is None:
        return static_threshold

    # Dynamic threshold = mean + z_threshold * stddev
    dynamic = int(baseline.mean + z_threshold * baseline.stddev)
    return max(dynamic, 1)


def _evaluate_dict_field_condition(event: dict[str, Any], condition: dict[str, Any]) -> bool:
    """Evaluate a single field_condition against an event dict (raw SQL row).

    Mirror of ``evaluate_field_condition`` but operates on plain dicts instead
    of AuditEvent ORM instances.  Supports the same operator set.
    """
    field_path: str = condition["field"]
    operator: str = condition["operator"]
    expected = condition.get("value")

    # Resolve field value — data.* keys are looked up inside the JSONB column
    if field_path.startswith("data."):
        key = field_path[5:]
        data = event.get("data")
        actual = data.get(key) if isinstance(data, dict) else None
    else:
        actual = event.get(field_path)

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
            return str(expected) in str(actual) if actual is not None else False
        case "not_contains":
            return str(expected) not in str(actual) if actual is not None else True
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


def _event_dict_matches_step(event: dict[str, Any], step: dict[str, Any]) -> bool:
    """Check if an event dict matches a step's action_filters and field_conditions."""
    step_actions: list[str] = step.get("action_filters", [])
    if step_actions and event.get("action") not in step_actions:
        return False

    field_conditions: list[dict[str, Any]] = step.get("field_conditions", [])
    return all(_evaluate_dict_field_condition(event, cond) for cond in field_conditions)


def _match_sequence_steps(
    events: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    window_minutes: int,
    require_distinct: bool,
) -> list[dict[str, Any]] | None:
    """Try to match all steps in sequence order within the time window.

    Returns the list of matched events (one per step minimum) or ``None`` if no
    complete match is found.  Events must appear in chronological order; each
    step is satisfied once *min_count* matching events have been found.
    """
    sorted_steps = sorted(steps, key=lambda s: s.get("step", 0))
    if not sorted_steps:
        return None

    first_step = sorted_steps[0]

    for i, event in enumerate(events):
        # Check if this event can start step 1
        if not _event_dict_matches_step(event, first_step):
            continue

        window_end = event["created_at"] + timedelta(minutes=window_minutes)
        matched: list[dict[str, Any]] = [event]
        used_ids: set[int] = {event["id"]} if require_distinct else set()

        current_step_idx = 0
        current_step_matches = 1
        first_min = first_step.get("min_count", 1)

        # Advance past step 1 if min_count is already satisfied
        if current_step_matches >= first_min:
            current_step_idx = 1
            current_step_matches = 0

        # Single-step rule already complete
        if current_step_idx >= len(sorted_steps):
            return matched

        # Scan remaining events for subsequent steps
        search_start = i + 1 if require_distinct else i
        for j in range(search_start, len(events)):
            if current_step_idx >= len(sorted_steps):
                break
            if events[j]["created_at"] > window_end:
                break
            if require_distinct and events[j]["id"] in used_ids:
                continue

            step = sorted_steps[current_step_idx]
            if _event_dict_matches_step(events[j], step):
                matched.append(events[j])
                if require_distinct:
                    used_ids.add(events[j]["id"])
                current_step_matches += 1

                if current_step_matches >= step.get("min_count", 1):
                    current_step_idx += 1
                    current_step_matches = 0

        if current_step_idx >= len(sorted_steps):
            return matched

    return None


async def evaluate_cross_namespace_sequence(
    session: AsyncSession,
    rule: RuleDefinition,
    scoped_orgs: list[str],
) -> list[dict[str, Any]]:
    """Evaluate a cross-namespace sequence rule.

    For each unique aggregation_key value (e.g. each actor), check if ALL steps
    in the sequence have matching events within the time window.  Steps are
    ordered and must occur in sequence (step 1 before step 2, etc.).

    Returns a list of hit dicts suitable for
    ``_write_cross_namespace_sequence_detection``.
    """
    config = rule.logic_config
    agg_key: str = config.get("aggregation_key", "actor")
    window_minutes: int = config.get("time_window_minutes", 120)
    require_distinct: bool = config.get("require_distinct_steps", True)
    steps: list[dict[str, Any]] = config.get("steps", [])

    if not steps:
        return []

    # Validate aggregation_key against whitelist
    if agg_key not in _SAFE_DISTINCT_COLUMNS:
        raise ValueError(f"aggregation_key '{agg_key}' is not a permitted column.")

    # Collect all action_filters across all steps
    all_actions: list[str] = []
    for step in steps:
        all_actions.extend(step.get("action_filters", []))

    if not all_actions:
        return []

    # Query events matching any step's action_filters within the window.
    # Compute cutoff in Python (same pattern as evaluate_threshold_rule) so the
    # SQL stays fully parameterised and TimescaleDB can still prune chunks.
    window_minutes_int = int(window_minutes)
    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes_int)
    result = await session.execute(
        text("""
            SELECT id, action, actor, org, repo, source_ip, created_at, data,
                   geo_country_code, user_agent
            FROM events
            WHERE action = ANY(:actions)
              AND org = ANY(:scoped_orgs)
              AND created_at >= :cutoff
            ORDER BY created_at ASC
        """),
        {
            "actions": all_actions,
            "scoped_orgs": scoped_orgs if scoped_orgs else [""],
            "cutoff": cutoff,
        },
    )

    rows = result.fetchall()
    if not rows:
        return []

    events_list: list[dict[str, Any]] = [dict(row._mapping) for row in rows]

    # Group events by aggregation key
    groups: dict[str, list[dict[str, Any]]] = {}
    for ev in events_list:
        key_val = ev.get(agg_key)
        if key_val is not None:
            key_str = str(key_val)
            groups.setdefault(key_str, []).append(ev)

    results: list[dict[str, Any]] = []

    for key_val, key_events in groups.items():
        key_events.sort(key=lambda e: e["created_at"])

        matched = _match_sequence_steps(key_events, steps, window_minutes_int, require_distinct)
        if not matched:
            continue

        first_event = matched[0]
        last_event = matched[-1]
        time_span = (last_event["created_at"] - first_event["created_at"]).total_seconds() / 60

        results.append(
            {
                "aggregation_key": agg_key,
                "aggregation_key_value": key_val,
                "matched_steps": len(steps),
                "time_span_minutes": round(time_span, 2),
                "event_ids": [e["id"] for e in matched],
                "matched_events": [
                    {
                        "action": e["action"],
                        "created_at": str(e["created_at"]),
                        "org": e.get("org"),
                    }
                    for e in matched
                ],
                "actor": (key_val if agg_key == "actor" else first_event.get("actor")),
                "org": first_event.get("org"),
                "repo": first_event.get("repo"),
                "source_ip": (
                    str(first_event["source_ip"]) if first_event.get("source_ip") else None
                ),
                "window_start": first_event["created_at"],
                "window_end": last_event["created_at"],
            }
        )

    return results


async def run_detection_pipeline(
    session: AsyncSession,
    event_ids: list[int],
    scoped_orgs: list[str] | None = None,
) -> PipelineResult:
    """Run the full 8-step detection pipeline for a batch of event IDs.

    Returns a :class:`PipelineResult` containing the number of new detections
    written and a list of rule IDs that failed evaluation.
    """
    if not event_ids:
        return PipelineResult()

    # Step 1: Fetch events
    stmt = (
        select(AuditEvent).where(AuditEvent.id.in_(event_ids)).order_by(AuditEvent.created_at.asc())
    )
    result = await session.execute(stmt)
    events = list(result.scalars().all())
    if not events:
        return PipelineResult()

    # Step 2: Load active rules
    rules_stmt = select(RuleDefinition).where(
        RuleDefinition.enabled.is_(True),
        RuleDefinition.status == "active",
    )
    rules_result = await session.execute(rules_stmt)
    rules = list(rules_result.scalars().all())

    if not rules:
        return PipelineResult()

    orgs = scoped_orgs or list({e.org for e in events if e.org})
    detections_written = 0
    detection_ids: list[int] = []
    failed_rules: list[int] = []

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
                    det_id = await _write_detection_for_event(session, rule, event, orgs)
                    if det_id is not None:
                        detections_written += 1
                        detection_ids.append(det_id)

            elif rule.logic_type == "threshold":
                hits = await evaluate_threshold_rule(session, rule, events, orgs)
                for hit in hits:
                    det_id = await _write_threshold_detection(session, rule, hit, orgs)
                    if det_id is not None:
                        detections_written += 1
                        detection_ids.append(det_id)

            elif rule.logic_type == "statistical" and engine == "impossible_travel":
                hits = await evaluate_impossible_travel(session, rule, events, orgs)
                for hit in hits:
                    det_id = await _write_impossible_travel_detection(session, rule, hit, orgs)
                    if det_id is not None:
                        detections_written += 1
                        detection_ids.append(det_id)

            elif rule.logic_type == "statistical" and engine == "off_hours_anomaly":
                hits = await evaluate_off_hours_anomaly(session, rule, events, orgs)
                for hit in hits:
                    det_id = await _write_off_hours_detection(session, rule, hit, orgs)
                    if det_id is not None:
                        detections_written += 1
                        detection_ids.append(det_id)

            elif rule.logic_type == "sequence":
                # Sequence evaluation is handled separately per-actor
                await _evaluate_sequence_rule(session, rule, events, orgs)

            elif rule.logic_type == "cross_namespace_sequence":
                hits = await evaluate_cross_namespace_sequence(session, rule, orgs)
                for hit in hits:
                    det_id = await _write_cross_namespace_sequence_detection(
                        session, rule, hit, orgs
                    )
                    if det_id is not None:
                        detections_written += 1
                        detection_ids.append(det_id)

        except Exception as exc:
            logger.error(
                "detection.rule_evaluation_failed",
                rule_id=rule.id,
                rule_name=rule.name,
                rule_slug=rule.slug,
                logic_type=rule.logic_type,
                error=str(exc),
                exc_info=True,
            )
            failed_rules.append(rule.id)

    if failed_rules:
        logger.warning(
            "detection.coverage_reduced",
            failed_rule_count=len(failed_rules),
            failed_rule_ids=failed_rules,
            total_rules=len(rules),
        )

    return PipelineResult(
        detections_written=detections_written,
        detection_ids=detection_ids,
        failed_rules=failed_rules,
    )


async def _write_detection_for_event(
    session: AsyncSession,
    rule: RuleDefinition,
    event: AuditEvent,
    orgs: list[str],
) -> int | None:
    """Write a pattern-rule detection for a single matching event.

    Returns the detection ID if written, or ``None`` if suppressed.
    """
    # Step 5: Suppression check
    suppression = await check_suppression(session, rule.id, event.actor, event.org, event.repo)
    if suppression:
        logger.debug(
            "detection.suppressed",
            rule_id=rule.id,
            suppression_id=suppression.id,
        )
        return None

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

    return detection.id


async def _write_threshold_detection(
    session: AsyncSession,
    rule: RuleDefinition,
    hit: dict[str, Any],
    orgs: list[str],
) -> int | None:
    """Write or update a threshold detection. Returns detection ID if new, else None."""
    agg_value = hit["aggregation_key_value"]
    config = rule.logic_config
    window_minutes: int = config.get("time_window_minutes", 60)

    # Suppression check
    suppression = await check_suppression(session, rule.id, agg_value, None, None)
    if suppression:
        return None

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
        return None

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
    return detection.id


async def _write_impossible_travel_detection(
    session: AsyncSession,
    rule: RuleDefinition,
    hit: dict[str, Any],
    orgs: list[str],
) -> int | None:
    """Write an impossible travel detection. Returns detection ID if new, else None."""
    actor = hit["aggregation_key_value"]
    ctx = hit.get("context_data", {})
    config = rule.logic_config

    suppression = await check_suppression(session, rule.id, actor, None, None)
    if suppression:
        return None

    window_minutes = config.get("time_window_minutes", 60)
    existing = await find_existing_detection(session, rule.id, actor, window_minutes)
    if existing:
        return None

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
    return detection.id


async def _write_cross_namespace_sequence_detection(
    session: AsyncSession,
    rule: RuleDefinition,
    hit: dict[str, Any],
    orgs: list[str],
) -> int | None:
    """Write a cross-namespace sequence detection. Returns detection ID if new, else None."""
    actor = hit.get("actor")
    agg_value: str = hit["aggregation_key_value"]
    config = rule.logic_config
    window_minutes: int = config.get("time_window_minutes", 120)

    # Suppression check
    suppression = await check_suppression(session, rule.id, actor, hit.get("org"), hit.get("repo"))
    if suppression:
        logger.debug(
            "detection.suppressed",
            rule_id=rule.id,
            suppression_id=suppression.id,
        )
        return None

    # Dedup: check for existing open detection
    existing = await find_existing_detection(session, rule.id, agg_value, window_minutes)
    if existing:
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
        return None

    # Severity resolution — use the first step's primary action
    first_action = config.get("steps", [{}])[0].get("action_filters", ["*"])[0]
    severity = await resolve_severity(session, first_action, rule.default_severity)

    # Confidence scoring
    base_conf = float(config.get("confidence", 0.5))
    score, tier = compute_confidence_score(base_conf, is_sequence_complete=True)

    agg_key = hit.get("aggregation_key", "actor")
    matched_steps = hit.get("matched_steps", 0)

    detection = Detection(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=severity,
        confidence=tier,
        confidence_score=score,
        title=f"{rule.name} — {agg_value}",
        description=(
            f"Cross-namespace sequence detected for {agg_key}={agg_value}. "
            f"All {matched_steps} steps matched within {window_minutes} minutes."
        ),
        actor=actor,
        org=hit.get("org") or (orgs[0] if orgs else None),
        repo=hit.get("repo"),
        source_ip=hit.get("source_ip"),
        event_ids=hit.get("event_ids", []),
        context_data={
            "aggregation_key": agg_key,
            "aggregation_key_value": agg_value,
            "matched_steps": matched_steps,
            "time_span_minutes": hit.get("time_span_minutes", 0),
            "matched_events": hit.get("matched_events", []),
        },
        window_start=hit.get("window_start"),
        window_end=hit.get("window_end"),
    )
    session.add(detection)
    await session.flush()

    logger.info(
        "detection.cross_namespace_sequence",
        rule_id=rule.id,
        detection_id=detection.id,
        severity=severity,
        confidence=tier,
        actor=actor,
        matched_steps=matched_steps,
    )

    return detection.id


async def _evaluate_sequence_rule(
    session: AsyncSession,
    rule: RuleDefinition,
    events: list[AuditEvent],
    orgs: list[str],
) -> None:
    """Evaluate a sequence rule by checking ordered event type occurrence per aggregation key.

    Supports aggregation by standard columns (actor, repo, org, etc.) and
    JSONB ``data.*`` keys (e.g. ``data.repo``, ``data.team``) using PostgreSQL
    ``->>`` extraction.
    """
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

    # Build column expression for WHERE clause (same approach as evaluate_threshold_rule).
    # Column names come from trusted rule config and are validated against a whitelist;
    # data.* keys use PostgreSQL JSONB extraction (->>) with regex-validated sub-keys.
    if agg_key in _SAFE_DISTINCT_COLUMNS:
        where_col = agg_key
    elif agg_key.startswith("data."):
        sub_key = agg_key[5:]
        if not re.match(r"^[a-zA-Z0-9_]+$", sub_key):
            logger.warning("detection.sequence_invalid_data_key", agg_key=agg_key)
            return
        where_col = f"data->>'{sub_key}'"
    else:
        logger.warning("detection.sequence_unsupported_agg_key", agg_key=agg_key)
        return

    seq_stmt = text(
        "SELECT id, action, created_at "
        "FROM events "
        "WHERE " + where_col + " = :agg_value "
        "AND action = ANY(:actions) "
        "AND created_at >= :window_start "
        "ORDER BY created_at ASC"
    )

    for agg_value in agg_values:
        window_start = datetime.now(UTC) - timedelta(minutes=window_minutes)

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


# ─── Posture assessment ───────────────────────────────────────────────────────

_POSTURE_OPS: dict[str, Any] = {
    "eq": lambda a, v: a == v,
    "ne": lambda a, v: a != v,
    "gt": lambda a, v: a is not None and a > v,
    "gte": lambda a, v: a is not None and a >= v,
    "lt": lambda a, v: a is not None and a < v,
    "lte": lambda a, v: a is not None and a <= v,
    "in": lambda a, v: a in v if v else False,
    "not_in": lambda a, v: a not in v if v else True,
}


async def run_posture_assessment(
    session: AsyncSession,
    run_id: str | None = None,
) -> int:
    """Evaluate posture rules against synced metadata.

    Unlike ``run_detection_pipeline`` which processes audit events,
    this evaluates the *current state* of the environment for insecure
    configurations.

    Returns the number of new detections created.
    """
    rules_result = await session.execute(
        select(RuleDefinition).where(
            RuleDefinition.enabled.is_(True),
            RuleDefinition.status == "active",
            RuleDefinition.logic_type == "posture",
        )
    )
    posture_rules = list(rules_result.scalars().all())
    if not posture_rules:
        return 0

    detections_written = 0
    active_dedup_keys: set[str] = set()

    for rule in posture_rules:
        config = rule.logic_config
        try:
            hits = await _evaluate_posture_rule(
                session,
                rule,
                config,
            )
            for hit in hits:
                dedup_key = hit["dedup_key"]
                active_dedup_keys.add(dedup_key)
                written = await _write_posture_detection(
                    session,
                    rule,
                    hit,
                )
                if written:
                    detections_written += 1
        except Exception as exc:
            logger.error(
                "detection.posture_rule_failed",
                slug=rule.slug,
                error=str(exc),
            )

    # Auto-resolve detections whose issues have been fixed
    await _auto_resolve_posture_detections(
        session,
        posture_rules,
        active_dedup_keys,
    )

    return detections_written


async def _evaluate_posture_rule(
    session: AsyncSession,
    rule: RuleDefinition,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate a single posture rule against synced metadata."""
    entity_type: str = config.get("entity_type", "")
    check_type: str = config.get("check_type", "field_value")

    if entity_type == "org":
        return await _evaluate_org_posture(session, rule, config)
    if entity_type == "repo":
        return await _evaluate_repo_posture(session, rule, config)
    if entity_type == "branch_protection":
        if check_type == "missing_protection":
            return await _evaluate_missing_bp(
                session,
                rule,
                config,
            )
        return await _evaluate_bp_posture(
            session,
            rule,
            config,
        )

    logger.warning(
        "detection.posture_unknown_entity",
        entity_type=entity_type,
        slug=rule.slug,
    )
    return []


async def _evaluate_org_posture(
    session: AsyncSession,
    rule: RuleDefinition,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate a posture rule against EnterpriseOrg rows."""
    field = config.get("field", "")
    operator = config.get("operator", "eq")
    expected_value = config.get("value")

    result = await session.execute(select(EnterpriseOrg))
    orgs = list(result.scalars().all())

    op_fn = _POSTURE_OPS.get(operator)
    if op_fn is None:
        return []

    hits: list[dict[str, Any]] = []
    for org_row in orgs:
        actual = getattr(org_row, field, None)
        if actual is None:
            continue
        if op_fn(actual, expected_value):
            hits.append(
                {
                    "org": org_row.org_login,
                    "repo": None,
                    "dedup_key": (f"posture:{rule.slug}:{org_row.org_login}:"),
                    "entity_type": "org",
                    "field": field,
                    "actual_value": actual,
                    "expected_value": expected_value,
                }
            )
    return hits


async def _evaluate_repo_posture(
    session: AsyncSession,
    rule: RuleDefinition,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate a posture rule against Repository rows."""
    field = config.get("field", "")
    operator = config.get("operator", "eq")
    expected_value = config.get("value")

    result = await session.execute(
        select(Repository).where(
            Repository.archived.is_(False),
        ),
    )
    repos = list(result.scalars().all())

    op_fn = _POSTURE_OPS.get(operator)
    if op_fn is None:
        return []

    hits: list[dict[str, Any]] = []
    for repo_row in repos:
        actual = getattr(repo_row, field, None)
        if actual is None:
            continue
        if op_fn(actual, expected_value):
            full = f"{repo_row.org}/{repo_row.repo_name}"
            hits.append(
                {
                    "org": repo_row.org,
                    "repo": full,
                    "dedup_key": (f"posture:{rule.slug}:{repo_row.org}:{repo_row.repo_name}"),
                    "entity_type": "repo",
                    "field": field,
                    "actual_value": actual,
                    "expected_value": expected_value,
                }
            )
    return hits


async def _evaluate_missing_bp(
    session: AsyncSession,
    rule: RuleDefinition,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Find repos whose default branch has no protection."""
    repo_result = await session.execute(
        select(Repository).where(
            Repository.archived.is_(False),
            Repository.default_branch.isnot(None),
        )
    )
    repos = list(repo_result.scalars().all())

    bp_result = await session.execute(
        select(RepoBranchProtection),
    )
    all_bps = list(bp_result.scalars().all())

    protected: set[tuple[str, str, str]] = {(bp.org, bp.repo_name, bp.branch) for bp in all_bps}

    hits: list[dict[str, Any]] = []
    for repo_row in repos:
        branch = repo_row.default_branch
        if not branch:
            continue
        key = (repo_row.org, repo_row.repo_name, branch)
        if key not in protected:
            full = f"{repo_row.org}/{repo_row.repo_name}"
            hits.append(
                {
                    "org": repo_row.org,
                    "repo": full,
                    "dedup_key": (f"posture:{rule.slug}:{repo_row.org}:{repo_row.repo_name}"),
                    "entity_type": "branch_protection",
                    "field": "missing",
                    "actual_value": None,
                    "expected_value": "branch_protection_exists",
                }
            )
    return hits


async def _evaluate_bp_posture(
    session: AsyncSession,
    rule: RuleDefinition,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Evaluate a posture rule against branch protection rows."""
    field = config.get("field", "")
    operator = config.get("operator", "eq")
    expected_value = config.get("value")

    result = await session.execute(select(RepoBranchProtection))
    bps = list(result.scalars().all())

    op_fn = _POSTURE_OPS.get(operator)
    if op_fn is None:
        return []

    hits: list[dict[str, Any]] = []
    for bp_row in bps:
        actual = getattr(bp_row, field, None)
        if actual is None:
            continue
        if op_fn(actual, expected_value):
            full = f"{bp_row.org}/{bp_row.repo_name}"
            hits.append(
                {
                    "org": bp_row.org,
                    "repo": full,
                    "dedup_key": (f"posture:{rule.slug}:{bp_row.org}:{bp_row.repo_name}"),
                    "entity_type": "branch_protection",
                    "field": field,
                    "actual_value": actual,
                    "expected_value": expected_value,
                }
            )
    return hits


async def _write_posture_detection(
    session: AsyncSession,
    rule: RuleDefinition,
    hit: dict[str, Any],
) -> bool:
    """Write a posture detection. Returns True if new.

    Deduplication uses a stable key in ``context_data["dedup_key"]``.
    """
    dedup_key = hit["dedup_key"]
    org = hit.get("org")
    repo = hit.get("repo")

    suppression = await check_suppression(
        session,
        rule.id,
        "system",
        org,
        repo,
    )
    if suppression:
        return False

    existing_result = await session.execute(
        select(Detection).where(
            Detection.rule_id == rule.id,
            Detection.status.in_(["open", "investigating"]),
            Detection.context_data["dedup_key"].astext == dedup_key,
        )
    )
    existing = existing_result.scalar_one_or_none()

    now = datetime.now(UTC)
    if existing:
        await session.execute(
            update(Detection)
            .where(Detection.id == existing.id)
            .values(
                updated_at=now,
                context_data={
                    **(existing.context_data or {}),
                    "entity_type": hit["entity_type"],
                    "field": hit["field"],
                    "actual_value": hit["actual_value"],
                    "expected_value": hit["expected_value"],
                    "dedup_key": dedup_key,
                    "last_assessed_at": now.isoformat(),
                },
            )
        )
        return False

    base_conf = float(
        rule.logic_config.get("confidence", 0.5),
    )
    score, tier = compute_confidence_score(base_conf)

    title_org = org or "unknown"
    detection = Detection(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=rule.default_severity,
        confidence=tier,
        confidence_score=score,
        title=f"{rule.name} — {title_org}",
        description=rule.description or rule.name,
        actor="system",
        org=org,
        repo=repo,
        event_ids=[],
        context_data={
            "entity_type": hit["entity_type"],
            "field": hit["field"],
            "actual_value": hit["actual_value"],
            "expected_value": hit["expected_value"],
            "dedup_key": dedup_key,
            "last_assessed_at": now.isoformat(),
        },
    )
    session.add(detection)
    await session.flush()

    logger.info(
        "detection.posture_written",
        rule_id=rule.id,
        detection_id=detection.id,
        slug=rule.slug,
        org=org,
        repo=repo,
    )
    return True


async def _auto_resolve_posture_detections(
    session: AsyncSession,
    posture_rules: list[RuleDefinition],
    active_dedup_keys: set[str],
) -> None:
    """Auto-resolve posture detections whose issues were fixed."""
    rule_ids = [r.id for r in posture_rules]
    if not rule_ids:
        return

    result = await session.execute(
        select(Detection).where(
            Detection.rule_id.in_(rule_ids),
            Detection.status.in_(["open", "investigating"]),
        )
    )
    open_detections = list(result.scalars().all())

    now = datetime.now(UTC)
    for det in open_detections:
        ctx = det.context_data or {}
        dedup_key = ctx.get("dedup_key", "")
        if not dedup_key:
            continue
        if dedup_key not in active_dedup_keys:
            await session.execute(
                update(Detection)
                .where(Detection.id == det.id)
                .values(
                    status="resolved",
                    resolved_at=now,
                    resolved_by="system",
                    resolution_note=("Auto-resolved: posture check passed"),
                    updated_at=now,
                )
            )
            logger.info(
                "detection.posture_auto_resolved",
                detection_id=det.id,
                dedup_key=dedup_key,
            )


# ─── Lightweight dry-run evaluator (no DB writes) ─────────────────────────────


def _evaluate_field_condition_dict(
    event_data: dict[str, Any],
    condition: dict[str, Any],
) -> bool:
    """Evaluate a single field_condition against a flat event dict.

    This mirrors ``evaluate_field_condition`` but works on a raw dict instead of
    an ORM ``AuditEvent`` instance, making it suitable for dry-run testing
    without requiring a database row.
    """
    field_path: str = condition.get("field", "")
    operator: str = condition.get("operator", "")
    expected = condition.get("value")

    # Resolve field value from nested data or top-level keys
    if field_path.startswith("data."):
        data_block = event_data.get("data", {}) or {}
        actual = data_block.get(field_path[5:])
    else:
        actual = event_data.get(field_path)

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
            return False


def evaluate_rule_against_event(
    rule: RuleDefinition,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate a rule against a sample event payload (dry-run, no side effects).

    Returns a dict with:
      - matched: bool
      - reason: str
      - matched_fields: list[str]  (fields that contributed to the match)
    """
    config: dict[str, Any] = rule.logic_config
    matched_fields: list[str] = []

    # ── Step 1: Action filter check ────────────────────────────────────────
    action_filters: list[str] = config.get("action_filters", [])
    event_action: str = event.get("action", "")

    if action_filters:
        action_matched = any(fnmatch.fnmatch(event_action, pat) for pat in action_filters)
        if not action_matched:
            return {
                "matched": False,
                "reason": (
                    f"Event action '{event_action}' does not match any "
                    f"action filter: {action_filters}"
                ),
                "matched_fields": [],
            }
        matched_fields.append("action")

    # ── Step 2: Field conditions check ─────────────────────────────────────
    field_conditions: list[dict[str, Any]] = config.get("field_conditions", [])
    for cond in field_conditions:
        field_name = cond.get("field", "")
        if not _evaluate_field_condition_dict(event, cond):
            return {
                "matched": False,
                "reason": (
                    f"Field condition failed: {field_name} "
                    f"{cond.get('operator', '?')} {cond.get('value', '')}"
                ),
                "matched_fields": matched_fields,
            }
        matched_fields.append(field_name)

    # ── Step 3: Confidence threshold check ─────────────────────────────────
    confidence_threshold = config.get("confidence")
    if confidence_threshold is not None:
        try:
            conf_val = float(confidence_threshold)
            # Map default_confidence tier to a numeric value for comparison
            confidence_map = {"high": 0.8, "medium": 0.5, "low": 0.2}
            rule_conf = confidence_map.get(rule.default_confidence, 0.5)
            if rule_conf < conf_val:
                return {
                    "matched": False,
                    "reason": (
                        f"Rule confidence ({rule.default_confidence}={rule_conf}) "
                        f"is below the configured threshold ({conf_val})"
                    ),
                    "matched_fields": matched_fields,
                }
            matched_fields.append("confidence")
        except (TypeError, ValueError):
            pass  # Skip if not a valid number

    # ── Step 4: Logic-type-specific checks ─────────────────────────────────
    if rule.logic_type == "threshold":
        threshold = config.get("threshold")
        if threshold is not None:
            matched_fields.append("threshold")

    if rule.logic_type == "sequence":
        sequence_steps = config.get("sequence_steps", [])
        if sequence_steps:
            # Check if the event action matches any step
            step_actions = [s.get("action", "") for s in sequence_steps]
            if event_action and not any(fnmatch.fnmatch(event_action, sa) for sa in step_actions):
                return {
                    "matched": False,
                    "reason": (
                        f"Event action '{event_action}' does not match any "
                        f"sequence step: {step_actions}"
                    ),
                    "matched_fields": matched_fields,
                }
            matched_fields.append("sequence_step")

    # ── All checks passed ──────────────────────────────────────────────────
    return {
        "matched": True,
        "reason": "Event matches all rule conditions",
        "matched_fields": matched_fields,
    }
