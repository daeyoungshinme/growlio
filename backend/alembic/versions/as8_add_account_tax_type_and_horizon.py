"""add tax_type and investment_horizon to asset_accounts

Revision ID: as8_add_account_tax_type_and_horizon
Revises: as7_add_goal_recommendation_options
Create Date: 2026-07-12 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "as8_add_account_tax_type_and_horizon"
down_revision = "as7_add_goal_recommendation_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_accounts",
        sa.Column("tax_type", sa.String(length=30), nullable=False, server_default="GENERAL"),
    )
    op.add_column(
        "asset_accounts",
        sa.Column("investment_horizon", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("asset_accounts", "investment_horizon")
    op.drop_column("asset_accounts", "tax_type")
