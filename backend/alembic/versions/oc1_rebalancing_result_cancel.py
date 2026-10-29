"""rebalancing_execution_results: 미체결 주문 취소 컬럼

KIS 국내 취소는 주문 응답의 KRX_FWDG_ORD_ORGNO(주문 조직번호)가 필요해 저장한다. 취소 결과도 주문 행에
남긴다(plans/89).

Revision ID: oc1_rebalancing_result_cancel
Revises: pm1_drop_dup_portfolio_item_members_index
Create Date: 2026-10-29 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "oc1_rebalancing_result_cancel"
down_revision = "pm1_drop_dup_portfolio_item_members_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rebalancing_execution_results", sa.Column("order_org_no", sa.String(20), nullable=True))
    op.add_column("rebalancing_execution_results", sa.Column("cancel_status", sa.String(20), nullable=True))
    op.add_column("rebalancing_execution_results", sa.Column("cancel_message", sa.Text(), nullable=True))
    op.add_column("rebalancing_execution_results", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("rebalancing_execution_results", "canceled_at")
    op.drop_column("rebalancing_execution_results", "cancel_message")
    op.drop_column("rebalancing_execution_results", "cancel_status")
    op.drop_column("rebalancing_execution_results", "order_org_no")
