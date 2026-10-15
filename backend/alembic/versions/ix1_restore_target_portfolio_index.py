"""restore asset_accounts.target_portfolio_id index

ah1_add_target_portfolio_to_accounts가 만든 인덱스를 a64e36a53a40(autogenerate)이 모델에 선언돼 있지
않다는 이유로 지웠다. FK(ON DELETE SET NULL)라 포트폴리오 삭제 때마다 계좌 테이블을 스캔한다.
같은 마이그레이션이 지운 uq_positions_account_ticker_current(현재 포지션 부분 유니크)는 복구하지 않는다 —
수동 포지션 저장·브로커 잔고(현금/신용 별도 행)가 같은 계좌·티커를 여러 행으로 쓸 수 있어, 다시 걸면
동기화가 IntegrityError로 실패할 수 있다(plans/55 C6).

Revision ID: ix1_restore_target_portfolio_index
Revises: xr1_transaction_external_ref
Create Date: 2026-10-15 12:00:00.000000

"""

from alembic import op

revision = "ix1_restore_target_portfolio_index"
down_revision = "xr1_transaction_external_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_asset_accounts_target_portfolio_id",
        "asset_accounts",
        ["target_portfolio_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_asset_accounts_target_portfolio_id", table_name="asset_accounts", if_exists=True)
