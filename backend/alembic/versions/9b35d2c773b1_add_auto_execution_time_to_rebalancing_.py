"""add_auto_execution_time_to_rebalancing_alert

Revision ID: 9b35d2c773b1
Revises: ac1_remove_deposit_trigger
Create Date: 2026-06-25 18:00:43.198350

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9b35d2c773b1"
down_revision: Union[str, None] = "ac1_remove_deposit_trigger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rebalancing_alerts", sa.Column("auto_execution_time", sa.String(length=5), nullable=True))


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "auto_execution_time")
