"""add_snapshots_user_date_index: asset_snapshots(user_id, snapshot_date DESC) 인덱스 추가

Revision ID: aa2_add_snapshots_user_date_index
Revises: z2_positions_normalization
Create Date: 2026-06-15
"""

from sqlalchemy import text

from alembic import op

revision = "aa2_add_snapshots_user_date_index"
down_revision = "ak1_add_deposit_trigger_to_rebalancing_alert"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text("CREATE INDEX IF NOT EXISTS idx_snapshots_user_date_desc ON asset_snapshots (user_id, snapshot_date DESC)")
    )


def downgrade() -> None:
    op.execute(text("DROP INDEX IF EXISTS idx_snapshots_user_date_desc"))
