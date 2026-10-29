"""rebalancing_execution_results: 주문 가격 저장

실행 직후 화면은 지정가(또는 시장가 주문의 참고 시세)를 보여 주는데 이력에는 저장하지 않아 이력 상세에서
가격이 항상 비어 있었다. 국내=KRW, 해외=USD 원 통화 그대로 저장한다(KRW 환산 금액 컬럼이 아님).

Revision ID: oc2_rebalancing_result_price
Revises: oc1_rebalancing_result_cancel
Create Date: 2026-10-29 16:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "oc2_rebalancing_result_price"
down_revision = "oc1_rebalancing_result_cancel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rebalancing_execution_results", sa.Column("price", sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("rebalancing_execution_results", "price")
