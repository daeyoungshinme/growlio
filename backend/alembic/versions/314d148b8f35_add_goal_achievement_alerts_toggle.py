"""add goal achievement alerts toggle

Revision ID: 314d148b8f35
Revises: 6efd01502c77
Create Date: 2026-07-20 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "314d148b8f35"
down_revision: str | None = "6efd01502c77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("goal_achievement_alerts_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "goal_achievement_alerts_enabled")
