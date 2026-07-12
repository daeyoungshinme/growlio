"""add goal recommendation options (risk tolerance, max weight, cagr lookback) to user_settings

Revision ID: as7_add_goal_recommendation_options
Revises: as6_add_goal_candidate_tickers
Create Date: 2026-07-11 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "as7_add_goal_recommendation_options"
down_revision = "as6_add_goal_candidate_tickers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_settings", sa.Column("goal_risk_tolerance", sa.String(length=20), nullable=True))
    op.add_column("user_settings", sa.Column("goal_max_weight_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("user_settings", sa.Column("goal_cagr_lookback_years", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_settings", "goal_cagr_lookback_years")
    op.drop_column("user_settings", "goal_max_weight_pct")
    op.drop_column("user_settings", "goal_risk_tolerance")
