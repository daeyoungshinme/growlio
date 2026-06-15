"""merge deposit trigger and snapshot index heads

Revision ID: al1_merge_deposit_trigger_and_snapshot_index
Revises: ak1_add_deposit_trigger_to_rebalancing_alert, aa2_add_snapshots_user_date_index
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "al1_merge_deposit_trigger_and_snapshot_index"
down_revision: Union[str, tuple[str, ...], None] = (
    "ak1_add_deposit_trigger_to_rebalancing_alert",
    "aa2_add_snapshots_user_date_index",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
