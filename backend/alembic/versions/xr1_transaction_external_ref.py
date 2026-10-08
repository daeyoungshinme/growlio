"""add transactions.external_ref (nestlio 연동 멱등 키)

POST /external/transactions 재전송을 멱등하게 만들고, GET /external/net-deposits가 nestlio가 넣은 입출금을
걸러 증권사 직접 입금만 돌려줄 수 있게 한다. 기존 행은 NULL.

Revision ID: xr1_transaction_external_ref
Revises: tr1_add_trade_records
Create Date: 2026-10-08 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "xr1_transaction_external_ref"
down_revision = "tr1_add_trade_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("external_ref", sa.String(length=100), nullable=True))
    op.create_index(
        "uq_transactions_user_external_ref",
        "transactions",
        ["user_id", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_transactions_user_external_ref", table_name="transactions")
    op.drop_column("transactions", "external_ref")
