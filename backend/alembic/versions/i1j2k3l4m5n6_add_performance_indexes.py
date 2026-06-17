"""add_performance_indexes

Revision ID: i1j2k3l4m5n6
Revises: 18bc774cd76e
Create Date: 2026-05-24

"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "i1j2k3l4m5n6"
down_revision: str | None = "18bc774cd76e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # asset_accounts.user_id — user별 계좌 목록 조회 최적화
    op.create_index("idx_asset_accounts_user", "asset_accounts", ["user_id"])
    # asset_accounts(user_id, is_active) — 활성 계좌 필터 복합 쿼리 최적화
    op.create_index("idx_asset_accounts_user_active", "asset_accounts", ["user_id", "is_active"])
    # asset_accounts(user_id, is_active, include_in_total) — _get_monthly_trend SQL 필터 최적화
    op.create_index(
        "idx_asset_accounts_user_active_include",
        "asset_accounts",
        ["user_id", "is_active", "include_in_total"],
    )
    # asset_snapshots(user_id, account_id, snapshot_date) — 월별 추이 CTE 쿼리 최적화
    op.create_index(
        "idx_asset_snapshots_user_account_date",
        "asset_snapshots",
        ["user_id", "account_id", "snapshot_date"],
        postgresql_ops={"snapshot_date": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("idx_asset_snapshots_user_account_date", table_name="asset_snapshots")
    op.drop_index("idx_asset_accounts_user_active_include", table_name="asset_accounts")
    op.drop_index("idx_asset_accounts_user_active", table_name="asset_accounts")
    op.drop_index("idx_asset_accounts_user", table_name="asset_accounts")
