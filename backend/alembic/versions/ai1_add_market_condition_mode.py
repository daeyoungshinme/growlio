"""add market_condition_mode to rebalancing_alerts

Revision ID: ai1_add_market_condition_mode
Revises: a64e36a53a40
Create Date: 2026-06-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "ai1_add_market_condition_mode"
down_revision = "a64e36a53a40"


def upgrade() -> None:
    op.add_column(
        "rebalancing_alerts",
        sa.Column(
            "market_condition_mode",
            sa.String(10),
            nullable=False,
            server_default="DISABLED",
        ),
    )


def downgrade() -> None:
    op.drop_column("rebalancing_alerts", "market_condition_mode")
