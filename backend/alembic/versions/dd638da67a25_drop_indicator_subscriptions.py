"""drop indicator subscriptions

Revision ID: dd638da67a25
Revises: 6ce0d285d1a8
Create Date: 2026-07-15 20:18:06.613049

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "dd638da67a25"
down_revision: str | None = "6ce0d285d1a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_indicator_subscriptions_user", table_name="indicator_subscriptions")
    op.drop_table("indicator_subscriptions")


def downgrade() -> None:
    op.create_table(
        "indicator_subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("indicator_code", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "indicator_code", name="uq_indicator_subscription_user_code"),
    )
    op.create_index("idx_indicator_subscriptions_user", "indicator_subscriptions", ["user_id"], unique=False)
