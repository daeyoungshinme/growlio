"""Add missing performance index for transactions

Revision ID: q1_add_performance_indexes
Revises: 36929c974b86
Create Date: 2026-05-30
"""

from alembic import op

revision = "q1_add_performance_indexes"
down_revision = "36929c974b86"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_transactions_user_type",
        "transactions",
        ["user_id", "transaction_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_transactions_user_type", table_name="transactions")
