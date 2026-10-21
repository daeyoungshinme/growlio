"""add tactical_strategies table (매크로+차트 신호 기반 QQQ/SPY 전술 배분)

Revision ID: ta1_add_tactical_strategies
Revises: ix1_restore_target_portfolio_index
Create Date: 2026-10-20 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ta1_add_tactical_strategies"
down_revision: str | None = "ix1_restore_target_portfolio_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tactical_strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("notify_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("regime_weights", postgresql.JSONB(), nullable=True),
        sa.Column("last_regime", sa.String(12), nullable=True),
        sa.Column("last_regime_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_regime", sa.String(12), nullable=True),
        sa.Column("pending_first_seen", sa.Date(), nullable=True),
        sa.Column("applied_regime", sa.String(12), nullable=True),
        sa.Column("notified_regime", sa.String(12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tactical_strategies_user_id", "tactical_strategies", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_tactical_strategies_user_id", table_name="tactical_strategies")
    op.drop_table("tactical_strategies")
