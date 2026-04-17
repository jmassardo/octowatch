"""Report service: TimescaleDB-backed metric aggregations for 8 report buckets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def _window_start(window_days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=window_days)


def _bucket_interval(granularity: str) -> timedelta:
    return {
        "daily": timedelta(days=1),
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
    }.get(granularity, timedelta(days=1))


async def get_mau_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Monthly Active Users (unique actors per time bucket)."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)  AS bucket,
            COUNT(DISTINCT actor)               AS unique_actors,
            COUNT(*)                            AS total_events
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND actor IS NOT NULL
        GROUP BY 1
        ORDER BY 1 ASC
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "unique_actors": row.unique_actors,
            "total_events": row.total_events,
        }
        for row in result.fetchall()
    ]


async def get_seat_utilization_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Seat utilization: active actors / licensed seat count per bucket.

    Returns ``active_seat_count`` (distinct actors per bucket),
    ``provisioned_seat_count`` (max active count across the window as a proxy
    for the licence ceiling) and ``utilization_pct``.
    """
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    # ------------------------------------------------------------------
    # 1. Proxy for provisioned_seat_count: max active actors in any bucket
    # ------------------------------------------------------------------
    max_stmt = text(f"""
        SELECT COALESCE(MAX(active_count), 0) AS max_active
        FROM (
            SELECT COUNT(DISTINCT actor) AS active_count
            FROM events
            WHERE created_at >= :start
              {org_filter}
              AND actor IS NOT NULL
            GROUP BY time_bucket(:interval, created_at)
        ) sub
    """)

    max_result = await session.execute(max_stmt, params)
    max_row = max_result.fetchone()
    provisioned_seat_count: int = max_row.max_active if max_row and max_row.max_active else 0

    # ------------------------------------------------------------------
    # 2. Per-bucket active seat counts
    # ------------------------------------------------------------------
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)  AS bucket,
            org,
            COUNT(DISTINCT actor)               AS active_seats
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND actor IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2
    """)

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "active_seat_count": row.active_seats,
            "provisioned_seat_count": provisioned_seat_count,
            "utilization_pct": (
                round(row.active_seats / provisioned_seat_count * 100, 1)
                if provisioned_seat_count > 0
                else 0.0
            ),
        }
        for row in result.fetchall()
    ]


async def get_repo_creation_rate_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Repository creation rate: repos.create events per time bucket."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            COUNT(*)                             AS repos_created,
            COUNT(DISTINCT actor)                AS unique_creators
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action = 'repos.create'
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "org": row.org,
            "repos_created": row.repos_created,
            "unique_creators": row.unique_creators,
        }
        for row in result.fetchall()
    ]


async def get_actions_volume_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """GitHub Actions workflow volume per time bucket with success/failure breakdown."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            COUNT(*)                             AS workflow_runs_total,
            COUNT(*) FILTER (WHERE action = 'workflow_run.success')
                AS workflow_runs_succeeded,
            COUNT(*) FILTER (WHERE action IN (
                'workflow_run.failure', 'workflow_run.startup_failure'
            ))  AS workflow_runs_failed,
            COUNT(DISTINCT actor)                AS unique_actors,
            COUNT(DISTINCT repo)                 AS unique_repos
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action LIKE 'workflow_run.%%'
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    rows = []
    for row in result.fetchall():
        total = row.workflow_runs_total or 0
        succeeded = row.workflow_runs_succeeded or 0
        success_pct = round(100.0 * succeeded / total, 2) if total > 0 else 0.0
        rows.append(
            {
                "bucket": row.bucket.isoformat(),
                "org": row.org,
                "workflow_runs": total,
                "workflow_runs_total": total,
                "workflow_runs_succeeded": succeeded,
                "workflow_runs_failed": row.workflow_runs_failed or 0,
                "success_rate_pct": success_pct,
                "unique_actors": row.unique_actors,
                "unique_repos": row.unique_repos,
            }
        )
    return rows


async def get_copilot_seats_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Copilot seat assignment / removal trends."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            action,
            COUNT(*)                             AS seat_events
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action IN (
              'copilot.enable_organization',
              'copilot.disable_organization',
              'copilot.add_seats',
              'copilot.remove_seats',
              'copilot.seat_allotment_added',
              'copilot.seat_allotment_removed'
          )
        GROUP BY 1, 2, 3
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    rows = result.fetchall()

    # Action categories matching the frontend CopilotSeatsBucket type
    _ASSIGN_ACTIONS = frozenset(
        {
            "copilot.add_seats",
            "copilot.seat_allotment_added",
            "copilot.enable_organization",
        }
    )
    _REVOKE_ACTIONS = frozenset(
        {
            "copilot.remove_seats",
            "copilot.seat_allotment_removed",
            "copilot.disable_organization",
        }
    )
    _POLICY_ACTIONS = frozenset(
        {
            "copilot.enable_organization",
            "copilot.disable_organization",
        }
    )

    # Pivot into per-bucket summaries with frontend-expected field names
    buckets: dict[str, dict] = {}
    for row in rows:
        key = row.bucket.isoformat()
        if key not in buckets:
            buckets[key] = {
                "bucket": key,
                "seats_assigned": 0,
                "seats_revoked": 0,
                "seats_net": 0,
                "policy_change_count": 0,
            }
        count: int = row.seat_events
        if row.action in _ASSIGN_ACTIONS:
            buckets[key]["seats_assigned"] += count
        if row.action in _REVOKE_ACTIONS:
            buckets[key]["seats_revoked"] += count
        if row.action in _POLICY_ACTIONS:
            buckets[key]["policy_change_count"] += count

    for bucket_data in buckets.values():
        bucket_data["seats_net"] = bucket_data["seats_assigned"] - bucket_data["seats_revoked"]

    return list(buckets.values())


async def get_codespace_hours_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Codespace billable hours aggregated from billing events."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)         AS bucket,
            org,
            COUNT(*)                                   AS codespace_events,
            COUNT(DISTINCT actor)                      AS unique_users,
            SUM((data->>'billable_hours')::numeric)    AS total_billable_hours
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action LIKE 'codespaces.%'
          AND data ? 'billable_hours'
        GROUP BY 1, 2
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "org": row.org,
            "codespace_events": row.codespace_events,
            "unique_users": row.unique_users,
            "total_billable_hours": float(row.total_billable_hours or 0),
        }
        for row in result.fetchall()
    ]


async def get_pat_counts_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Personal Access Token creation / deletion events per bucket."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            action,
            COUNT(*)                             AS pat_events,
            COUNT(DISTINCT actor)                AS unique_actors
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action IN (
              'personal_access_token.create',
              'personal_access_token.revoke',
              'personal_access_token.expire',
              'personal_access_token_request.create',
              'personal_access_token_request.deny',
              'personal_access_token_request.approve'
          )
        GROUP BY 1, 2, 3
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    rows = result.fetchall()

    buckets: dict[str, dict] = {}
    for row in rows:
        key = row.bucket.isoformat()
        if key not in buckets:
            buckets[key] = {"bucket": key, "org": row.org, "actions": {}}
        buckets[key]["actions"].setdefault(row.action, 0)
        buckets[key]["actions"][row.action] += row.pat_events

    return list(buckets.values())


async def get_webhook_counts_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "daily",
    org: str | None = None,
) -> list[dict]:
    """Webhook creation / deletion counts per bucket."""
    interval = _bucket_interval(granularity)
    start = _window_start(window_days)

    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at)   AS bucket,
            org,
            action,
            COUNT(*)                             AS webhook_events
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND action LIKE 'hook.%'
        GROUP BY 1, 2, 3
        ORDER BY 1 ASC, 2
    """)
    params: dict = {"interval": interval, "start": start}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    rows = result.fetchall()

    buckets: dict[str, dict] = {}
    for row in rows:
        key = row.bucket.isoformat()
        if key not in buckets:
            buckets[key] = {"bucket": key, "org": row.org, "actions": {}}
        buckets[key]["actions"].setdefault(row.action, 0)
        buckets[key]["actions"][row.action] += row.webhook_events

    return list(buckets.values())


async def get_top_actors_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    limit: int = 25,
    org: str | None = None,
) -> list[dict]:
    """Top actors by event count in window (admin endpoint)."""
    start = _window_start(window_days)
    org_filter = "AND org = :org" if org else ""
    stmt = text(f"""
        SELECT actor, COUNT(*) AS event_count
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND actor IS NOT NULL
        GROUP BY actor
        ORDER BY event_count DESC
        LIMIT :limit
    """)
    params: dict = {"start": start, "limit": limit}
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [{"actor": row.actor, "event_count": row.event_count} for row in result.fetchall()]


async def get_event_trend_report(
    session: AsyncSession,
    *,
    window_days: int = 30,
    granularity: str = "hourly",
    org: str | None = None,
) -> list[dict]:
    """Overall event volume trend. Uses pre-computed events_hourly if available."""
    start = _window_start(window_days)
    org_filter = "AND org = :org" if org else ""

    if granularity == "hourly":
        # Use pre-computed continuous aggregate
        stmt = text(f"""
            SELECT bucket, org, event_count, unique_actors
            FROM events_hourly
            WHERE bucket >= :start
              {org_filter}
            ORDER BY bucket ASC
        """)
    else:
        _interval = _bucket_interval(granularity)
        stmt = text(f"""
            SELECT
                time_bucket(:interval, created_at) AS bucket,
                org,
                COUNT(*) AS event_count,
                COUNT(DISTINCT actor) AS unique_actors
            FROM events
            WHERE created_at >= :start
              {org_filter}
            GROUP BY 1, 2
            ORDER BY 1 ASC
        """)

    params: dict = {"start": start}
    if granularity != "hourly":
        params["interval"] = _bucket_interval(granularity)
    if org:
        params["org"] = org

    result = await session.execute(stmt, params)
    return [
        {
            "bucket": row.bucket.isoformat(),
            "org": row.org,
            "event_count": row.event_count,
            "unique_actors": row.unique_actors,
        }
        for row in result.fetchall()
    ]


async def get_metrics_that_matter(
    session: AsyncSession,
    *,
    period_days: int = 30,
    org: str | None = None,
) -> dict:
    """Metrics That Matter: shipping faster/safer/cheaper KPIs from audit log events."""
    start = _window_start(period_days)
    org_filter = "AND org = :org" if org else ""
    week_interval = timedelta(days=7)

    params_base: dict = {"start": start}
    if org:
        params_base["org"] = org

    # ── Shipping Faster ──────────────────────────────────────────────────────

    # PR lifecycle: avg hours from open to merge using subquery join
    pr_lifecycle_stmt = text(f"""
        SELECT AVG(lifecycle_hours) AS avg_hours
        FROM (
            SELECT
                EXTRACT(EPOCH FROM (c.created_at - o.created_at)) / 3600.0 AS lifecycle_hours
            FROM (
                SELECT repo, payload->>'number' AS pr_num, created_at
                FROM events
                WHERE action = 'pull_request.opened'
                  AND created_at >= :start
                  AND actor NOT LIKE '%%[bot]'
                  {org_filter}
            ) o
            JOIN (
                SELECT repo, payload->>'number' AS pr_num, created_at
                FROM events
                WHERE action = 'pull_request.closed'
                  AND payload->>'merged' = 'true'
                  AND created_at >= :start
            ) c ON o.repo = c.repo AND o.pr_num = c.pr_num
            WHERE c.created_at > o.created_at
        ) sub
    """)
    pr_lifecycle_row = (await session.execute(pr_lifecycle_stmt, params_base)).fetchone()
    avg_pr_lifecycle_hours: float | None = (
        float(pr_lifecycle_row.avg_hours)
        if pr_lifecycle_row and pr_lifecycle_row.avg_hours is not None
        else None
    )

    # PR merge rate: % of PRs closed that were merged
    pr_rate_stmt = text(f"""
        SELECT
            COUNT(*) FILTER (WHERE payload->>'merged' = 'true') * 100.0 /
            NULLIF(COUNT(*), 0) AS merge_rate_pct
        FROM events
        WHERE action = 'pull_request.closed'
          AND created_at >= :start
          AND actor NOT LIKE '%%[bot]'
          {org_filter}
    """)
    pr_rate_row = (await session.execute(pr_rate_stmt, params_base)).fetchone()
    pr_merge_rate_pct: float | None = (
        float(pr_rate_row.merge_rate_pct)
        if pr_rate_row and pr_rate_row.merge_rate_pct is not None
        else None
    )

    # Deployment frequency per week
    deploy_stmt = text(f"""
        SELECT
            COUNT(*)::float / GREATEST(1, :period_days / 7.0) AS deploys_per_week
        FROM events
        WHERE action = 'workflow_run.completed'
          AND (
              payload->>'name' ILIKE '%%deploy%%'
              OR payload->>'name' ILIKE '%%release%%'
              OR payload->>'name' ILIKE '%%publish%%'
          )
          AND payload->>'conclusion' = 'success'
          AND created_at >= :start
          {org_filter}
    """)
    deploy_params = {**params_base, "period_days": period_days}
    deploy_row = (await session.execute(deploy_stmt, deploy_params)).fetchone()
    deployment_frequency_per_week: float | None = (
        float(deploy_row.deploys_per_week)
        if deploy_row and deploy_row.deploys_per_week is not None
        else None
    )

    # PR review rounds: approximated via review_requested events per PR
    review_rounds_stmt = text(f"""
        SELECT AVG(round_count) AS avg_rounds
        FROM (
            SELECT
                payload->>'number' AS pr_num,
                repo,
                COUNT(*) AS round_count
            FROM events
            WHERE action = 'pull_request.review_requested'
              AND created_at >= :start
              AND actor NOT LIKE '%%[bot]'
              {org_filter}
            GROUP BY payload->>'number', repo
        ) sub
    """)
    review_rounds_row = (await session.execute(review_rounds_stmt, params_base)).fetchone()
    avg_pr_review_rounds: float | None = (
        float(review_rounds_row.avg_rounds)
        if review_rounds_row and review_rounds_row.avg_rounds is not None
        else None
    )

    # Faster trend: weekly merged PR counts
    faster_trend_stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at) AS bucket,
            COUNT(*) FILTER (WHERE payload->>'merged' = 'true') AS merged_prs
        FROM events
        WHERE action = 'pull_request.closed'
          AND created_at >= :start
          {org_filter}
        GROUP BY 1
        ORDER BY 1 ASC
    """)
    faster_trend_rows = (
        await session.execute(faster_trend_stmt, {**params_base, "interval": week_interval})
    ).fetchall()
    faster_trend = [
        {
            "date": row.bucket.isoformat(),
            "avg_pr_hours": float(row.merged_prs) if row.merged_prs is not None else 0.0,
            "deployments": 0,
        }
        for row in faster_trend_rows
    ]

    # ── Shipping Safer ───────────────────────────────────────────────────────

    # Workflow success rate
    success_rate_stmt = text(f"""
        SELECT
            COUNT(*) FILTER (WHERE payload->>'conclusion' = 'success') * 100.0 /
            NULLIF(COUNT(*), 0) AS success_rate
        FROM events
        WHERE action = 'workflow_run.completed'
          AND created_at >= :start
          {org_filter}
    """)
    success_row = (await session.execute(success_rate_stmt, params_base)).fetchone()
    workflow_success_rate_pct: float | None = (
        float(success_row.success_rate)
        if success_row and success_row.success_rate is not None
        else None
    )

    # Security alerts
    alerts_stmt = text(f"""
        SELECT
            COUNT(*) FILTER (WHERE action = 'secret_scanning_alert.create') AS secrets_opened,
            COUNT(*) FILTER (WHERE action IN (
                'secret_scanning_alert.resolve',
                'secret_scanning_alert.revoke'
            )) AS secrets_resolved,
            COUNT(*) FILTER (
                WHERE action = 'code_scanning_alert.appeared_in_branch'
            ) AS codeql_opened,
            COUNT(*) FILTER (WHERE action IN (
                'code_scanning_alert.fixed',
                'code_scanning_alert.dismissed'
            )) AS codeql_closed
        FROM events
        WHERE created_at >= :start
          {org_filter}
    """)
    alerts_row = (await session.execute(alerts_stmt, params_base)).fetchone()
    secret_alerts_opened = int(alerts_row.secrets_opened) if alerts_row else 0
    secret_alerts_resolved = int(alerts_row.secrets_resolved) if alerts_row else 0
    codeql_alerts_opened = int(alerts_row.codeql_opened) if alerts_row else 0
    codeql_alerts_closed = int(alerts_row.codeql_closed) if alerts_row else 0

    # Branch protection compliance
    bp_stmt = text(f"""
        SELECT
            COUNT(DISTINCT repo) FILTER (
                WHERE action LIKE 'branch_protection%%'
            ) * 100.0 /
            NULLIF(COUNT(DISTINCT repo), 0) AS bp_compliance_pct
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND repo IS NOT NULL
    """)
    bp_row = (await session.execute(bp_stmt, params_base)).fetchone()
    branch_protection_compliance_pct: float | None = (
        float(bp_row.bp_compliance_pct) if bp_row and bp_row.bp_compliance_pct is not None else None
    )

    # Change failure rate: failed deploy workflows as % of all deploy workflows
    cfr_stmt = text(f"""
        SELECT
            COUNT(*) FILTER (WHERE
                payload->>'conclusion' IN ('failure', 'timed_out')
                AND (
                    payload->>'name' ILIKE '%%deploy%%'
                    OR payload->>'name' ILIKE '%%release%%'
                )
            ) * 100.0 /
            NULLIF(COUNT(*) FILTER (WHERE
                payload->>'name' ILIKE '%%deploy%%'
                OR payload->>'name' ILIKE '%%release%%'
            ), 0) AS cfr_pct
        FROM events
        WHERE action = 'workflow_run.completed'
          AND created_at >= :start
          {org_filter}
    """)
    cfr_row = (await session.execute(cfr_stmt, params_base)).fetchone()
    change_failure_rate_pct: float | None = (
        float(cfr_row.cfr_pct) if cfr_row and cfr_row.cfr_pct is not None else None
    )

    # Safer trend: weekly workflow success rate
    safer_trend_stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at) AS bucket,
            COUNT(*) FILTER (WHERE payload->>'conclusion' = 'success') * 100.0 /
            NULLIF(COUNT(*), 0) AS success_rate,
            COUNT(*) FILTER (WHERE action = 'code_scanning_alert.appeared_in_branch') -
            COUNT(*) FILTER (WHERE action IN (
                'code_scanning_alert.fixed', 'code_scanning_alert.dismissed'
            )) AS codeql_delta,
            COUNT(*) FILTER (WHERE action = 'secret_scanning_alert.create') -
            COUNT(*) FILTER (WHERE action IN (
                'secret_scanning_alert.resolve', 'secret_scanning_alert.revoke'
            )) AS secret_delta
        FROM events
        WHERE created_at >= :start
          {org_filter}
          AND (
              action = 'workflow_run.completed'
              OR action LIKE 'code_scanning_alert.%%'
              OR action LIKE 'secret_scanning_alert.%%'
          )
        GROUP BY 1
        ORDER BY 1 ASC
    """)
    safer_trend_rows = (
        await session.execute(safer_trend_stmt, {**params_base, "interval": week_interval})
    ).fetchall()
    safer_trend = [
        {
            "date": row.bucket.isoformat(),
            "success_rate": float(row.success_rate) if row.success_rate is not None else None,
            "codeql_delta": int(row.codeql_delta) if row.codeql_delta is not None else 0,
            "secret_delta": int(row.secret_delta) if row.secret_delta is not None else 0,
        }
        for row in safer_trend_rows
    ]

    # ── Shipping Cheaper ─────────────────────────────────────────────────────

    # Failed run waste %
    waste_stmt = text(f"""
        SELECT
            COUNT(*) FILTER (WHERE payload->>'conclusion' IN (
                'failure', 'timed_out', 'cancelled'
            )) * 100.0 /
            NULLIF(COUNT(*), 0) AS waste_pct
        FROM events
        WHERE action = 'workflow_run.completed'
          AND created_at >= :start
          {org_filter}
    """)
    waste_row = (await session.execute(waste_stmt, params_base)).fetchone()
    failed_run_waste_pct: float | None = (
        float(waste_row.waste_pct) if waste_row and waste_row.waste_pct is not None else None
    )

    # Rerun rate
    rerun_stmt = text(f"""
        SELECT
            COUNT(*) FILTER (WHERE (payload->>'run_attempt')::int > 1) * 100.0 /
            NULLIF(COUNT(*), 0) AS rerun_rate_pct
        FROM events
        WHERE action = 'workflow_run.completed'
          AND created_at >= :start
          AND payload ? 'run_attempt'
          {org_filter}
    """)
    rerun_row = (await session.execute(rerun_stmt, params_base)).fetchone()
    rerun_rate_pct: float | None = (
        float(rerun_row.rerun_rate_pct)
        if rerun_row and rerun_row.rerun_rate_pct is not None
        else None
    )

    # Automation merge rate: bot-merged PRs / total merged PRs
    auto_merge_stmt = text(f"""
        SELECT
            COUNT(*) FILTER (WHERE actor LIKE '%%[bot]' OR actor LIKE '%%bot%%') * 100.0 /
            NULLIF(COUNT(*), 0) AS automation_rate_pct
        FROM events
        WHERE action = 'pull_request.closed'
          AND payload->>'merged' = 'true'
          AND created_at >= :start
          {org_filter}
    """)
    auto_merge_row = (await session.execute(auto_merge_stmt, params_base)).fetchone()
    automation_merge_rate_pct: float | None = (
        float(auto_merge_row.automation_rate_pct)
        if auto_merge_row and auto_merge_row.automation_rate_pct is not None
        else None
    )

    # Top wasteful workflows
    top_wasteful_stmt = text(f"""
        SELECT
            payload->>'name' AS workflow_name,
            COUNT(*) FILTER (WHERE payload->>'conclusion' IN (
                'failure', 'timed_out', 'cancelled'
            )) * 100.0 /
            NULLIF(COUNT(*), 0) AS waste_pct
        FROM events
        WHERE action = 'workflow_run.completed'
          AND created_at >= :start
          AND payload->>'name' IS NOT NULL
          {org_filter}
        GROUP BY payload->>'name'
        HAVING COUNT(*) >= 3
        ORDER BY waste_pct DESC
        LIMIT 5
    """)
    top_wasteful_rows = (await session.execute(top_wasteful_stmt, params_base)).fetchall()
    top_wasteful_workflows = [
        {
            "workflow": row.workflow_name,
            "waste_pct": float(row.waste_pct) if row.waste_pct is not None else 0.0,
        }
        for row in top_wasteful_rows
    ]

    # Cheaper trend
    cheaper_trend_stmt = text(f"""
        SELECT
            time_bucket(:interval, created_at) AS bucket,
            COUNT(*) FILTER (WHERE payload->>'conclusion' IN (
                'failure', 'timed_out', 'cancelled'
            )) * 100.0 /
            NULLIF(COUNT(*), 0) AS failed_waste_pct,
            COUNT(*) FILTER (
                WHERE payload ? 'run_attempt' AND (payload->>'run_attempt')::int > 1
            ) * 100.0 /
            NULLIF(COUNT(*) FILTER (WHERE payload ? 'run_attempt'), 0) AS rerun_rate
        FROM events
        WHERE action = 'workflow_run.completed'
          AND created_at >= :start
          {org_filter}
        GROUP BY 1
        ORDER BY 1 ASC
    """)
    cheaper_trend_rows = (
        await session.execute(cheaper_trend_stmt, {**params_base, "interval": week_interval})
    ).fetchall()
    cheaper_trend = [
        {
            "date": row.bucket.isoformat(),
            "failed_waste_pct": (
                float(row.failed_waste_pct) if row.failed_waste_pct is not None else None
            ),
            "rerun_rate": float(row.rerun_rate) if row.rerun_rate is not None else None,
        }
        for row in cheaper_trend_rows
    ]

    return {
        "period_days": period_days,
        "generated_at": datetime.now(UTC).isoformat(),
        "shipping_faster": {
            "avg_pr_lifecycle_hours": avg_pr_lifecycle_hours,
            "avg_pr_review_rounds": avg_pr_review_rounds,
            "deployment_frequency_per_week": deployment_frequency_per_week,
            "pr_merge_rate_pct": pr_merge_rate_pct,
            "trend": faster_trend,
        },
        "shipping_safer": {
            "workflow_success_rate_pct": workflow_success_rate_pct,
            "codeql_alerts_opened": codeql_alerts_opened,
            "codeql_alerts_closed": codeql_alerts_closed,
            "secret_alerts_opened": secret_alerts_opened,
            "secret_alerts_resolved": secret_alerts_resolved,
            "branch_protection_compliance_pct": branch_protection_compliance_pct,
            "change_failure_rate_pct": change_failure_rate_pct,
            "trend": safer_trend,
        },
        "shipping_cheaper": {
            "failed_run_waste_pct": failed_run_waste_pct,
            "rerun_rate_pct": rerun_rate_pct,
            "automation_merge_rate_pct": automation_merge_rate_pct,
            "avg_pr_review_rounds": avg_pr_review_rounds,
            "top_wasteful_workflows": top_wasteful_workflows,
            "trend": cheaper_trend,
        },
    }
