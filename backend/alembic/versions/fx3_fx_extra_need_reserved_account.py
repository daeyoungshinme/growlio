"""추가 환전 항목의 보관 증권 계좌 — plans/123 후속

- fx_extra_needs.reserved_account_id: 여행 달러를 둔 증권 계좌(선택, 계좌 삭제 시 SET NULL).
  지정하면 적립 환전 계획의 그 계좌 보유 달러에서 이미 환전한 금액만큼 뺀다.

배포 순서: 공유 Supabase에 fx2 다음 이것을 적용하고 코드를 배포한다(컬럼 추가만이라 옛 코드와 호환).

Revision ID: fx3_fx_extra_need_reserved_account
Revises: fx2_fx_extra_needs
Create Date: 2026-11-11 14:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "fx3_fx_extra_need_reserved_account"
down_revision = "fx2_fx_extra_needs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fx_extra_needs",
        sa.Column("reserved_account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fx_extra_needs_reserved_account_id",
        "fx_extra_needs",
        "asset_accounts",
        ["reserved_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_fx_extra_needs_reserved_account_id", "fx_extra_needs", type_="foreignkey")
    op.drop_column("fx_extra_needs", "reserved_account_id")
