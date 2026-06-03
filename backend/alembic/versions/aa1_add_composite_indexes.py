"""Add composite indexes for dashboard and asset queries

Revision ID: aa1_add_composite_indexes
Revises: z2_positions_normalization
Create Date: 2026-06-02
"""

from alembic import op

revision = "aa1_add_composite_indexes"
down_revision = "z2_positions_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 대시보드 집계: 활성 계좌 필터 + 타입별 분류
    op.create_index(
        "idx_asset_accounts_user_active_type",
        "asset_accounts",
        ["user_id", "is_active", "asset_type"],
    )
    # 배당 집계 / 거래 내역 조회: 타입+날짜 복합 필터
    op.create_index(
        "idx_transactions_user_type_date",
        "transactions",
        ["user_id", "transaction_type", "transaction_date"],
    )
    # 최신 스냅샷 조회: account_id + 날짜 내림차순
    op.create_index(
        "idx_snapshots_account_date_desc",
        "asset_snapshots",
        ["account_id", "snapshot_date"],
        postgresql_ops={"snapshot_date": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("idx_asset_accounts_user_active_type", table_name="asset_accounts")
    op.drop_index("idx_transactions_user_type_date", table_name="transactions")
    op.drop_index("idx_snapshots_account_date_desc", table_name="asset_snapshots")
