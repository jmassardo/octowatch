"""Add org security settings columns to enterprise_orgs.

Stores security-relevant organisation settings synced via REST API
(two_factor_required, default_repo_permission, fork / public-repo policies,
IP allow-list flags) so posture-assessment rules can evaluate them.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE enterprise_orgs
        ADD COLUMN IF NOT EXISTS two_factor_required BOOLEAN,
        ADD COLUMN IF NOT EXISTS default_repo_permission TEXT,
        ADD COLUMN IF NOT EXISTS members_can_fork_private_repos BOOLEAN,
        ADD COLUMN IF NOT EXISTS members_can_create_public_repos BOOLEAN,
        ADD COLUMN IF NOT EXISTS ip_allow_list_enabled BOOLEAN,
        ADD COLUMN IF NOT EXISTS ip_allow_list_for_installed_apps_enabled BOOLEAN
    """)
    # Add 'posture' to the logic_type check constraint
    op.execute("""
        ALTER TABLE rule_definitions
        DROP CONSTRAINT IF EXISTS rule_definitions_logic_type_check
    """)
    op.execute("""
        ALTER TABLE rule_definitions
        ADD CONSTRAINT rule_definitions_logic_type_check
        CHECK (logic_type = ANY (ARRAY[
            'threshold', 'pattern', 'sequence', 'statistical',
            'cross_namespace_sequence', 'posture'
        ]))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE enterprise_orgs
        DROP COLUMN IF EXISTS two_factor_required,
        DROP COLUMN IF EXISTS default_repo_permission,
        DROP COLUMN IF EXISTS members_can_fork_private_repos,
        DROP COLUMN IF EXISTS members_can_create_public_repos,
        DROP COLUMN IF EXISTS ip_allow_list_enabled,
        DROP COLUMN IF EXISTS ip_allow_list_for_installed_apps_enabled
    """)
    # Restore original logic_type constraint
    op.execute("""
        ALTER TABLE rule_definitions
        DROP CONSTRAINT IF EXISTS rule_definitions_logic_type_check
    """)
    op.execute("""
        ALTER TABLE rule_definitions
        ADD CONSTRAINT rule_definitions_logic_type_check
        CHECK (logic_type = ANY (ARRAY[
            'threshold', 'pattern', 'sequence', 'statistical',
            'cross_namespace_sequence'
        ]))
    """)
