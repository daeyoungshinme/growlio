"""Add composite index on positions(account_id, ticker) for faster ticker lookups

Revision ID: ag1_add_position_account_ticker_index
Revises: af1_add_fcm_token
Create Date: 2026-06-11
"""

from alembic import op

revision = "ag1_position_ticker_idx"
down_revision = "af1_add_fcm_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_positions_account_ticker",
        "positions",
        ["account_id", "ticker"],
    )


def downgrade() -> None:
    op.drop_index("idx_positions_account_ticker", table_name="positions")
