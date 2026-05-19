"""add_goal_initial_amount_to_user_settings

Revision ID: c1d2e3f4a5b6
Revises: 9451f5d41bd5
Create Date: 2026-05-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = ('9451f5d41bd5', '1b815a243623')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_settings', sa.Column('goal_initial_amount', sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('user_settings', 'goal_initial_amount')
