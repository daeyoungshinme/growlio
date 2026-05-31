"""Add stock_price_alerts table

Revision ID: w1_add_stock_price_alert
Revises: v1_add_dca_auto_settings
Create Date: 2026-05-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "w1_add_stock_price_alert"
down_revision = "v1_add_dca_auto_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    direction_enum = postgresql.ENUM("BELOW", "ABOVE", name="stock_alert_direction_enum", create_type=False)
    direction_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "stock_price_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False, server_default=""),
        sa.Column("target_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("direction", direction_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("max_trigger_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trigger_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_stock_price_alerts_user_active", "stock_price_alerts", ["user_id", "is_active"])


def downgrade() -> None:
    op.drop_index("idx_stock_price_alerts_user_active", table_name="stock_price_alerts")
    op.drop_table("stock_price_alerts")
    postgresql.ENUM(name="stock_alert_direction_enum").drop(op.get_bind(), checkfirst=True)
