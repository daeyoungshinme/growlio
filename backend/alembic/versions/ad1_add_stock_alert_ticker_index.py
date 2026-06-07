"""Add index on stock_price_alerts.ticker for scheduler price check queries

Revision ID: ad1_add_stock_alert_ticker_index
Revises: ac1_positions_unique_constraint
Create Date: 2026-06-08
"""

from alembic import op

revision = "ad1_add_stock_alert_ticker_index"
down_revision = "ac1_positions_unique_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_stock_price_alerts_ticker",
            "stock_price_alerts",
            ["ticker"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "idx_stock_price_alerts_ticker",
            table_name="stock_price_alerts",
            postgresql_concurrently=True,
            if_exists=True,
        )
