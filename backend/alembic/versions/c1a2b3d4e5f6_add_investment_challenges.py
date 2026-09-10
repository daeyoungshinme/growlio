"""add investment_challenges table + challenge_reminders_enabled

Revision ID: c1a2b3d4e5f6
Revises: f0551a2b3c4d
Create Date: 2026-09-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: str | None = "f0551a2b3c4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investment_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("challenge_type", sa.String(20), nullable=False),
        sa.Column("target_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("target_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("target_months", sa.Integer(), nullable=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("start_month", sa.String(7), nullable=False),
        sa.Column("deadline_month", sa.String(7), nullable=True),
        sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_investment_challenges_user_status", "investment_challenges", ["user_id", "status"])
    op.add_column(
        "user_settings",
        sa.Column("challenge_reminders_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "challenge_reminders_enabled")
    op.drop_index("idx_investment_challenges_user_status", table_name="investment_challenges")
    op.drop_table("investment_challenges")
