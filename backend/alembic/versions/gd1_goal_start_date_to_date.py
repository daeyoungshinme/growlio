"""user_settings.goal_start_date: timestamptz → date — plans/114 B2

API는 처음부터 날짜만 받는데(schemas/settings.py) 컬럼만 timestamptz라 UTC 자정으로 붙여 저장했다.
KST로 날짜를 뽑는다 — UTC 자정(현재 코드)이든 옛 KST 자정(전날 15:00 UTC)이든 같은 날짜가 나온다.
downgrade는 UTC 자정 timestamptz로 되돌린다.

배포 순서: 이 마이그레이션을 공유 Supabase에 먼저 적용하고 곧바로 코드를 배포한다. 그 사이 옛 코드의
`goal_start_date.date()`(적립 분석)는 date 값에 실패한다.

Revision ID: gd1_goal_start_date_to_date
Revises: fk1_rebalancing_fk_indexes
Create Date: 2026-11-06 12:10:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "gd1_goal_start_date_to_date"
down_revision = "fk1_rebalancing_fk_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "user_settings",
        "goal_start_date",
        type_=sa.Date(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="(goal_start_date AT TIME ZONE 'Asia/Seoul')::date",
    )


def downgrade() -> None:
    op.alter_column(
        "user_settings",
        "goal_start_date",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.Date(),
        existing_nullable=True,
        postgresql_using="(goal_start_date::timestamp AT TIME ZONE 'UTC')",
    )
