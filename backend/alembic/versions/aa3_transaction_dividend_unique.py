"""Add partial unique index for dividend transactions to prevent duplicates from repeated syncs

Revision ID: aa3_transaction_dividend_unique
Revises: aa2_positions_indexes
Create Date: 2026-06-02
"""

from alembic import op

revision = "aa3_transaction_dividend_unique"
down_revision = "aa2_positions_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # account_id가 있는 동일 계좌·티커·날짜 배당은 중복 불가
    # account_id=NULL(계좌 삭제 후)은 제외 — 유니크 보장 불가
    op.create_index(
        "uq_div_account_ticker_date",
        "transactions",
        ["account_id", "ticker", "transaction_date"],
        unique=True,
        postgresql_where=("transaction_type = 'DIVIDEND' AND account_id IS NOT NULL AND ticker IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_div_account_ticker_date", table_name="transactions")
