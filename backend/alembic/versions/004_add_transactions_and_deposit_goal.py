"""add_transactions_and_deposit_goal

Revision ID: 004
Revises: 003
Create Date: 2026-05-02 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("annual_deposit_goal", sa.Numeric(18, 2), nullable=True),
    )

    op.create_table(
        "transactions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["asset_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_transactions_user_date", "transactions", ["user_id", "transaction_date"])
    op.create_index("idx_transactions_account", "transactions", ["account_id"])


def downgrade() -> None:
    op.drop_index("idx_transactions_account", table_name="transactions")
    op.drop_index("idx_transactions_user_date", table_name="transactions")
    op.drop_table("transactions")
    op.drop_column("user_settings", "annual_deposit_goal")
