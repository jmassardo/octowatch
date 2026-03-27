"""Initial schema migration.

Creates all tables, indexes, hypertables, continuous aggregates, compression
policies, and seed data exactly as specified in docs/architecture.md §3.

Revision ID: 0001
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── Extensions ──────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ─── PostgreSQL roles ─────────────────────────────────────────────────────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rw') THEN
                CREATE ROLE app_rw;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_ro') THEN
                CREATE ROLE app_ro;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_query_user') THEN
                CREATE ROLE readonly_query_user LOGIN PASSWORD 'PLACEHOLDER_CHANGE_ME';
            END IF;
        END
        $$;
    """)

    # ─── 3.1 events ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE events (
            id               BIGSERIAL        NOT NULL,
            document_id      TEXT             NOT NULL,
            created_at       TIMESTAMPTZ      NOT NULL,
            ingested_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
            action           TEXT             NOT NULL,
            namespace        TEXT             NOT NULL GENERATED ALWAYS AS (
                                                  split_part(action, '.', 1)
                                              ) STORED,
            actor            TEXT,
            actor_id         BIGINT,
            actor_is_bot     BOOLEAN          NOT NULL DEFAULT FALSE,
            org              TEXT,
            org_id           BIGINT,
            repo             TEXT,
            repo_id          BIGINT,
            business         TEXT,
            business_id      BIGINT,
            source_ip        INET,
            user_agent       TEXT,
            geo_country_code CHAR(2),
            geo_city         TEXT,
            geo_latitude     DOUBLE PRECISION,
            geo_longitude    DOUBLE PRECISION,
            geo_is_proxy     BOOLEAN,
            data             JSONB            NOT NULL,
            ingestion_source TEXT             NOT NULL
                             CHECK (ingestion_source IN ('s3', 'azure_blob', 'minio')),
            source_file_path TEXT             NOT NULL,
            PRIMARY KEY (id, created_at)
        )
    """)

    op.execute("""
        SELECT create_hypertable(
            'events',
            'created_at',
            chunk_time_interval => INTERVAL '1 week',
            if_not_exists => TRUE
        )
    """)

    op.execute("""
        ALTER TABLE events SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'org, namespace',
            timescaledb.compress_orderby   = 'created_at DESC'
        )
    """)

    op.execute("SELECT add_compression_policy('events', INTERVAL '7 days')")

    op.execute("CREATE INDEX idx_events_actor ON events (actor, created_at DESC)")
    op.execute("CREATE INDEX idx_events_org ON events (org, created_at DESC)")
    op.execute("""
        CREATE INDEX idx_events_repo ON events (repo, created_at DESC)
        WHERE repo IS NOT NULL
    """)
    op.execute("CREATE INDEX idx_events_namespace ON events (namespace, created_at DESC)")
    op.execute("CREATE INDEX idx_events_action ON events (action, created_at DESC)")
    op.execute("""
        CREATE INDEX idx_events_source_ip ON events (source_ip, created_at DESC)
        WHERE source_ip IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_events_actor_is_bot ON events (actor_is_bot, created_at DESC)
        WHERE actor_is_bot = TRUE
    """)
    op.execute("CREATE INDEX idx_events_data_gin ON events USING GIN (data jsonb_path_ops)")

    # ─── 3.2 event_dedup ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE event_dedup (
            document_id  TEXT        PRIMARY KEY,
            event_id     BIGINT      NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL,
            ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ─── 3.3 event_raw_payloads ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE event_raw_payloads (
            id           BIGSERIAL   PRIMARY KEY,
            document_id  TEXT        NOT NULL UNIQUE,
            source_file  TEXT        NOT NULL,
            raw_json     JSONB       NOT NULL,
            event_id     BIGINT,
            ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_raw_payloads_event_id ON event_raw_payloads (event_id)
        WHERE event_id IS NOT NULL
    """)

    # ─── 3.4 ingestion_cursors ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ingestion_cursors (
            id                SERIAL      PRIMARY KEY,
            source_type       TEXT        NOT NULL
                              CHECK (source_type IN ('s3', 'azure_blob', 'minio')),
            source_name       TEXT        NOT NULL,
            source_region     TEXT,
            source_prefix     TEXT        NOT NULL DEFAULT '',
            last_prefix       TEXT        NOT NULL DEFAULT '',
            last_file         TEXT,
            last_event_count  BIGINT      NOT NULL DEFAULT 0,
            last_processed_at TIMESTAMPTZ,
            status            TEXT        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'paused', 'error', 'backfilling')),
            error_message     TEXT,
            error_count       INT         NOT NULL DEFAULT 0,
            poll_interval_sec INT         NOT NULL DEFAULT 300,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (source_type, source_name)
        )
    """)

    # ─── rbac_roles (must precede user_role_assignments) ─────────────────────
    op.execute("""
        CREATE TABLE rbac_roles (
            id           SERIAL      PRIMARY KEY,
            name         TEXT        NOT NULL UNIQUE
                         CHECK (name IN ('analyst', 'report_admin', 'rule_author', 'sys_admin')),
            display_name TEXT        NOT NULL,
            description  TEXT,
            permissions  JSONB       NOT NULL DEFAULT '[]',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        INSERT INTO rbac_roles (name, display_name, description, permissions) VALUES
        ('analyst', 'Analyst',
         'View and triage detections, run custom queries, view reports',
         '["events:read","detections:read","detections:update","reports:read","queries:run"]'),
        ('report_admin', 'Report Admin',
         'All Analyst permissions plus manage report exports and query templates',
         '["events:read","detections:read","detections:update","reports:read","reports:manage","queries:run","queries:manage","exports:create"]'),
        ('rule_author', 'Rule Author',
         'All Analyst permissions plus create and modify detection rules',
         '["events:read","detections:read","detections:update","reports:read","queries:run","rules:read","rules:write","rules:enable_disable","suppressions:manage"]'),
        ('sys_admin', 'System Admin',
         'Full administrative access including system configuration and RBAC management',
         '["*"]')
    """)

    # ─── user_role_assignments ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE user_role_assignments (
            id               BIGSERIAL    PRIMARY KEY,
            github_login     TEXT         NOT NULL,
            github_team_id   BIGINT,
            github_team_slug TEXT,
            saml_subject     TEXT,
            role_id          INT          NOT NULL REFERENCES rbac_roles(id),
            scope_type       TEXT         NOT NULL
                             CHECK (scope_type IN ('global', 'org', 'repo')),
            scope_value      TEXT,
            granted_by       TEXT         NOT NULL,
            granted_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            expires_at       TIMESTAMPTZ,
            active           BOOLEAN      NOT NULL DEFAULT TRUE,
            CONSTRAINT chk_scope_value CHECK (
                (scope_type = 'global' AND scope_value IS NULL)
                OR (scope_type IN ('org', 'repo') AND scope_value IS NOT NULL)
            )
        )
    """)

    # Expression-based uniqueness requires a unique index, not a constraint
    op.execute("""
        CREATE UNIQUE INDEX uq_role_assignments
        ON user_role_assignments (github_login, role_id, scope_type, COALESCE(scope_value, ''))
    """)

    op.execute("CREATE INDEX idx_role_assign_login ON user_role_assignments (github_login, active)")
    op.execute("""
        CREATE INDEX idx_role_assign_team ON user_role_assignments (github_team_id, active)
        WHERE github_team_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_role_assign_scope
        ON user_role_assignments (scope_type, scope_value, active)
    """)

    # ─── rule_definitions (must precede detections and detection_suppressions) ─
    op.execute("""
        CREATE TABLE rule_definitions (
            id                BIGSERIAL    PRIMARY KEY,
            name              TEXT         NOT NULL,
            slug              TEXT         NOT NULL UNIQUE,
            description       TEXT,
            category          TEXT         NOT NULL,
            default_severity  TEXT         NOT NULL
                              CHECK (default_severity IN ('critical', 'high', 'medium', 'low', 'info')),
            default_confidence TEXT        NOT NULL
                              CHECK (default_confidence IN ('high', 'medium', 'low')),
            logic_type        TEXT         NOT NULL
                              CHECK (logic_type IN ('threshold', 'pattern', 'sequence', 'statistical')),
            logic_config      JSONB        NOT NULL,
            enabled           BOOLEAN      NOT NULL DEFAULT TRUE,
            status            TEXT         NOT NULL DEFAULT 'active'
                              CHECK (status IN ('draft', 'active', 'deprecated')),
            version           INT          NOT NULL DEFAULT 1,
            git_commit_sha    TEXT,
            created_by        TEXT         NOT NULL,
            updated_by        TEXT,
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_rules_enabled ON rule_definitions (enabled, status)
        WHERE enabled = TRUE AND status = 'active'
    """)
    op.execute("CREATE INDEX idx_rules_category ON rule_definitions (category)")

    # ─── rule_versions ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE rule_versions (
            id             BIGSERIAL    PRIMARY KEY,
            rule_id        BIGINT       NOT NULL REFERENCES rule_definitions(id) ON DELETE CASCADE,
            version        INT          NOT NULL,
            logic_config   JSONB        NOT NULL,
            change_summary TEXT,
            changed_by     TEXT         NOT NULL,
            git_commit_sha TEXT,
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            UNIQUE (rule_id, version)
        )
    """)

    # ─── detection_suppressions (must precede detections) ────────────────────
    op.execute("""
        CREATE TABLE detection_suppressions (
            id              BIGSERIAL    PRIMARY KEY,
            rule_id         BIGINT       REFERENCES rule_definitions(id),
            suppress_actor  TEXT,
            suppress_org    TEXT,
            suppress_repo   TEXT,
            reason          TEXT         NOT NULL,
            created_by      TEXT         NOT NULL,
            expires_at      TIMESTAMPTZ,
            active          BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            CONSTRAINT chk_suppression_has_scope CHECK (
                suppress_actor IS NOT NULL
                OR suppress_org IS NOT NULL
                OR suppress_repo IS NOT NULL
                OR rule_id IS NOT NULL
            )
        )
    """)

    op.execute("""
        CREATE INDEX idx_suppressions_active ON detection_suppressions (active, expires_at)
        WHERE active = TRUE
    """)
    op.execute("""
        CREATE INDEX idx_suppressions_actor ON detection_suppressions (suppress_actor)
        WHERE suppress_actor IS NOT NULL AND active = TRUE
    """)
    op.execute("""
        CREATE INDEX idx_suppressions_org ON detection_suppressions (suppress_org)
        WHERE suppress_org IS NOT NULL AND active = TRUE
    """)

    # ─── 3.5 detections ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE detections (
            id              BIGSERIAL    PRIMARY KEY,
            rule_id         BIGINT       NOT NULL REFERENCES rule_definitions(id),
            rule_version    INT          NOT NULL,
            triggered_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            window_start    TIMESTAMPTZ,
            window_end      TIMESTAMPTZ,
            severity        TEXT         NOT NULL
                            CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
            confidence      TEXT         NOT NULL
                            CHECK (confidence IN ('high', 'medium', 'low')),
            confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            status          TEXT         NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'investigating', 'resolved', 'false_positive')),
            assigned_to     TEXT,
            title           TEXT         NOT NULL,
            description     TEXT         NOT NULL,
            actor           TEXT,
            org             TEXT,
            repo            TEXT,
            source_ip       INET,
            event_ids       BIGINT[]     NOT NULL DEFAULT '{}',
            context_data    JSONB        NOT NULL DEFAULT '{}',
            resolved_at     TIMESTAMPTZ,
            resolved_by     TEXT,
            resolution_note TEXT,
            suppressed_by   BIGINT       REFERENCES detection_suppressions(id),
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX idx_detections_status ON detections (status, triggered_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_detections_actor ON detections (actor, triggered_at DESC)
        WHERE actor IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_detections_org ON detections (org, triggered_at DESC)
        WHERE org IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX idx_detections_severity ON detections (severity, status, triggered_at DESC)
    """)
    op.execute("CREATE INDEX idx_detections_rule ON detections (rule_id, triggered_at DESC)")

    # ─── 3.6 detections daily summary (regular materialized view) ────────────
    op.execute("""
        CREATE MATERIALIZED VIEW detections_daily AS
            SELECT
                date_trunc('day', triggered_at) AS bucket_day,
                severity,
                status,
                COUNT(*) AS detection_count
            FROM detections
            GROUP BY 1, 2, 3
        WITH NO DATA
    """)

    # ─── 3.7 severity_configs ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE severity_configs (
            id               SERIAL      PRIMARY KEY,
            action_pattern   TEXT        NOT NULL UNIQUE,
            default_severity TEXT        NOT NULL
                             CHECK (default_severity IN ('critical', 'high', 'medium', 'low', 'info')),
            custom_severity  TEXT
                             CHECK (custom_severity IN ('critical', 'high', 'medium', 'low', 'info', NULL)),
            notes            TEXT,
            updated_by       TEXT,
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        INSERT INTO severity_configs (action_pattern, default_severity, notes) VALUES
        ('protected_branch.policy_override', 'critical', 'Branch protection bypass'),
        ('business.recovery_code_used',      'critical', 'Enterprise SSO bypass'),
        ('org.recovery_code_used',           'critical', 'Org SSO bypass'),
        ('secret_scanning_alert.reopen',     'high',     'Dismissed secret scanning alert reopened'),
        ('repo.destroy',                     'high',     'Repository deleted'),
        ('repo.transfer',                    'high',     'Repository transferred'),
        ('org.remove_member',                'medium',   'Member removed from org'),
        ('personal_access_token.access',     'low',      'PAT API access event'),
        ('*',                                'info',     'Default fallback severity')
    """)

    # ─── 3.8 behavioral_baselines ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE behavioral_baselines (
            id             BIGSERIAL         PRIMARY KEY,
            baseline_type  TEXT              NOT NULL,
            scope_key      TEXT              NOT NULL,
            metric_name    TEXT              NOT NULL,
            window_start   TIMESTAMPTZ       NOT NULL,
            window_end     TIMESTAMPTZ       NOT NULL,
            mean           DOUBLE PRECISION  NOT NULL,
            stddev         DOUBLE PRECISION  NOT NULL DEFAULT 0,
            p95            DOUBLE PRECISION  NOT NULL,
            p99            DOUBLE PRECISION  NOT NULL,
            sample_count   INT               NOT NULL,
            computed_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
            UNIQUE (baseline_type, scope_key, metric_name, window_start)
        )
    """)

    op.execute("""
        CREATE INDEX idx_baselines_lookup ON behavioral_baselines
        (baseline_type, scope_key, metric_name, window_end DESC)
    """)

    # ─── 3.9 audit_trail ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE audit_trail (
            id             BIGSERIAL    NOT NULL,
            timestamp      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            user_login     TEXT         NOT NULL,
            user_github_id BIGINT,
            ip_address     INET,
            user_agent     TEXT,
            action_type    TEXT         NOT NULL,
            resource_type  TEXT,
            resource_id    TEXT,
            parameters     JSONB,
            outcome        TEXT         NOT NULL
                           CHECK (outcome IN ('success', 'denied', 'error')),
            error_detail   TEXT,
            PRIMARY KEY (id, timestamp)
        )
    """)

    op.execute("""
        SELECT create_hypertable(
            'audit_trail',
            'timestamp',
            chunk_time_interval => INTERVAL '1 month',
            if_not_exists => TRUE
        )
    """)

    op.execute("""
        ALTER TABLE audit_trail SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'user_login',
            timescaledb.compress_orderby   = 'timestamp DESC'
        )
    """)

    op.execute("SELECT add_compression_policy('audit_trail', INTERVAL '30 days')")

    op.execute("CREATE INDEX idx_audit_trail_user ON audit_trail (user_login, timestamp DESC)")
    op.execute("CREATE INDEX idx_audit_trail_action ON audit_trail (action_type, timestamp DESC)")
    op.execute("""
        CREATE INDEX idx_audit_trail_resource ON audit_trail (resource_type, resource_id, timestamp DESC)
        WHERE resource_type IS NOT NULL
    """)

    # ─── 3.12 idp_actor_enrichments ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE idp_actor_enrichments (
            id                BIGSERIAL    PRIMARY KEY,
            github_login      TEXT         NOT NULL,
            idp_provider      TEXT         NOT NULL
                              CHECK (idp_provider IN ('okta', 'entra', 'google_workspace')),
            idp_user_id       TEXT,
            email             TEXT,
            display_name      TEXT,
            department        TEXT,
            title             TEXT,
            employment_status TEXT
                              CHECK (employment_status IN ('active', 'inactive', 'unknown')),
            manager_login     TEXT,
            location          TEXT,
            timezone          TEXT,
            raw_attributes    JSONB        NOT NULL DEFAULT '{}',
            last_synced_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            sync_error        TEXT,
            UNIQUE (github_login, idp_provider)
        )
    """)

    op.execute("""
        CREATE INDEX idx_idp_enrichments_login ON idp_actor_enrichments (github_login)
    """)

    # ─── 3.13 ticketing_configs and tickets ──────────────────────────────────
    op.execute("""
        CREATE TABLE ticketing_configs (
            id                     SERIAL      PRIMARY KEY,
            provider               TEXT        NOT NULL
                                   CHECK (provider IN ('jira', 'github_issues')),
            display_name           TEXT        NOT NULL,
            target                 TEXT        NOT NULL,
            project_key            TEXT,
            default_issue_type     TEXT        NOT NULL DEFAULT 'Bug',
            severity_priority_map  JSONB       NOT NULL DEFAULT '{}',
            auto_create            BOOLEAN     NOT NULL DEFAULT FALSE,
            auto_create_severities TEXT[]      NOT NULL DEFAULT ARRAY['critical', 'high'],
            credential_env_var     TEXT        NOT NULL,
            enabled                BOOLEAN     NOT NULL DEFAULT TRUE,
            created_by             TEXT        NOT NULL,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE tickets (
            id                  BIGSERIAL    PRIMARY KEY,
            ticketing_config_id INT          NOT NULL REFERENCES ticketing_configs(id),
            detection_id        BIGINT       NOT NULL REFERENCES detections(id),
            external_id         TEXT         NOT NULL,
            external_url        TEXT         NOT NULL,
            external_status     TEXT,
            created_by          TEXT         NOT NULL,
            created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            last_synced_at      TIMESTAMPTZ,
            UNIQUE (ticketing_config_id, detection_id)
        )
    """)

    op.execute("CREATE INDEX idx_tickets_detection_id ON tickets (detection_id)")

    # ─── 3.14 notification_configs ───────────────────────────────────────────
    op.execute("""
        CREATE TABLE notification_configs (
            id                     SERIAL      PRIMARY KEY,
            channel_type           TEXT        NOT NULL
                                   CHECK (channel_type IN ('slack', 'email')),
            display_name           TEXT        NOT NULL,
            target                 TEXT        NOT NULL,
            credential_env_var     TEXT,
            notify_severities      TEXT[]      NOT NULL DEFAULT ARRAY['critical', 'high'],
            cooldown_seconds       INT         NOT NULL DEFAULT 3600,
            enabled                BOOLEAN     NOT NULL DEFAULT TRUE,
            created_by             TEXT        NOT NULL,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ─── Continuous aggregates for events ────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW events_hourly
        WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 hour', created_at) AS bucket_hour,
                org,
                namespace,
                action,
                COUNT(*) AS event_count
            FROM events
            GROUP BY 1, 2, 3, 4
        WITH NO DATA
    """)

    op.execute("""
        SELECT add_continuous_aggregate_policy('events_hourly',
            start_offset => INTERVAL '6 hours',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour')
    """)

    op.execute("""
        CREATE MATERIALIZED VIEW events_daily_actor
        WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 day', created_at)  AS bucket_day,
                actor,
                org,
                namespace,
                COUNT(*) AS event_count
            FROM events
            WHERE actor IS NOT NULL
            GROUP BY 1, 2, 3, 4
        WITH NO DATA
    """)

    op.execute("""
        SELECT add_continuous_aggregate_policy('events_daily_actor',
            start_offset => INTERVAL '3 days',
            end_offset   => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour')
    """)

    # ─── Grant permissions ────────────────────────────────────────────────────
    op.execute("""
        GRANT SELECT ON events, detections, behavioral_baselines,
                        events_hourly, events_daily_actor, detections_daily
        TO readonly_query_user
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS events_daily_actor CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS events_hourly CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS detections_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS notification_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS tickets CASCADE")
    op.execute("DROP TABLE IF EXISTS ticketing_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS idp_actor_enrichments CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_trail CASCADE")
    op.execute("DROP TABLE IF EXISTS behavioral_baselines CASCADE")
    op.execute("DROP TABLE IF EXISTS severity_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS detections CASCADE")
    op.execute("DROP TABLE IF EXISTS detection_suppressions CASCADE")
    op.execute("DROP TABLE IF EXISTS rule_versions CASCADE")
    op.execute("DROP TABLE IF EXISTS rule_definitions CASCADE")
    op.execute("DROP TABLE IF EXISTS user_role_assignments CASCADE")
    op.execute("DROP TABLE IF EXISTS rbac_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS ingestion_cursors CASCADE")
    op.execute("DROP TABLE IF EXISTS event_raw_payloads CASCADE")
    op.execute("DROP TABLE IF EXISTS event_dedup CASCADE")
    op.execute("DROP TABLE IF EXISTS events CASCADE")
    op.execute("DROP ROLE IF EXISTS readonly_query_user")
    op.execute("DROP ROLE IF EXISTS app_ro")
    op.execute("DROP ROLE IF EXISTS app_rw")
