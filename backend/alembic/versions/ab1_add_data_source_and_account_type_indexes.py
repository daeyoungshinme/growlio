"""add_data_source_and_account_type_indexes

Revision ID: ab1_add_data_source_and_account_type_indexes
Revises: 2142c5b6b44a
Create Date: 2026-06-03

"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "ab1_add_ds_account_type_idx"
down_revision: str | None = "2142c5b6b44a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "idx_asset_accounts_data_source",
        "asset_accounts",
        ["user_id", "data_source"],
        unique=False,
    )
    op.create_index(
        "idx_transactions_account_type_date",
        "transactions",
        ["account_id", "transaction_type", "transaction_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_transactions_account_type_date", table_name="transactions")
    op.drop_index("idx_asset_accounts_data_source", table_name="asset_accounts")
