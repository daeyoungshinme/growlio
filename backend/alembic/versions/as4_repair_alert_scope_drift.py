"""repair rebalancing_alerts.alert_scope drift against portfolios.alert_scope (idempotent)

as3_repair_rebalancing_alert_scope의 복구 UPDATE는 `if "alert_scope" not in columns:` 블록
안에 중첩되어 있어, as1이 이미 컬럼을 추가한 뒤 실행되는 정상적인 마이그레이션 체인에서는
그 조건이 항상 False라 실제로는 한 번도 실행되지 않는 죽은 코드였다. as3는 이미 적용
완료된 마이그레이션이라 파일 내용을 고쳐도 기존 DB에는 재실행되지 않으므로, 별도의
forward-only 데이터 복구 마이그레이션으로 다시 처리한다.

Revision ID: as4_repair_alert_scope_drift
Revises: as3_repair_rebalancing_alert_scope
Create Date: 2026-07-07 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "as4_repair_alert_scope_drift"
down_revision: str | None = "as3_repair_rebalancing_alert_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Portfolio.alert_scope를 권위 있는 값으로 삼아 어긋난 rebalancing_alerts.alert_scope를 교정한다.
    # AGGREGATE+AUTO 알림도 실행계좌 지정 때문에 account_id가 NOT NULL이 되므로,
    # 과거 as1의 "account_id IS NOT NULL → PER_ACCOUNT" 백필 로직이 이런 행을 잘못 분류했었다.
    op.execute(
        """
        UPDATE rebalancing_alerts ra
        SET alert_scope = p.alert_scope
        FROM portfolios p
        WHERE p.id = ra.portfolio_id
          AND ra.alert_scope != p.alert_scope
        """
    )


def downgrade() -> None:
    # 데이터 복구 마이그레이션 — 원래의 드리프트 상태를 복원할 방법이 없으므로 downgrade는 no-op.
    pass
