"""Add investment_horizon/tax_type to portfolios

Revision ID: ac1_add_portfolio_horizon_tax_type
Revises: dd638da67a25
Create Date: 2026-07-15
"""

import sqlalchemy as sa

from alembic import op

revision = "ac1_add_portfolio_horizon_tax_type"
down_revision = "dd638da67a25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("investment_horizon", sa.String(length=20), nullable=True))
    op.add_column("portfolios", sa.Column("tax_type", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("portfolios", "tax_type")
    op.drop_column("portfolios", "investment_horizon")
