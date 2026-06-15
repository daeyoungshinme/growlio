"""add trigger_condition to rebalancing_alerts (replaces only_when_drift boolean)

Revision ID: am1_add_trigger_condition_to_rebalancing_alert
Revises: al1_merge_deposit_trigger_and_snapshot_index
Create Date: 2026-06-15

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "am1_add_trigger_condition_to_rebalancing_alert"
down_revision = "al1_merge_deposit_trigger_and_snapshot_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column(
            "trigger_condition",
            sa.String(20),
            nullable=False,
            server_default="DRIFT_ONLY",
        ),
    )
    op.execute(
        """
        UPDATE rebalancing_alerts
        SET trigger_condition =
            CASE WHEN only_when_drift THEN 'DRIFT_ONLY' ELSE 'SCHEDULE_ONLY' END
        """
    )
    op.drop_column("rebalancing_alerts", "only_when_drift")


def downgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column(
            "only_when_drift",
            sa.Boolean(),
            nullable=False,
            server_default="TRUE",
        ),
    )
    op.execute(
        """
        UPDATE rebalancing_alerts
        SET only_when_drift =
            CASE WHEN trigger_condition = 'DRIFT_ONLY' THEN TRUE ELSE FALSE END
        """
    )
    op.drop_column("rebalancing_alerts", "trigger_condition")
