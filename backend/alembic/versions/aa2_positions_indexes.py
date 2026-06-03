"""Add indexes for positions table and asset_snapshots user_id

Revision ID: aa2_positions_indexes
Revises: aa1_add_composite_indexes
Create Date: 2026-06-02
"""

from alembic import op

revision = "aa2_positions_indexes"
down_revision = "aa1_add_composite_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # _build_asset_totals: Position.snapshot_id.in_(snap_ids) 배치 쿼리
    op.create_index(
        "idx_positions_snapshot_id",
        "positions",
        ["snapshot_id"],
    )
    # _build_asset_totals: account_id.in_(...) AND snapshot_id IS NULL (현재 포지션)
    op.create_index(
        "idx_positions_account_no_snapshot",
        "positions",
        ["account_id"],
        postgresql_where="snapshot_id IS NULL",
    )
    # monthly trend raw SQL: WHERE s.user_id = :uid
    op.create_index(
        "idx_snapshots_user_id",
        "asset_snapshots",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_positions_snapshot_id", table_name="positions")
    op.drop_index("idx_positions_account_no_snapshot", table_name="positions")
    op.drop_index("idx_snapshots_user_id", table_name="asset_snapshots")
