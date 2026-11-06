"""리밸런싱 FK 인덱스 3개 — plans/111 E1 → plans/114 B1

- rebalancing_plans.portfolio_id: 포트폴리오 삭제, cancel_pending_buy_legs
- rebalancing_executions.portfolio_id: 포트폴리오 삭제 시 SET NULL
- rebalancing_plan_legs.execution_id: 사용자 삭제 시 실행 건마다 legs 전체 스캔

CONCURRENTLY라 테이블 잠금 없이 만든다(트랜잭션 밖 — autocommit_block).

Revision ID: fk1_rebalancing_fk_indexes
Revises: dc2_drop_dead_columns
Create Date: 2026-11-06 12:00:00.000000

"""

from alembic import op

revision = "fk1_rebalancing_fk_indexes"
down_revision = "dc2_drop_dead_columns"
branch_labels = None
depends_on = None

_INDEXES = (
    ("idx_rebalancing_plans_portfolio", "rebalancing_plans", "portfolio_id"),
    ("idx_rebalancing_executions_portfolio", "rebalancing_executions", "portfolio_id"),
    ("idx_rebalancing_plan_legs_execution", "rebalancing_plan_legs", "execution_id"),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, column in _INDEXES:
            op.create_index(name, table, [column], postgresql_concurrently=True, if_not_exists=True)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, _column in _INDEXES:
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
