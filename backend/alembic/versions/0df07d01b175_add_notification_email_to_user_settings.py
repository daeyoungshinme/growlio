"""add_notification_email_to_user_settings

Revision ID: 0df07d01b175
Revises: f1a2b3c4d5e6
Create Date: 2026-05-18 21:30:25.551942

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0df07d01b175'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_settings', sa.Column('notification_email', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('user_settings', 'notification_email')
