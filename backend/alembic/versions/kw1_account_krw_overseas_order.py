"""키움 원화주문 서비스 계좌 표시

- asset_accounts.krw_overseas_order: 해외 매수를 원화 예수금으로 결제하는 계좌(키움 원화주문 신청).
  적립 해외 매수의 달러 부족 판정과 환전 계획이 원화 매수여력을 함께 본다.

배포 순서: 공유 Supabase에 이것을 적용하고 코드를 배포한다(기본값 false 컬럼 추가라 옛 코드와 호환).

Revision ID: kw1_account_krw_overseas_order
Revises: fx3_fx_extra_need_reserved_account
Create Date: 2026-11-14 10:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "kw1_account_krw_overseas_order"
down_revision = "fx3_fx_extra_need_reserved_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_accounts",
        sa.Column("krw_overseas_order", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("asset_accounts", "krw_overseas_order")
