"""Add threat intel indicators, feeds tables and baseline upsert constraint.

Revision ID: 0028
Revises: 0027
"""

from __future__ import annotations

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Threat Intel Indicators ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS threat_intel_indicators (
            id               BIGSERIAL PRIMARY KEY,
            indicator_type   TEXT        NOT NULL,
            value            TEXT        NOT NULL,
            source           TEXT        NOT NULL,
            confidence       DOUBLE PRECISION NOT NULL DEFAULT 0.80,
            active           BOOLEAN     NOT NULL DEFAULT TRUE,
            added_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            added_by         TEXT        NOT NULL,
            expires_at       TIMESTAMPTZ,
            notes            TEXT,
            feed_id          BIGINT,
            metadata_json    JSONB
        );
    """)

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_indicators_type_value_unique
            ON threat_intel_indicators (indicator_type, value);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_indicators_type_value
            ON threat_intel_indicators (indicator_type, value);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_indicators_active
            ON threat_intel_indicators (active, indicator_type)
            WHERE active = TRUE;
    """)

    # ── Threat Intel Feeds ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS threat_intel_feeds (
            id                         BIGSERIAL PRIMARY KEY,
            name                       TEXT        NOT NULL,
            url                        TEXT        NOT NULL,
            feed_type                  TEXT        NOT NULL DEFAULT 'domain',
            enabled                    BOOLEAN     NOT NULL DEFAULT TRUE,
            refresh_interval_minutes   INTEGER     NOT NULL DEFAULT 1440,
            last_fetched_at            TIMESTAMPTZ,
            last_fetch_status          TEXT,
            last_indicator_count       INTEGER,
            created_by                 TEXT        NOT NULL,
            created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # ── Behavioral baselines: add unique constraint for upsert ───────────────
    # The baseline worker now does ON CONFLICT (baseline_type, scope_key, metric_name)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_baselines_upsert_key
            ON behavioral_baselines (baseline_type, scope_key, metric_name);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_baselines_upsert_key;")
    op.execute("DROP TABLE IF EXISTS threat_intel_feeds;")
    op.execute("DROP TABLE IF EXISTS threat_intel_indicators;")
