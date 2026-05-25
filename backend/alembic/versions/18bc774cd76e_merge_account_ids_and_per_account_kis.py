"""merge_account_ids_and_per_account_kis

Revision ID: 18bc774cd76e
Revises: a2b3c4d5e6f7, h1i2j3k4l5m6
Create Date: 2026-05-24 18:06:06.393874

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '18bc774cd76e'
down_revision: Union[str, None] = ('a2b3c4d5e6f7', 'h1i2j3k4l5m6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
