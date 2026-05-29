"""add_index_exchange_rate_alerts_user_id

Revision ID: 36929c974b86
Revises: 7936847f6b94
Create Date: 2026-05-29 20:10:55.088966

"""
from typing import Sequence, Union

from alembic import op

revision: str = '36929c974b86'
down_revision: Union[str, None] = '7936847f6b94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'idx_exchange_rate_alerts_user',
        'exchange_rate_alerts',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('idx_exchange_rate_alerts_user', table_name='exchange_rate_alerts')
