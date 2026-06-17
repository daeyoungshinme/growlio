"""rebalancing_results_normalization: results JSONB → 정규화 테이블

Revision ID: z1_rebalancing_results_normalization
Revises: y1_portfolio_normalization
Create Date: 2026-06-01

rebalancing_executions.results JSONB → rebalancing_execution_results 테이블
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "z1_rebalancing_results"
down_revision = "y1_portfolio_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. rebalancing_execution_results 테이블 생성
    op.create_table(
        "rebalancing_execution_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "execution_id",
            UUID(as_uuid=True),
            sa.ForeignKey("rebalancing_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(50), nullable=True),
        sa.Column("account_name", sa.String(200), nullable=True),
        sa.Column("is_mock", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("market", sa.String(20), nullable=True),
        sa.Column("quantity", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("order_no", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("order_type", sa.String(20), nullable=False, server_default="'MARKET'"),
    )
    op.create_index(
        "idx_rebalancing_results_execution",
        "rebalancing_execution_results",
        ["execution_id"],
    )

    # 2. 기존 JSONB 데이터 마이그레이션
    conn = op.get_bind()
    executions = conn.execute(
        sa.text("SELECT id, results FROM rebalancing_executions WHERE results IS NOT NULL")
    ).fetchall()

    for row in executions:
        exec_id = row[0]
        results_json = row[1] or []

        for exec_result in results_json:
            account_id = exec_result.get("account_id", "")
            account_name = exec_result.get("account_name", "")
            is_mock = exec_result.get("is_mock", False)
            for order in exec_result.get("orders", []):
                conn.execute(
                    sa.text(
                        "INSERT INTO rebalancing_execution_results "
                        "(id, execution_id, account_id, account_name, is_mock, "
                        "action, ticker, name, market, "
                        " quantity, status, order_no, error_message, order_type) "
                        "VALUES "
                        "(gen_random_uuid(), :eid, :aid, :aname, :is_mock, "
                        ":action, :ticker, :name, "
                        " :market, :qty, :status, :order_no, :error_msg, :order_type)"
                    ),
                    {
                        "eid": exec_id,
                        "aid": account_id,
                        "aname": account_name,
                        "is_mock": is_mock,
                        "action": order.get("side", "BUY"),
                        "ticker": order.get("ticker"),
                        "name": order.get("name"),
                        "market": order.get("market"),
                        "qty": order.get("quantity"),
                        "status": order.get("status", "UNKNOWN"),
                        "order_no": order.get("order_no"),
                        "error_msg": order.get("error_msg"),
                        "order_type": order.get("order_type", "MARKET"),
                    },
                )

    # 3. JSONB 컬럼 DROP
    op.drop_column("rebalancing_executions", "results")


def downgrade() -> None:
    # 1. JSONB 컬럼 복구
    op.add_column("rebalancing_executions", sa.Column("results", JSONB, nullable=True))

    # 2. 테이블 데이터 → JSONB 역마이그레이션
    conn = op.get_bind()
    import json
    from collections import defaultdict

    exec_ids = conn.execute(sa.text("SELECT id FROM rebalancing_executions")).fetchall()
    for (exec_id,) in exec_ids:
        rows = conn.execute(
            sa.text(
                "SELECT account_id, account_name, is_mock, action, ticker, name, market, "
                "quantity, status, order_no, error_message, order_type "
                "FROM rebalancing_execution_results WHERE execution_id = :eid"
            ),
            {"eid": exec_id},
        ).fetchall()

        by_account: dict = defaultdict(lambda: {"orders": [], "is_mock": False, "account_name": ""})
        for r in rows:
            acc_id = r[0] or ""
            by_account[acc_id]["account_name"] = r[1] or ""
            by_account[acc_id]["is_mock"] = r[2]
            by_account[acc_id]["orders"].append(
                {
                    "side": r[3],
                    "ticker": r[4],
                    "name": r[5],
                    "market": r[6],
                    "quantity": r[7],
                    "status": r[8],
                    "order_no": r[9],
                    "error_msg": r[10],
                    "order_type": r[11],
                }
            )

        results_list = [
            {
                "account_id": aid,
                "account_name": data["account_name"],
                "is_mock": data["is_mock"],
                "orders": data["orders"],
                "success_count": sum(1 for o in data["orders"] if o["status"] == "SUCCESS"),
                "fail_count": sum(1 for o in data["orders"] if o["status"] == "FAILED"),
                "executed_at": "",
            }
            for aid, data in by_account.items()
        ]
        if results_list:
            conn.execute(
                sa.text("UPDATE rebalancing_executions SET results = :r::jsonb WHERE id = :eid"),
                {"r": json.dumps(results_list), "eid": exec_id},
            )

    # 3. 정규화 테이블 DROP
    op.drop_index("idx_rebalancing_results_execution", table_name="rebalancing_execution_results")
    op.drop_table("rebalancing_execution_results")
