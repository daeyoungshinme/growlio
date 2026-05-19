"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "user_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("goal_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("goal_annual_return_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("goal_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kis_app_key", sa.String(512), nullable=True),
        sa.Column("kis_app_secret", sa.String(512), nullable=True),
        sa.Column("kis_account_no", sa.String(20), nullable=True),
        sa.Column("kis_is_mock", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("ob_access_token", sa.Text(), nullable=True),
        sa.Column("ob_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "asset_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("asset_type", sa.String(30), nullable=False),
        sa.Column("data_source", sa.String(20), nullable=False, server_default="MANUAL"),
        sa.Column("institution", sa.String(100), nullable=True),
        sa.Column("ob_bank_code", sa.String(10), nullable=True),
        sa.Column("ob_account_no_encrypted", sa.String(200), nullable=True),
        sa.Column("ob_fintech_use_no", sa.String(50), nullable=True),
        sa.Column("kis_account_no", sa.String(20), nullable=True),
        sa.Column("is_mock_mode", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("manual_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("manual_currency", sa.String(3), nullable=False, server_default="KRW"),
        sa.Column("manual_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "asset_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("amount_krw", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount_original", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KRW"),
        sa.Column("usd_krw_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("invested_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(18, 2), nullable=True),
        sa.Column("positions", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="MANUAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["asset_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "snapshot_date", name="uq_snapshot_account_date"),
    )
    op.create_index("idx_snapshots_user_date", "asset_snapshots", ["user_id", "snapshot_date"])

    op.create_table(
        "securities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("name_ko", sa.String(200), nullable=True),
        sa.Column("name_en", sa.String(200), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("is_etf", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "market", name="uq_security_ticker_market"),
    )
    op.create_index("idx_securities_ticker", "securities", ["ticker"])
    op.create_index("idx_securities_market", "securities", ["market"])

    op.create_table(
        "kis_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(50), nullable=False, server_default="Bearer"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_mock_mode", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "is_mock_mode", name="uq_kis_token_user_mode"),
    )


def downgrade() -> None:
    op.drop_table("kis_tokens")
    op.drop_index("idx_securities_market", "securities")
    op.drop_index("idx_securities_ticker", "securities")
    op.drop_table("securities")
    op.drop_index("idx_snapshots_user_date", "asset_snapshots")
    op.drop_table("asset_snapshots")
    op.drop_table("asset_accounts")
    op.drop_table("user_settings")
    op.drop_table("users")
