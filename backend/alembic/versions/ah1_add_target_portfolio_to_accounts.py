"""Add target_portfolio_id to asset_accounts for per-account target portfolio designation

Revision ID: ah1_add_target_portfolio_to_accounts
Revises: ag1_add_position_account_ticker_index
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "ah1_account_target_portfolio"
down_revision = "ag1_position_ticker_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_accounts",
        sa.Column(
            "target_portfolio_id",
            UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_asset_accounts_target_portfolio_id",
        "asset_accounts",
        ["target_portfolio_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_asset_accounts_target_portfolio_id", table_name="asset_accounts")
    op.drop_column("asset_accounts", "target_portfolio_id")
