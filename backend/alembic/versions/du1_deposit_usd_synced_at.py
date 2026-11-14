"""달러 예수금 확정 시각 + 추가 환전 보관 계좌 FK 인덱스

- asset_accounts.deposit_usd_synced_at: `deposit_usd`가 증권사 조회로 확정된 시각. 해외 조회 실패로 옛 달러를 유지한
  동기화도 `last_synced_at`은 새로 찍혀 환전 계획 기준 시각이 stale 달러를 "방금"으로 보였다. 기존 행은
  `last_synced_at`으로 채운다(지금까지의 표시와 같은 값).
- idx_fx_extra_needs_reserved_account: fx3에서 FK만 만들고 인덱스가 없었다(계좌 삭제 SET NULL·보관 계좌 조회).

배포 순서: 공유 Supabase에 이것을 적용하고 코드를 배포한다(nullable 컬럼·인덱스 추가라 옛 코드와 호환).

Revision ID: du1_deposit_usd_synced_at
Revises: kw1_account_krw_overseas_order
Create Date: 2026-11-14 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "du1_deposit_usd_synced_at"
down_revision = "kw1_account_krw_overseas_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("asset_accounts", sa.Column("deposit_usd_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE asset_accounts SET deposit_usd_synced_at = last_synced_at WHERE deposit_usd_synced_at IS NULL")
    op.create_index("idx_fx_extra_needs_reserved_account", "fx_extra_needs", ["reserved_account_id"])


def downgrade() -> None:
    op.drop_index("idx_fx_extra_needs_reserved_account", table_name="fx_extra_needs")
    op.drop_column("asset_accounts", "deposit_usd_synced_at")
