"""add_deposit_usd_to_asset_accounts

Revision ID: 7936847f6b94
Revises: p1_add_alert_trigger_count
Create Date: 2026-05-29 18:00:40.425030

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7936847f6b94'
down_revision: Union[str, None] = 'p1_add_alert_trigger_count'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('asset_accounts', sa.Column('deposit_usd', sa.Numeric(precision=18, scale=4), nullable=True))


def downgrade() -> None:
    op.drop_column('asset_accounts', 'deposit_usd')
