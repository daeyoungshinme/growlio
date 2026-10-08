"""add trade_records table (수기 매매 기록 — 기간별 매수 수익률)

Revision ID: tr1_add_trade_records
Revises: bt1_drop_backtest_portfolios
Create Date: 2026-10-08 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "tr1_add_trade_records"
down_revision = "bt1_drop_backtest_portfolios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_krw", sa.Numeric(18, 2), nullable=False),
        sa.Column("fee", sa.Numeric(18, 2), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("idx_trade_records_user_date", "trade_records", ["user_id", "trade_date"])
    op.create_index(
        "idx_trade_records_account_ticker_date",
        "trade_records",
        ["account_id", "ticker", "market", "trade_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_trade_records_account_ticker_date", table_name="trade_records")
    op.drop_index("idx_trade_records_user_date", table_name="trade_records")
    op.drop_table("trade_records")
