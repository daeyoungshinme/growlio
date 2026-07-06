"""remove open banking integration columns and constraints

Revision ID: ob1_remove_open_banking
Revises: cs2_composite_signal_user_level
Create Date: 2026-07-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ob1_remove_open_banking"
down_revision: str | None = "cs2_composite_signal_user_level"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_asset_accounts_ob_fintech_use_no", "asset_accounts", type_="unique")
    op.drop_column("asset_accounts", "ob_fintech_use_no")
    op.drop_column("asset_accounts", "ob_account_no_encrypted")
    op.drop_column("asset_accounts", "ob_bank_code")

    op.drop_column("user_settings", "ob_user_seq_no")
    op.drop_column("user_settings", "ob_refresh_token")
    op.drop_column("user_settings", "ob_token_expires_at")
    op.drop_column("user_settings", "ob_access_token")


def downgrade() -> None:
    op.add_column("user_settings", sa.Column("ob_access_token", sa.String(), nullable=True))
    op.add_column("user_settings", sa.Column("ob_token_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_settings", sa.Column("ob_refresh_token", sa.String(), nullable=True))
    op.add_column("user_settings", sa.Column("ob_user_seq_no", sa.String(20), nullable=True))

    op.add_column("asset_accounts", sa.Column("ob_bank_code", sa.String(10), nullable=True))
    op.add_column("asset_accounts", sa.Column("ob_account_no_encrypted", sa.String(200), nullable=True))
    op.add_column("asset_accounts", sa.Column("ob_fintech_use_no", sa.String(50), nullable=True))
    op.create_unique_constraint("uq_asset_accounts_ob_fintech_use_no", "asset_accounts", ["ob_fintech_use_no"])
