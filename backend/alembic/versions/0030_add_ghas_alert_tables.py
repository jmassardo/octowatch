"""Add individual GHAS alert tables for secret scanning, code scanning, Dependabot.

Revision ID: 0029
Revises: 0028
"""

from __future__ import annotations

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Secret Scanning Alerts ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS secret_scanning_alerts (
            id                          BIGSERIAL PRIMARY KEY,
            org_slug                    VARCHAR(200)    NOT NULL,
            alert_number                INTEGER         NOT NULL,
            repo_full_name              VARCHAR(400)    NOT NULL,
            secret_type                 VARCHAR(200)    NOT NULL,
            secret_type_display         VARCHAR(400),
            file_path                   VARCHAR(1000),
            commit_sha                  VARCHAR(64),
            state                       VARCHAR(50)     NOT NULL,
            resolution                  VARCHAR(50),
            push_protection_bypassed    BOOLEAN         NOT NULL DEFAULT FALSE,
            push_protection_bypassed_by VARCHAR(200),
            created_at                  TIMESTAMPTZ     NOT NULL,
            resolved_at                 TIMESTAMPTZ,
            synced_at                   TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("""
        ALTER TABLE secret_scanning_alerts
            ADD CONSTRAINT uq_secret_scanning_alert
            UNIQUE (org_slug, repo_full_name, alert_number);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_secret_scanning_alert_org_state
            ON secret_scanning_alerts (org_slug, state);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_secret_scanning_alert_repo
            ON secret_scanning_alerts (repo_full_name);
    """)

    # ── Code Scanning Alerts ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS code_scanning_alerts (
            id                  BIGSERIAL PRIMARY KEY,
            org_slug            VARCHAR(200)    NOT NULL,
            alert_number        INTEGER         NOT NULL,
            repo_full_name      VARCHAR(400)    NOT NULL,
            rule_id             VARCHAR(200)    NOT NULL,
            rule_description    TEXT,
            severity            VARCHAR(50),
            security_severity   VARCHAR(50),
            cwe_ids             TEXT[],
            tool_name           VARCHAR(200),
            file_path           VARCHAR(1000),
            start_line          INTEGER,
            state               VARCHAR(50)     NOT NULL,
            dismissed_by        VARCHAR(200),
            dismissed_reason    VARCHAR(200),
            dismissed_at        TIMESTAMPTZ,
            created_at          TIMESTAMPTZ     NOT NULL,
            fixed_at            TIMESTAMPTZ,
            synced_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("""
        ALTER TABLE code_scanning_alerts
            ADD CONSTRAINT uq_code_scanning_alert
            UNIQUE (org_slug, repo_full_name, alert_number);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_code_scanning_alert_org_state
            ON code_scanning_alerts (org_slug, state);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_code_scanning_alert_repo
            ON code_scanning_alerts (repo_full_name);
    """)

    # ── Dependabot Alerts ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS dependabot_alerts (
            id                      BIGSERIAL PRIMARY KEY,
            org_slug                VARCHAR(200)        NOT NULL,
            alert_number            INTEGER             NOT NULL,
            repo_full_name          VARCHAR(400)        NOT NULL,
            package_name            VARCHAR(400)        NOT NULL,
            package_ecosystem       VARCHAR(100),
            severity                VARCHAR(50),
            cvss_score              DOUBLE PRECISION,
            cve_id                  VARCHAR(50),
            cwe_ids                 TEXT[],
            vulnerable_version_range VARCHAR(200),
            patched_version         VARCHAR(200),
            state                   VARCHAR(50)         NOT NULL,
            dismissed_by            VARCHAR(200),
            dismissed_reason        VARCHAR(200),
            created_at              TIMESTAMPTZ         NOT NULL,
            fixed_at                TIMESTAMPTZ,
            auto_dismissed_at       TIMESTAMPTZ,
            synced_at               TIMESTAMPTZ         NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("""
        ALTER TABLE dependabot_alerts
            ADD CONSTRAINT uq_dependabot_alert
            UNIQUE (org_slug, repo_full_name, alert_number);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dependabot_alert_org_state
            ON dependabot_alerts (org_slug, state);
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_dependabot_alert_repo
            ON dependabot_alerts (repo_full_name);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dependabot_alerts CASCADE;")
    op.execute("DROP TABLE IF EXISTS code_scanning_alerts CASCADE;")
    op.execute("DROP TABLE IF EXISTS secret_scanning_alerts CASCADE;")
