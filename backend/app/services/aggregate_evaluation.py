"""Aggregate evaluation engine: classification + utilization rules."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# ─── Condition evaluation ─────────────────────────────────────────────────────


def _evaluate_condition(actor_metrics: dict[str, Any], condition: dict[str, Any]) -> bool:
    """Evaluate a single condition against actor metrics.

    Supported operators:
        gte, gt, lte, lt, eq — standard comparisons against field value
        pct_gt — field value as percentage of total_events exceeds threshold
    """
    field = condition["field"]
    op = condition["op"]
    value = condition["value"]

    actual = actor_metrics.get(field)
    if actual is None:
        return False

    if op == "gte":
        return float(actual) >= float(value)
    if op == "gt":
        return float(actual) > float(value)
    if op == "lte":
        return float(actual) <= float(value)
    if op == "lt":
        return float(actual) < float(value)
    if op == "eq":
        return bool(actual == value)
    if op == "pct_gt":
        total = actor_metrics.get("total_events", 0)
        if total == 0:
            return False
        pct = (float(actual) / float(total)) * 100.0
        return pct > float(value)

    logger.warning("aggregate_evaluation.unknown_operator", op=op)
    return False


# ─── Classification rules ────────────────────────────────────────────────────


def evaluate_classification_rules(
    actor_metrics: dict[str, Any],
    rules: list[dict[str, Any]],
) -> tuple[str, float]:
    """Evaluate ordered classification rules and return first match.

    Rules are evaluated in priority order (lowest priority number first).
    Each rule has a list of conditions that must ALL match (AND logic).

    Returns:
        (persona_name, confidence) — first matching rule's output, or
        ("Viewer", 0.5) as the fallback when no rule matches.
    """
    sorted_rules = sorted(rules, key=lambda r: r.get("priority", 999))

    for rule in sorted_rules:
        conditions = rule.get("conditions", [])
        # A single condition can be provided as "condition" (legacy)
        if not conditions and "condition" in rule:
            conditions = [rule["condition"]]

        if not conditions:
            continue

        all_match = all(_evaluate_condition(actor_metrics, c) for c in conditions)
        if all_match:
            persona = rule.get("output_persona", "Viewer")
            confidence = float(rule.get("confidence", 0.8))
            return persona, confidence

    return ("Viewer", 0.5)


# ─── IQR anomaly evaluation ──────────────────────────────────────────────────


async def evaluate_iqr_anomaly(
    db: AsyncSession,
    rule: dict[str, Any],
    actor_login: str,
    org_slug: str,
) -> dict[str, Any] | None:
    """Evaluate an IQR-based anomaly rule for a single actor.

    Looks up the behavioral baseline for the metric, computes the anomaly
    threshold using IQR, and compares against the current utilization value.

    Returns a detection dict if anomalous, None otherwise.
    """
    logic_config = rule.get("logic_config", {})
    metric_field = logic_config.get("metric_field", "")
    multiplier = float(logic_config.get("multiplier", 3.0))
    min_baseline_days = int(logic_config.get("min_baseline_days", 14))

    scope_key = f"{org_slug}/{actor_login}"

    # Fetch baseline
    baseline_result = await db.execute(
        text("""
            SELECT p25, p75, mean, stddev, sample_count, window_start, window_end
            FROM behavioral_baselines
            WHERE baseline_type = 'actor'
              AND scope_key = :scope_key
              AND metric_name = :metric_name
            ORDER BY window_end DESC
            LIMIT 1
        """),
        {"scope_key": scope_key, "metric_name": metric_field},
    )
    baseline_row = baseline_result.mappings().first()

    if baseline_row is None:
        logger.debug(
            "aggregate_evaluation.no_baseline",
            actor=actor_login,
            org=org_slug,
            metric=metric_field,
        )
        return None

    # Verify minimum baseline history
    window_start = baseline_row["window_start"]
    window_end = baseline_row["window_end"]
    baseline_days = (window_end - window_start).days
    if baseline_days < min_baseline_days:
        logger.debug(
            "aggregate_evaluation.insufficient_baseline",
            actor=actor_login,
            days=baseline_days,
            required=min_baseline_days,
        )
        return None

    p25 = float(baseline_row["p25"]) if baseline_row["p25"] is not None else 0.0
    p75 = float(baseline_row["p75"]) if baseline_row["p75"] is not None else 0.0
    iqr = p75 - p25

    # If IQR is zero, fall back to stddev-based threshold
    if iqr <= 0:
        stddev = float(baseline_row["stddev"]) if baseline_row["stddev"] else 0.0
        threshold = float(baseline_row["mean"]) + multiplier * stddev
    else:
        threshold = p75 + multiplier * iqr

    # Get current value from utilization_facts using validated column name
    safe_col = _safe_column_name(metric_field)
    query = (
        "SELECT "
        + safe_col
        + " AS current_value, metric_date"
        + " FROM utilization_facts"
        + " WHERE org_slug = :org_slug"
        + "   AND actor_login = :actor_login"
        + " ORDER BY metric_date DESC"
        + " LIMIT 1"
    )
    current_result = await db.execute(
        text(query),
        {"org_slug": org_slug, "actor_login": actor_login},
    )
    current_row = current_result.mappings().first()

    if current_row is None or current_row["current_value"] is None:
        return None

    current_value = float(current_row["current_value"])

    if current_value <= threshold:
        return None

    # Anomaly detected
    return {
        "rule_slug": rule.get("slug", "unknown"),
        "rule_id": rule.get("id"),
        "actor_login": actor_login,
        "org_slug": org_slug,
        "metric_field": metric_field,
        "current_value": current_value,
        "threshold": threshold,
        "p25": p25,
        "p75": p75,
        "iqr": iqr,
        "multiplier": multiplier,
        "severity": rule.get("default_severity", "medium"),
        "confidence": rule.get("default_confidence", "medium"),
        "triggered_at": datetime.now(tz=UTC),
    }


def _safe_column_name(name: str) -> str:
    """Validate and return a safe column name to prevent SQL injection."""
    allowed_columns = {
        "actions_minutes",
        "actions_runs",
        "copilot_suggestions",
        "copilot_acceptances",
        "copilot_credits",
        "ghas_alerts_dismissed",
        "git_clones",
        "git_pushes",
        "packages_published",
        "storage_bytes",
    }
    if name not in allowed_columns:
        raise ValueError(f"Invalid metric field: {name!r}")
    return name


# ─── Composite risk scoring ──────────────────────────────────────────────────


def evaluate_composite_risk(
    triggered_rules: list[dict[str, Any]],
    rule: dict[str, Any],
) -> float:
    """Compute a composite risk score from multiple triggered rule detections.

    Uses weighted scoring with exponential recency decay.

    Args:
        triggered_rules: list of detection dicts from previously triggered rules
        rule: the composite risk rule with logic_config containing:
            - contributing_rules: list of rule slugs that contribute to the score
            - weights: mapping of logic_type → weight multiplier
            - recency_decay_days: half-life for exponential decay

    Returns:
        Weighted composite score clamped to [0.0, 1.0].
    """
    logic_config = rule.get("logic_config", {})
    contributing_slugs = set(logic_config.get("contributing_rules", []))
    weights = logic_config.get("weights", {})
    recency_decay_days = float(logic_config.get("recency_decay_days", 30))

    if not triggered_rules or not contributing_slugs:
        return 0.0

    now = datetime.now(tz=UTC)
    total_weight = 0.0
    weighted_sum = 0.0

    for detection in triggered_rules:
        slug = detection.get("rule_slug", "")
        if slug not in contributing_slugs:
            continue

        logic_type = detection.get("logic_type", "threshold")
        weight = float(weights.get(logic_type, 1.0))

        # Compute recency decay
        triggered_at = detection.get("triggered_at")
        if triggered_at is None:
            decay = 1.0
        else:
            if isinstance(triggered_at, str):
                triggered_at = datetime.fromisoformat(triggered_at)
            age_days = max((now - triggered_at).total_seconds() / 86400.0, 0.0)
            # Exponential decay: e^(-ln(2) * age / half_life)
            if recency_decay_days > 0:
                decay = math.exp(-math.log(2) * age_days / recency_decay_days)
            else:
                decay = 1.0

        # Base severity score
        severity_score = _severity_to_score(detection.get("severity", "medium"))

        contribution = weight * decay * severity_score
        weighted_sum += contribution
        total_weight += weight

    if total_weight == 0.0:
        return 0.0

    # Normalize to [0, 1]
    raw_score = weighted_sum / total_weight
    return max(0.0, min(1.0, raw_score))


def _severity_to_score(severity: str) -> float:
    """Map severity string to a numeric score."""
    mapping = {
        "critical": 1.0,
        "high": 0.8,
        "medium": 0.5,
        "low": 0.25,
        "info": 0.1,
    }
    return mapping.get(severity.lower(), 0.5)


# ─── Main orchestrator ────────────────────────────────────────────────────────


async def run_aggregate_evaluation(
    db: AsyncSession,
    scoped_orgs: list[str] | None = None,
    *,
    mode: str = "all",
) -> dict[str, Any]:
    """Run classification + utilization rules against per-actor summaries.

    Steps:
    1. Query activity counts by category per actor (last 30 days)
    2. Query utilization_facts per actor (if available)
    3. Load classification rules (ordered by priority)
    4. Load utilization rules (iqr_anomaly + threshold)
    5. For each actor: evaluate classification → assign persona
    6. For each actor: evaluate utilization rules → collect triggered rules
    7. Compute composite risk scores from triggered rules
    8. Write persona + risk score to user_classifications table
    9. Write detections for high-severity utilization hits

    Args:
        db: async database session
        scoped_orgs: optional list of org slugs to scope evaluation
        mode: "classification", "utilization", or "all"

    Returns:
        Summary dict with counts.
    """
    summary: dict[str, Any] = {
        "actors_evaluated": 0,
        "classifications_written": 0,
        "utilization_detections": 0,
        "errors": 0,
    }

    try:
        # Build org filter
        org_filter = ""
        params: dict[str, Any] = {}
        if scoped_orgs:
            org_filter = "AND org IN :orgs"
            params["orgs"] = tuple(scoped_orgs)

        # Step 1: Get actor activity counts (last 30 days)
        window_start = datetime.now(tz=UTC) - timedelta(days=30)
        params["window_start"] = window_start

        base_query = (
            "SELECT"
            " actor,"
            " org,"
            " COUNT(*) AS total_events,"
            " COUNT(*) FILTER (WHERE action LIKE 'git%%') AS code_events,"
            " COUNT(*) FILTER ("
            "WHERE action LIKE 'org%%' OR action LIKE 'team%%'"
            ") AS admin_events,"
            " COUNT(*) FILTER (WHERE action LIKE 'repo%%') AS repo_events,"
            " BOOL_OR(actor LIKE '%%[bot]') AS actor_is_bot"
            " FROM audit_events"
            " WHERE created_at >= :window_start"
            f" {org_filter}"
            " GROUP BY actor, org"
            " HAVING COUNT(*) >= 5"
        )
        actors_result = await db.execute(text(base_query), params)
        actors = [dict(row) for row in actors_result.mappings().all()]

        if not actors:
            logger.info("aggregate_evaluation.no_actors_found")
            return summary

        summary["actors_evaluated"] = len(actors)

        # Step 3: Load classification rules
        classification_rules: list[dict[str, Any]] = []
        utilization_rules: list[dict[str, Any]] = []
        composite_rules: list[dict[str, Any]] = []

        rules_result = await db.execute(
            text("""
                SELECT id, slug, name, logic_type, logic_config,
                       default_severity, default_confidence
                FROM rule_definitions
                WHERE enabled = true
                  AND status = 'active'
                  AND logic_type IN ('classification', 'iqr_anomaly', 'composite_risk')
            """)
        )
        for row in rules_result.mappings().all():
            rule_dict = dict(row)
            lt = rule_dict["logic_type"]
            if lt == "classification":
                classification_rules.append(rule_dict)
            elif lt == "iqr_anomaly":
                utilization_rules.append(rule_dict)
            elif lt == "composite_risk":
                composite_rules.append(rule_dict)

        # Step 5-8: Evaluate per actor
        all_triggered: list[dict[str, Any]] = []

        for actor_row in actors:
            actor_login = actor_row["actor"]
            org_slug = actor_row["org"]

            if not actor_login or not org_slug:
                continue

            actor_metrics = {
                "code_events": actor_row.get("code_events", 0),
                "admin_events": actor_row.get("admin_events", 0),
                "repo_events": actor_row.get("repo_events", 0),
                "total_events": actor_row.get("total_events", 0),
                "actor_is_bot": actor_row.get("actor_is_bot", False),
            }

            # Classification
            if mode in ("all", "classification") and classification_rules:
                rule_configs = [r["logic_config"] for r in classification_rules]
                persona, confidence = evaluate_classification_rules(actor_metrics, rule_configs)

                await db.execute(
                    text("""
                        INSERT INTO user_classifications
                            (user_login, org, persona, confidence_score, event_count,
                             classified_at, created_at, updated_at)
                        VALUES
                            (:user_login, :org, :persona, :confidence_score, :event_count,
                             NOW(), NOW(), NOW())
                        ON CONFLICT (user_login, org)
                        DO UPDATE SET
                            persona = EXCLUDED.persona,
                            confidence_score = EXCLUDED.confidence_score,
                            event_count = EXCLUDED.event_count,
                            classified_at = NOW(),
                            updated_at = NOW()
                    """),
                    {
                        "user_login": actor_login,
                        "org": org_slug,
                        "persona": persona,
                        "confidence_score": confidence,
                        "event_count": actor_metrics["total_events"],
                    },
                )
                summary["classifications_written"] += 1

            # Utilization anomaly detection
            if mode in ("all", "utilization") and utilization_rules:
                for u_rule in utilization_rules:
                    try:
                        detection = await evaluate_iqr_anomaly(db, u_rule, actor_login, org_slug)
                        if detection:
                            all_triggered.append(detection)
                            summary["utilization_detections"] += 1
                    except Exception as exc:
                        logger.warning(
                            "aggregate_evaluation.rule_error",
                            rule_slug=u_rule.get("slug"),
                            actor=actor_login,
                            error=str(exc),
                        )
                        summary["errors"] += 1

        # Step 7: Composite risk scoring
        for c_rule in composite_rules:
            for actor_row in actors:
                actor_login = actor_row["actor"]
                org_slug = actor_row["org"]
                if not actor_login or not org_slug:
                    continue

                actor_triggered = [
                    t
                    for t in all_triggered
                    if t.get("actor_login") == actor_login and t.get("org_slug") == org_slug
                ]
                if actor_triggered:
                    risk_score = evaluate_composite_risk(actor_triggered, c_rule)
                    if risk_score > 0.0:
                        logger.info(
                            "aggregate_evaluation.composite_risk",
                            actor=actor_login,
                            org=org_slug,
                            score=risk_score,
                        )

        # Step 9: Write detections for high-severity utilization hits
        for detection in all_triggered:
            severity = detection.get("severity", "medium")
            if severity in ("high", "critical"):
                await db.execute(
                    text("""
                        INSERT INTO detections
                            (rule_id, rule_version, severity, confidence,
                             confidence_score, title, description, actor, org,
                             context_data, event_ids, triggered_at)
                        VALUES
                            (:rule_id, 1, :severity, :confidence,
                             0.75, :title, :description, :actor, :org,
                             :context_data, '{}', :triggered_at)
                    """),
                    {
                        "rule_id": detection["rule_id"],
                        "severity": severity,
                        "confidence": detection.get("confidence", "medium"),
                        "title": (
                            f"Utilization anomaly: {detection['metric_field']} "
                            f"for {detection['actor_login']}"
                        ),
                        "description": (
                            f"Actor {detection['actor_login']} in org {detection['org_slug']} "
                            f"has {detection['metric_field']}={detection['current_value']:.1f} "
                            f"exceeding threshold {detection['threshold']:.1f} "
                            f"(IQR method, multiplier={detection['multiplier']})"
                        ),
                        "actor": detection["actor_login"],
                        "org": detection["org_slug"],
                        "context_data": {
                            "metric_field": detection["metric_field"],
                            "current_value": detection["current_value"],
                            "threshold": detection["threshold"],
                            "p25": detection["p25"],
                            "p75": detection["p75"],
                            "iqr": detection["iqr"],
                        },
                        "triggered_at": detection["triggered_at"],
                    },
                )

        await db.commit()
        logger.info("aggregate_evaluation.completed", **summary)

    except Exception as exc:
        logger.error("aggregate_evaluation.failed", error=str(exc))
        await db.rollback()
        raise

    return summary
