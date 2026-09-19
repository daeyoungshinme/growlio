"""add isa_baseline_auto_pnl_krw, isa_baseline_captured_at to asset_accounts

Revision ID: bs1_add_isa_baseline_fields
Revises: 3a44262845b3
Create Date: 2026-09-18 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "bs1_add_isa_baseline_fields"
down_revision = "3a44262845b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_accounts",
        sa.Column("isa_baseline_auto_pnl_krw", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "asset_accounts",
        sa.Column("isa_baseline_captured_at", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("asset_accounts", "isa_baseline_captured_at")
    op.drop_column("asset_accounts", "isa_baseline_auto_pnl_krw")
