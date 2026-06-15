"""drop duplicate user_id indexes on asset_accounts

Revision ID: aj1_drop_duplicate_asset_account_indexes
Revises: ai1_add_market_condition_mode
Create Date: 2026-06-14
"""

from __future__ import annotations

from alembic import op

revision = "aj1_drop_duplicate_asset_account_indexes"
down_revision = "ai1_add_market_condition_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_asset_accounts_user_id", table_name="asset_accounts", if_exists=True)
    op.drop_index("idx_asset_accounts_user", table_name="asset_accounts", if_exists=True)


def downgrade() -> None:
    op.create_index("idx_asset_accounts_user_id", "asset_accounts", ["user_id"])
    op.create_index("idx_asset_accounts_user", "asset_accounts", ["user_id"])
