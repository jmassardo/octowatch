"""Enhanced RBAC: system roles, permissions, migration from old roles.

Revision ID: 0039
Revises: 0038
Create Date: 2024-01-20 00:00:00.000000+00:00

This migration:
1. Adds is_system, is_custom, updated_at columns to rbac_roles
2. Drops the CHECK constraint on role names (allows new role names)
3. Seeds 7 predefined system roles
4. Maps old role assignments to new roles
5. Removes old roles after migration
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply enhanced RBAC schema changes."""
    # ─── 1. Add new columns to rbac_roles ─────────────────────────────────────
    op.execute("""
        ALTER TABLE rbac_roles
            ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS is_custom BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
    """)

    # ─── 2. Drop the CHECK constraint on role names ───────────────────────────
    # The original schema had: CHECK (name IN ('analyst', 'report_admin', 'rule_author', 'sys_admin'))
    # We need to drop it to allow new role names.
    op.execute("""
        DO $$
        DECLARE
            constraint_name TEXT;
        BEGIN
            SELECT conname INTO constraint_name
            FROM pg_constraint
            WHERE conrelid = 'rbac_roles'::regclass
              AND contype = 'c'
              AND pg_get_constraintdef(oid) LIKE '%name%';
            IF constraint_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE rbac_roles DROP CONSTRAINT %I', constraint_name);
            END IF;
        END $$
    """)

    # ─── 3. Mark existing roles as system roles ───────────────────────────────
    op.execute("""
        UPDATE rbac_roles SET is_system = true WHERE name IN (
            'analyst', 'report_admin', 'rule_author', 'sys_admin'
        )
    """)

    # ─── 4. Insert new system roles ───────────────────────────────────────────
    op.execute("""
        INSERT INTO rbac_roles (name, display_name, description, permissions, is_system, is_custom)
        VALUES
            ('super_admin', 'Super Admin',
             'Full administrative access to all features and settings',
             '["*:*"]',
             true, false),
            ('security_analyst', 'Security Analyst',
             'View and triage detections, run queries, view reports and dashboards',
             '["detections:*", "events:*", "queries:execute", "reports:view", "dashboard:view", "rules:view", "posture:view", "cross_org:view", "workflow_security:view", "copilot:view", "org_health:view", "playbooks:view", "playbooks:execute"]',
             true, false),
            ('security_engineer', 'Security Engineer',
             'All analyst permissions plus manage detection rules and playbooks',
             '["detections:*", "events:*", "queries:execute", "reports:view", "dashboard:view", "rules:*", "playbooks:*", "posture:view", "cross_org:view", "workflow_security:view", "copilot:view", "org_health:view"]',
             true, false),
            ('compliance_officer', 'Compliance Officer',
             'Security posture, reports, audit log access, and event viewing',
             '["posture:*", "reports:*", "audit_log:view", "events:view", "dashboard:view", "detections:view", "queries:execute", "rules:view", "cross_org:view", "workflow_security:view", "copilot:view", "org_health:view", "playbooks:view"]',
             true, false),
            ('engineering_leader', 'Engineering Leader',
             'Developer velocity, activity metrics, CI/CD health, and Copilot insights',
             '["velocity:*", "dev_activity:*", "workflow_health:*", "copilot:view", "dashboard:view"]',
             true, false),
            ('copilot_admin', 'Copilot Admin',
             'Full Copilot metrics and governance management',
             '["copilot:*", "dashboard:view"]',
             true, false),
            ('viewer', 'Viewer',
             'Read-only access to dashboards, events, and detections',
             '["dashboard:view", "events:view", "detections:view"]',
             true, false)
        ON CONFLICT (name) DO UPDATE SET
            display_name = EXCLUDED.display_name,
            description = EXCLUDED.description,
            permissions = EXCLUDED.permissions,
            is_system = true,
            is_custom = false,
            updated_at = NOW()
    """)

    # ─── 5. Migrate existing role assignments ─────────────────────────────────
    # Map old role names to new role names via role_id updates
    # sys_admin → super_admin
    op.execute("""
        UPDATE user_role_assignments
        SET role_id = (SELECT id FROM rbac_roles WHERE name = 'super_admin')
        WHERE role_id = (SELECT id FROM rbac_roles WHERE name = 'sys_admin')
    """)

    # report_admin → compliance_officer
    op.execute("""
        UPDATE user_role_assignments
        SET role_id = (SELECT id FROM rbac_roles WHERE name = 'compliance_officer')
        WHERE role_id = (SELECT id FROM rbac_roles WHERE name = 'report_admin')
    """)

    # rule_author → security_engineer
    op.execute("""
        UPDATE user_role_assignments
        SET role_id = (SELECT id FROM rbac_roles WHERE name = 'security_engineer')
        WHERE role_id = (SELECT id FROM rbac_roles WHERE name = 'rule_author')
    """)

    # analyst → security_analyst
    op.execute("""
        UPDATE user_role_assignments
        SET role_id = (SELECT id FROM rbac_roles WHERE name = 'security_analyst')
        WHERE role_id = (SELECT id FROM rbac_roles WHERE name = 'analyst')
    """)

    # ─── 6. Remove old roles ──────────────────────────────────────────────────
    op.execute("""
        DELETE FROM rbac_roles WHERE name IN (
            'analyst', 'report_admin', 'rule_author', 'sys_admin'
        )
    """)


def downgrade() -> None:
    """Revert enhanced RBAC schema changes.

    WARNING: This is a destructive downgrade. Custom roles created after
    the upgrade will be deleted.
    """
    # Re-insert old roles
    op.execute("""
        INSERT INTO rbac_roles (name, display_name, description, permissions, is_system)
        VALUES
            ('analyst', 'Analyst',
             'View and triage detections, run custom queries, view reports',
             '["events:read","detections:read","detections:update","reports:read","queries:run"]',
             true),
            ('report_admin', 'Report Admin',
             'All Analyst permissions plus manage report exports and query templates',
             '["events:read","detections:read","detections:update","reports:read","reports:manage","queries:run","queries:manage","exports:create"]',
             true),
            ('rule_author', 'Rule Author',
             'All Analyst permissions plus create and modify detection rules',
             '["events:read","detections:read","detections:update","reports:read","queries:run","rules:read","rules:write","rules:enable_disable","suppressions:manage"]',
             true),
            ('sys_admin', 'System Admin',
             'Full administrative access including system configuration and RBAC management',
             '["*"]',
             true)
        ON CONFLICT (name) DO NOTHING
    """)

    # Map new role assignments back to old roles
    op.execute("""
        UPDATE user_role_assignments
        SET role_id = (SELECT id FROM rbac_roles WHERE name = 'sys_admin')
        WHERE role_id = (SELECT id FROM rbac_roles WHERE name = 'super_admin')
    """)
    op.execute("""
        UPDATE user_role_assignments
        SET role_id = (SELECT id FROM rbac_roles WHERE name = 'report_admin')
        WHERE role_id = (SELECT id FROM rbac_roles WHERE name = 'compliance_officer')
    """)
    op.execute("""
        UPDATE user_role_assignments
        SET role_id = (SELECT id FROM rbac_roles WHERE name = 'rule_author')
        WHERE role_id = (SELECT id FROM rbac_roles WHERE name = 'security_engineer')
    """)
    op.execute("""
        UPDATE user_role_assignments
        SET role_id = (SELECT id FROM rbac_roles WHERE name = 'analyst')
        WHERE role_id = (SELECT id FROM rbac_roles WHERE name = 'security_analyst')
    """)

    # Remove new system roles
    op.execute("""
        DELETE FROM rbac_roles WHERE name IN (
            'super_admin', 'security_analyst', 'security_engineer',
            'compliance_officer', 'engineering_leader', 'copilot_admin', 'viewer'
        )
    """)

    # Remove new columns
    op.execute("""
        ALTER TABLE rbac_roles
            DROP COLUMN IF EXISTS is_system,
            DROP COLUMN IF EXISTS is_custom,
            DROP COLUMN IF EXISTS updated_at
    """)

    # Re-add the CHECK constraint
    op.execute("""
        ALTER TABLE rbac_roles
            ADD CONSTRAINT rbac_roles_name_check
            CHECK (name IN ('analyst', 'report_admin', 'rule_author', 'sys_admin'))
    """)
