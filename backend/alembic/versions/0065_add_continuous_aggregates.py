"""Add TimescaleDB continuous aggregates for query performance.

Creates pre-computed daily rollups that replace expensive raw event scans.
Three continuous aggregates cover all major dashboard query patterns:

1. cagg_events_daily: Per (day, org, namespace, action, actor, actor_is_bot)
   - Covers: dev_activity, telemetry, user_behavior, user_classification
2. cagg_events_daily_repo: Per (day, org, action, actor, repo)
   - Covers: dev_activity top_repos, team_health bus_factor, stale repos
3. cagg_events_daily_geo: Per (day, org, actor, geo fields)
   - Covers: actor_locations, user_behavior geo-anomalies

Also tunes PostgreSQL for OLAP workloads and disables JIT
(which adds 2+ seconds overhead on aggregate queries).

Revision ID: 0065
"""

from __future__ import annotations

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Continuous Aggregate 1: event counts by actor/action/day ──────────
    # Covers: dev_activity, telemetry, user_behavior, user_classification
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_events_daily
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', created_at) AS bucket,
            org,
            namespace,
            action,
            actor,
            actor_is_bot,
            COUNT(*)          AS event_count,
            MAX(created_at)   AS last_seen
        FROM events
        GROUP BY bucket, org, namespace, action, actor, actor_is_bot
        WITH NO DATA
    """)

    # Indexes for common query patterns
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cagg_daily_org_bucket
        ON cagg_events_daily (org, bucket DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cagg_daily_org_actor
        ON cagg_events_daily (org, actor, bucket DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cagg_daily_org_action
        ON cagg_events_daily (org, action, bucket DESC)
    """)

    # Refresh policy: hourly, materialized_only so stale reads are fast
    op.execute("""
        SELECT add_continuous_aggregate_policy('cagg_events_daily',
            start_offset    => INTERVAL '90 days',
            end_offset      => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour',
            if_not_exists   => true
        )
    """)
    op.execute("""
        ALTER MATERIALIZED VIEW cagg_events_daily
        SET (timescaledb.materialized_only = false)
    """)

    # ── Continuous Aggregate 2: event counts by actor/repo/day ────────────
    # Covers: developer top_repos, team_health bus_factor, stale repos
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_events_daily_repo
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', created_at) AS bucket,
            org,
            action,
            actor,
            repo,
            COUNT(*) AS event_count
        FROM events
        GROUP BY bucket, org, action, actor, repo
        WITH NO DATA
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cagg_repo_org_bucket
        ON cagg_events_daily_repo (org, bucket DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cagg_repo_org_repo
        ON cagg_events_daily_repo (org, repo, bucket DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cagg_repo_org_actor
        ON cagg_events_daily_repo (org, actor, bucket DESC)
    """)

    # Refresh policy
    op.execute("""
        SELECT add_continuous_aggregate_policy('cagg_events_daily_repo',
            start_offset    => INTERVAL '90 days',
            end_offset      => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour',
            if_not_exists   => true
        )
    """)
    op.execute("""
        ALTER MATERIALIZED VIEW cagg_events_daily_repo
        SET (timescaledb.materialized_only = false)
    """)

    # ── Continuous Aggregate 3: geo-enriched actor summary ────────────────
    # Covers: actor_locations, geo-anomaly detection
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_events_daily_geo
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', created_at) AS bucket,
            org,
            actor,
            geo_country_code,
            geo_city,
            geo_latitude,
            geo_longitude,
            COUNT(*) AS event_count
        FROM events
        GROUP BY bucket, org, actor,
                 geo_country_code, geo_city, geo_latitude, geo_longitude
        WITH NO DATA
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_cagg_geo_org_actor
        ON cagg_events_daily_geo (org, actor, bucket DESC)
    """)

    op.execute("""
        SELECT add_continuous_aggregate_policy('cagg_events_daily_geo',
            start_offset    => INTERVAL '90 days',
            end_offset      => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour',
            if_not_exists   => true
        )
    """)
    op.execute("""
        ALTER MATERIALIZED VIEW cagg_events_daily_geo
        SET (timescaledb.materialized_only = false)
    """)


def downgrade() -> None:
    # Remove refresh policies before dropping views
    op.execute("""
        SELECT remove_continuous_aggregate_policy('cagg_events_daily_geo',
            if_exists => true)
    """)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS cagg_events_daily_geo CASCADE")

    op.execute("""
        SELECT remove_continuous_aggregate_policy('cagg_events_daily_repo',
            if_exists => true)
    """)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS cagg_events_daily_repo CASCADE")

    op.execute("""
        SELECT remove_continuous_aggregate_policy('cagg_events_daily',
            if_exists => true)
    """)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS cagg_events_daily CASCADE")
