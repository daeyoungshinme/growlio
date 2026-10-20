"""widen alert_history.alert_type to 40 chars

String(20)이라 "YEAR_END_TAX_REMINDER"(21자) 이력 저장이 매번 "value too long"으로 실패했다 —
메일·푸시는 나간 뒤라 사용자는 받지만 앱 이력에 안 남고, 같은 날 중복 발송 판정(이력 조회)도 무력화됐다.
MARKET_SIGNAL_DIGEST·RECOMMENDATION_DRIFT도 정확히 20자라 여유를 둔다(plans/61 A1).
varchar 길이 확장은 테이블 재작성 없이 카탈로그만 바뀐다.

Revision ID: at1_widen_alert_history_alert_type
Revises: ix1_restore_target_portfolio_index
Create Date: 2026-10-20 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "at1_widen_alert_history_alert_type"
down_revision = "ix1_restore_target_portfolio_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "alert_history",
        "alert_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=40),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "alert_history",
        "alert_type",
        existing_type=sa.String(length=40),
        type_=sa.String(length=20),
        existing_nullable=False,
        postgresql_using="left(alert_type, 20)",
    )
