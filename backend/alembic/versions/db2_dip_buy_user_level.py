"""낙폭 추매 안내를 포트폴리오에서 분리 — plans/148

- dip_buy_settings: 사용자당 1행(남은 여윳돈·알림 방식)
- dip_buy_rules: 지수별 규칙(여윳돈 배분 %·구간·사이클 기준액·완료 기록·알림 보낸 구간)
- dca_dip_buy_plans(db1) → 위 두 테이블로 이관 후 드롭. 여윳돈 = 사용자 플랜 합계, 지수별로 가장 먼저 만든
  플랜이 규칙이 되고 배분은 지수 수로 균등. `env.py`의 `include_name` 필터 때문에 autogenerate는 드롭을 못 잡아
  직접 쓴다.

배포 순서: 공유 Supabase에 먼저 적용하고 코드를 배포한다(옛 코드는 dca_dip_buy_plans가 없으면 추매 카드가 실패).
db1이 운영에 아직 없으면 `upgrade head`가 db1 → db2를 함께 적용한다.

Revision ID: db2_dip_buy_user_level
Revises: db1_dca_dip_buy_plans
Create Date: 2026-11-23 15:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "db2_dip_buy_user_level"
down_revision = "db1_dca_dip_buy_plans"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _user_fk() -> sa.Column:
    return sa.Column(
        "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "dip_buy_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(),
        sa.Column("reserve_krw", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("notify_mode", sa.String(12), nullable=False, server_default="ON_REACH"),
        sa.Column("notify_day", sa.SmallInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        *_timestamps(),
        sa.UniqueConstraint("user_id", name="uq_dip_buy_settings_user"),
    )
    op.create_table(
        "dip_buy_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(),
        sa.Column("index_ticker", sa.String(8), nullable=False),
        sa.Column("allocation_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("tiers", postgresql.JSONB(), nullable=False),
        sa.Column("cycle_base_krw", sa.Numeric(18, 2), nullable=True),
        sa.Column("completed", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("notified_tiers", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "index_ticker", name="uq_dip_buy_rules_user_index"),
    )
    op.create_index("idx_dip_buy_rules_user", "dip_buy_rules", ["user_id"])

    # 이관 — 옛 플랜의 사용자별 여윳돈 합계, 지수별 첫 플랜 → 규칙(배분은 지수 수로 균등)
    op.execute(
        """
        INSERT INTO dip_buy_settings (id, user_id, reserve_krw, notify_mode, notify_day, is_active)
        SELECT gen_random_uuid(), user_id, SUM(reserve_krw), 'ON_REACH', NULL, BOOL_OR(is_active)
        FROM dca_dip_buy_plans
        GROUP BY user_id
        """
    )
    op.execute(
        """
        INSERT INTO dip_buy_rules
            (id, user_id, index_ticker, allocation_pct, tiers, cycle_base_krw, completed, notified_tiers, is_active)
        SELECT gen_random_uuid(), p.user_id, p.index_ticker,
               ROUND(100.0 / COUNT(*) OVER (PARTITION BY p.user_id), 2),
               p.tiers, NULL, p.completed, '[]'::jsonb, p.is_active
        FROM (
            SELECT DISTINCT ON (user_id, index_ticker) *
            FROM dca_dip_buy_plans
            ORDER BY user_id, index_ticker, created_at
        ) p
        """
    )
    # 이관한 규칙의 진행 중 사이클 기준액은 버린다(옛 기준액은 포트폴리오 여윳돈 전체 기준이라 규칙 몫과 다르다).
    # 완료 기록은 남겨 같은 구간을 다시 안내하지 않는다.
    op.drop_index("idx_dca_dip_buy_plans_user", table_name="dca_dip_buy_plans")
    op.drop_table("dca_dip_buy_plans")


def downgrade() -> None:
    # 테이블 구조만 되돌린다 — 규칙 → 포트폴리오 플랜 역이관은 하지 않는다(포트폴리오 정보가 없다)
    op.create_table(
        "dca_dip_buy_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _user_fk(),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("index_ticker", sa.String(8), nullable=False, server_default="QQQ"),
        sa.Column("reserve_krw", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tiers", postgresql.JSONB(), nullable=False),
        sa.Column("cycle_base_krw", sa.Numeric(18, 2), nullable=True),
        sa.Column("completed", postgresql.JSONB(), nullable=False, server_default="[]"),
        *_timestamps(),
        sa.UniqueConstraint("portfolio_id", name="uq_dca_dip_buy_plans_portfolio"),
    )
    op.create_index("idx_dca_dip_buy_plans_user", "dca_dip_buy_plans", ["user_id"])
    op.drop_index("idx_dip_buy_rules_user", table_name="dip_buy_rules")
    op.drop_table("dip_buy_rules")
    op.drop_table("dip_buy_settings")
