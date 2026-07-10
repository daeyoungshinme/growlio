"""repair rebalancing_alerts.alert_scope drift (idempotent)

Revision ID: as3_repair_rebalancing_alert_scope
Revises: as2_relax_rebalancing_alert_unique
Create Date: 2026-07-06 00:00:02.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "as3_repair_rebalancing_alert_scope"
down_revision: str | None = "as2_relax_rebalancing_alert_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("rebalancing_alerts")}

    # 주의: 이 분기는 as1이 이미 컬럼을 추가한 뒤라 정상 체인에서는 항상 False —
    # 실제 alert_scope 드리프트 복구는 as4_repair_alert_scope_drift에서 처리한다.
    if "alert_scope" not in columns:
        op.add_column(
            "rebalancing_alerts",
            sa.Column("alert_scope", sa.String(20), nullable=True),
        )
        op.execute(
            "UPDATE rebalancing_alerts SET alert_scope = "
            "CASE WHEN account_id IS NOT NULL THEN 'PER_ACCOUNT' ELSE 'AGGREGATE' END"
        )
        op.alter_column(
            "rebalancing_alerts",
            "alert_scope",
            existing_type=sa.String(20),
            nullable=False,
            server_default="AGGREGATE",
        )

    indexes = {ix["name"] for ix in inspector.get_indexes("rebalancing_alerts")}
    for name in ("uq_rebalancing_alert_aggregate", "uq_rebalancing_alert_per_account"):
        if name in indexes:
            op.drop_index(name, table_name="rebalancing_alerts")

    op.create_index(
        "uq_rebalancing_alert_aggregate",
        "rebalancing_alerts",
        ["user_id", "portfolio_id"],
        unique=True,
        postgresql_where=sa.text("alert_scope = 'AGGREGATE'"),
    )
    op.create_index(
        "uq_rebalancing_alert_per_account",
        "rebalancing_alerts",
        ["user_id", "portfolio_id", "account_id"],
        unique=True,
        postgresql_where=sa.text("alert_scope = 'PER_ACCOUNT'"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = {ix["name"] for ix in inspector.get_indexes("rebalancing_alerts")}
    for name in ("uq_rebalancing_alert_per_account", "uq_rebalancing_alert_aggregate"):
        if name in indexes:
            op.drop_index(name, table_name="rebalancing_alerts")

    columns = {c["name"] for c in inspector.get_columns("rebalancing_alerts")}
    if "alert_scope" in columns:
        op.drop_column("rebalancing_alerts", "alert_scope")
