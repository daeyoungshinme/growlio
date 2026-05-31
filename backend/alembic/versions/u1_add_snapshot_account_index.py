"""Add index on asset_snapshots.account_id for account-specific lookups

Revision ID: u1_add_snapshot_account_index
Revises: t1_add_portfolio_sort_order
Create Date: 2026-05-31
"""

from alembic import op

revision = "u1_add_snapshot_account_index"
down_revision = "t1_add_portfolio_sort_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_asset_snapshots_account_date",
        "asset_snapshots",
        ["account_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_asset_snapshots_account_date", table_name="asset_snapshots")
