"""add user_classifications table

Revision ID: 0059
Revises: 0058
Create Date: 2025-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_classifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_login", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("persona", sa.String(30), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("surfaces", JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("analysis_window_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column(
            "classified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_user_classifications_login_org",
        "user_classifications",
        ["user_login", "org"],
        unique=True,
    )
    op.create_index(
        "idx_user_classifications_persona",
        "user_classifications",
        ["persona"],
    )
    op.create_index(
        "idx_user_classifications_classified_at",
        "user_classifications",
        ["classified_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_classifications_classified_at", table_name="user_classifications")
    op.drop_index("idx_user_classifications_persona", table_name="user_classifications")
    op.drop_index("idx_user_classifications_login_org", table_name="user_classifications")
    op.drop_table("user_classifications")
