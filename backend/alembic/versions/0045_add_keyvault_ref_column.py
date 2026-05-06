"""Add keyvault_ref column to app_settings.

Revision ID: 0045
Revises: 0044
Create Date: 2026-05-13 00:00:00.000000+00:00

Adds a nullable ``keyvault_ref`` column to the ``app_settings`` table.
This stores the Key Vault secret name that corresponds to a given DB key,
enabling the transition from DB-encrypted secrets to Azure Key Vault.
The ``encrypted_value`` column is preserved for backward compatibility
during the migration period.
"""

import sqlalchemy as sa

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("keyvault_ref", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_settings", "keyvault_ref")
