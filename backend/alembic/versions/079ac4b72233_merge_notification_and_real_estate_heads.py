"""merge_notification_and_real_estate_heads

Revision ID: 079ac4b72233
Revises: 0df07d01b175, a8b9c0d1e2f3
Create Date: 2026-05-18 21:57:42.932571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '079ac4b72233'
down_revision: Union[str, None] = ('0df07d01b175', 'a8b9c0d1e2f3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
