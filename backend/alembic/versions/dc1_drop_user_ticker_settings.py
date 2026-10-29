"""user_ticker_settings 테이블 드롭

배당월 수동 override 기능은 plans/52 배치 A에서 제거됐고 이 테이블을 읽고 쓰는 코드가 없다(nestlio 포함).
앱이 조회하지 않으므로 모델 제거와 같은 배포에서 드롭해도 옛 인스턴스가 깨지지 않는다(plans/91 G1).
downgrade는 빈 테이블만 다시 만든다 — 데이터는 복원하지 않는다.

Revision ID: dc1_drop_user_ticker_settings
Revises: oc2_rebalancing_result_price
Create Date: 2026-10-29 20:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "dc1_drop_user_ticker_settings"
down_revision = "oc2_rebalancing_result_price"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_user_ticker_settings_user", table_name="user_ticker_settings")
    op.drop_table("user_ticker_settings")


def downgrade() -> None:
    op.create_table(
        "user_ticker_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("dividend_months", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "ticker", "market", name="uq_user_ticker_settings"),
    )
    op.create_index("idx_user_ticker_settings_user", "user_ticker_settings", ["user_id"])
