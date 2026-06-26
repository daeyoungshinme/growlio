"""add annual_dividend_goal to user_settings

Revision ID: cc2fabe2d9eb
Revises: 9b35d2c773b1
Create Date: 2026-06-25 23:54:58.642339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'cc2fabe2d9eb'
down_revision: Union[str, None] = '9b35d2c773b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_settings', sa.Column('annual_dividend_goal', sa.Numeric(precision=18, scale=2), nullable=True))


def downgrade() -> None:
    op.drop_column('user_settings', 'annual_dividend_goal')
