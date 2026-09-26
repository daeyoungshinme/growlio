"""add income_bracket to user_settings

Revision ID: tx1_add_income_bracket
Revises: bs1_add_isa_baseline_fields
Create Date: 2026-09-26 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "tx1_add_income_bracket"
down_revision = "bs1_add_isa_baseline_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("income_bracket", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("user_settings", "income_bracket")
