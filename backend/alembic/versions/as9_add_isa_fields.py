"""add isa_open_date, isa_type, isa_manual_cumulative_pnl_krw to asset_accounts

Revision ID: as9_add_isa_fields
Revises: as8_add_account_tax_type_and_horizon
Create Date: 2026-07-13 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "as9_add_isa_fields"
down_revision = "as8_add_account_tax_type_and_horizon"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("asset_accounts", sa.Column("isa_open_date", sa.Date(), nullable=True))
    op.add_column("asset_accounts", sa.Column("isa_type", sa.String(length=20), nullable=True))
    op.add_column(
        "asset_accounts",
        sa.Column("isa_manual_cumulative_pnl_krw", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("asset_accounts", "isa_manual_cumulative_pnl_krw")
    op.drop_column("asset_accounts", "isa_type")
    op.drop_column("asset_accounts", "isa_open_date")
