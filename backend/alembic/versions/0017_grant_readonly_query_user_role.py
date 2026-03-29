"""Grant readonly_query_user to the main database user for SET ROLE support.

The query explorer uses ``SET LOCAL ROLE readonly_query_user`` as
defense-in-depth so the database itself rejects writes even if
AST-level validation has a gap.  For ``SET ROLE`` to succeed the
current (main) database user must be a member of
``readonly_query_user``.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          EXECUTE format('GRANT readonly_query_user TO %I', current_user);
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'Could not grant readonly_query_user to %: %',
                       current_user, SQLERRM;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          EXECUTE format('REVOKE readonly_query_user FROM %I', current_user);
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'Could not revoke readonly_query_user from %: %',
                       current_user, SQLERRM;
        END
        $$;
        """
    )
