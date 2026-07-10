"""add goal_candidate_tickers to user_settings

Revision ID: as6_add_goal_candidate_tickers
Revises: as5_add_rebalancing_pending_plan
Create Date: 2026-07-09 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "as6_add_goal_candidate_tickers"
down_revision = "as5_add_rebalancing_pending_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("goal_candidate_tickers", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "goal_candidate_tickers")
