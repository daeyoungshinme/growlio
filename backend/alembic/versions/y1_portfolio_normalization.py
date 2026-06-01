"""portfolio_normalization: items/account_ids JSONB → 정규화 테이블

Revision ID: y1_portfolio_normalization
Revises: x1_merge_rebalancing_and_auto
Create Date: 2026-06-01

portfolios.items JSONB → portfolio_items 테이블
portfolios.account_ids JSONB → portfolio_accounts 테이블
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "y1_portfolio_normalization"
down_revision = "x1_merge_rebalancing_and_auto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. portfolio_items 테이블 생성
    op.create_table(
        "portfolio_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("weight", sa.Numeric(6, 2), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("idx_portfolio_items_portfolio", "portfolio_items", ["portfolio_id"])

    # 2. portfolio_accounts 테이블 생성
    op.create_table(
        "portfolio_accounts",
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("asset_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("portfolio_id", "account_id"),
    )

    # 3. 기존 JSONB 데이터 마이그레이션
    conn = op.get_bind()

    portfolios = conn.execute(
        sa.text("SELECT id, items, account_ids FROM portfolios")
    ).fetchall()

    for row in portfolios:
        pid = row[0]
        items_json = row[1] or []
        account_ids_json = row[2] or []

        for idx, item in enumerate(items_json):
            conn.execute(
                sa.text(
                    "INSERT INTO portfolio_items (id, portfolio_id, ticker, name, market, weight, sort_order) "
                    "VALUES (gen_random_uuid(), :pid, :ticker, :name, :market, :weight, :sort_order)"
                ),
                {
                    "pid": pid,
                    "ticker": item.get("ticker", ""),
                    "name": item.get("name", ""),
                    "market": item.get("market", "KOSPI"),
                    "weight": float(item.get("weight", 0)),
                    "sort_order": idx,
                },
            )

        # account_ids는 UUID 문자열 목록 — asset_accounts에 실제 존재하는 것만 삽입
        for aid_str in account_ids_json:
            try:
                aid_uuid = str(uuid.UUID(aid_str))
            except (ValueError, AttributeError):
                continue
            exists = conn.execute(
                sa.text("SELECT 1 FROM asset_accounts WHERE id = :aid"),
                {"aid": aid_uuid},
            ).fetchone()
            if exists:
                conn.execute(
                    sa.text(
                        "INSERT INTO portfolio_accounts (portfolio_id, account_id) "
                        "VALUES (:pid, :aid) ON CONFLICT DO NOTHING"
                    ),
                    {"pid": pid, "aid": aid_uuid},
                )

    # 4. JSONB 컬럼 DROP
    op.drop_column("portfolios", "items")
    op.drop_column("portfolios", "account_ids")


def downgrade() -> None:
    # 1. JSONB 컬럼 복구
    op.add_column("portfolios", sa.Column("items", JSONB, nullable=False, server_default="[]"))
    op.add_column("portfolios", sa.Column("account_ids", JSONB, nullable=True))

    # 2. 테이블 데이터 → JSONB 역마이그레이션
    conn = op.get_bind()

    portfolio_ids = conn.execute(sa.text("SELECT id FROM portfolios")).fetchall()
    for (pid,) in portfolio_ids:
        items = conn.execute(
            sa.text(
                "SELECT ticker, name, market, weight FROM portfolio_items "
                "WHERE portfolio_id = :pid ORDER BY sort_order"
            ),
            {"pid": pid},
        ).fetchall()
        items_list = [
            {"ticker": r[0], "name": r[1], "market": r[2], "weight": float(r[3])}
            for r in items
        ]

        accounts = conn.execute(
            sa.text("SELECT account_id FROM portfolio_accounts WHERE portfolio_id = :pid"),
            {"pid": pid},
        ).fetchall()
        account_ids_list = [str(r[0]) for r in accounts]

        import json
        conn.execute(
            sa.text(
                "UPDATE portfolios SET items = :items::jsonb, account_ids = :aids::jsonb "
                "WHERE id = :pid"
            ),
            {
                "items": json.dumps(items_list),
                "aids": json.dumps(account_ids_list) if account_ids_list else None,
                "pid": pid,
            },
        )

    # 3. 정규화 테이블 DROP
    op.drop_index("idx_portfolio_items_portfolio", table_name="portfolio_items")
    op.drop_table("portfolio_accounts")
    op.drop_table("portfolio_items")
