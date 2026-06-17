"""positions_normalization: manual_positions/snapshot.positions JSONB → positions 테이블

Revision ID: z2_positions_normalization
Revises: z1_rebalancing_results_normalization
Create Date: 2026-06-01

AssetAccount.manual_positions JSONB → positions (snapshot_id IS NULL)
AssetSnapshot.positions JSONB → positions (snapshot_id = snapshot.id)
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "z2_positions_normalization"
down_revision = "z1_rebalancing_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. positions 테이블 생성
    op.create_table(
        "positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("asset_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            UUID(as_uuid=True),
            sa.ForeignKey("asset_snapshots.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("qty", sa.Numeric(18, 4), nullable=False),
        sa.Column("avg_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("avg_price_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("current_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("value_krw", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="'KRW'"),
        sa.Column("usd_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_positions_account_snapshot", "positions", ["account_id", "snapshot_id"])
    op.create_index(
        "idx_positions_snapshot_notnull",
        "positions",
        ["snapshot_id"],
        postgresql_where=sa.text("snapshot_id IS NOT NULL"),
    )

    # 2. asset_accounts.manual_positions JSONB → positions (snapshot_id IS NULL)
    conn = op.get_bind()
    accounts = conn.execute(
        sa.text(
            "SELECT id, manual_positions FROM asset_accounts WHERE manual_positions IS NOT NULL"
        )
    ).fetchall()

    for row in accounts:
        acc_id = row[0]
        positions_json = row[1] or []
        for p in positions_json:
            if not p.get("ticker"):
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO positions "
                    "(id, account_id, snapshot_id, ticker, name, market, qty, avg_price, "
                    " avg_price_usd, current_price, value_krw, currency, usd_rate) "
                    "VALUES "
                    "(gen_random_uuid(), :acc_id, NULL, :ticker, :name, :market, :qty, "
                    ":avg_price, :avg_price_usd, :current_price, :value_krw, :currency, :usd_rate)"
                ),
                {
                    "acc_id": acc_id,
                    "ticker": p.get("ticker", ""),
                    "name": p.get("name", ""),
                    "market": p.get("market", "KOSPI"),
                    "qty": float(p.get("qty", 0)),
                    "avg_price": float(p.get("avg_price", 0)),
                    "avg_price_usd": float(p["avg_price_usd"]) if p.get("avg_price_usd") else None,
                    "current_price": float(p.get("current_price"))
                    if p.get("current_price")
                    else None,
                    "value_krw": float(p.get("value_krw")) if p.get("value_krw") else None,
                    "currency": p.get("currency", "KRW"),
                    "usd_rate": float(p["usd_rate"]) if p.get("usd_rate") else None,
                },
            )

    # 3. asset_snapshots.positions JSONB → positions (snapshot_id = snap.id)
    snapshots = conn.execute(
        sa.text(
            "SELECT id, account_id FROM asset_snapshots "
            "WHERE positions IS NOT NULL AND account_id IS NOT NULL"
        )
    ).fetchall()

    for snap_row in snapshots:
        snap_id = snap_row[0]
        acc_id = snap_row[1]
        snap_positions = conn.execute(
            sa.text("SELECT positions FROM asset_snapshots WHERE id = :sid"),
            {"sid": snap_id},
        ).fetchone()
        if not snap_positions or not snap_positions[0]:
            continue
        for p in snap_positions[0]:
            if not p.get("ticker"):
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO positions "
                    "(id, account_id, snapshot_id, ticker, name, market, qty, avg_price, "
                    " avg_price_usd, current_price, value_krw, currency, usd_rate) "
                    "VALUES "
                    "(gen_random_uuid(), :acc_id, :snap_id, :ticker, :name, :market, :qty, "
                    ":avg_price, :avg_price_usd, :current_price, :value_krw, :currency, :usd_rate)"
                ),
                {
                    "acc_id": acc_id,
                    "snap_id": snap_id,
                    "ticker": p.get("ticker", ""),
                    "name": p.get("name", ""),
                    "market": p.get("market", "KOSPI"),
                    "qty": float(p.get("qty", 0)),
                    "avg_price": float(p.get("avg_price", 0)),
                    "avg_price_usd": float(p["avg_price_usd"]) if p.get("avg_price_usd") else None,
                    "current_price": float(p.get("current_price"))
                    if p.get("current_price")
                    else None,
                    "value_krw": float(p.get("value_krw") or p.get("value_usd", 0) or 0) or None,
                    "currency": p.get("currency", "KRW"),
                    "usd_rate": float(p["usd_rate"]) if p.get("usd_rate") else None,
                },
            )

    # 4. JSONB 컬럼 DROP
    op.drop_column("asset_accounts", "manual_positions")
    op.drop_column("asset_snapshots", "positions")


def downgrade() -> None:
    # 1. JSONB 컬럼 복구
    op.add_column("asset_accounts", sa.Column("manual_positions", JSONB, nullable=True))
    op.add_column("asset_snapshots", sa.Column("positions", JSONB, nullable=True))

    # 2. 역마이그레이션: positions → JSONB
    import json

    conn = op.get_bind()

    # account 현재 포지션 (snapshot_id IS NULL)
    acc_ids = conn.execute(
        sa.text("SELECT DISTINCT account_id FROM positions WHERE snapshot_id IS NULL")
    ).fetchall()
    for (acc_id,) in acc_ids:
        rows = conn.execute(
            sa.text("SELECT * FROM positions WHERE account_id = :aid AND snapshot_id IS NULL"),
            {"aid": acc_id},
        ).fetchall()
        pos_list = [
            {
                "ticker": r.ticker,
                "name": r.name,
                "market": r.market,
                "qty": float(r.qty),
                "avg_price": float(r.avg_price),
                "avg_price_usd": float(r.avg_price_usd) if r.avg_price_usd else None,
                "current_price": float(r.current_price) if r.current_price else None,
                "value_krw": float(r.value_krw) if r.value_krw else None,
                "currency": r.currency,
                "usd_rate": float(r.usd_rate) if r.usd_rate else None,
            }
            for r in rows
        ]
        conn.execute(
            sa.text("UPDATE asset_accounts SET manual_positions = :p::jsonb WHERE id = :aid"),
            {"p": json.dumps(pos_list), "aid": acc_id},
        )

    # snapshot 포지션 (snapshot_id IS NOT NULL)
    snap_ids = conn.execute(
        sa.text("SELECT DISTINCT snapshot_id FROM positions WHERE snapshot_id IS NOT NULL")
    ).fetchall()
    for (snap_id,) in snap_ids:
        rows = conn.execute(
            sa.text("SELECT * FROM positions WHERE snapshot_id = :sid"),
            {"sid": snap_id},
        ).fetchall()
        pos_list = [
            {
                "ticker": r.ticker,
                "name": r.name,
                "market": r.market,
                "qty": float(r.qty),
                "avg_price": float(r.avg_price),
                "current_price": float(r.current_price) if r.current_price else None,
                "value_krw": float(r.value_krw) if r.value_krw else None,
                "currency": r.currency,
            }
            for r in rows
        ]
        conn.execute(
            sa.text("UPDATE asset_snapshots SET positions = :p::jsonb WHERE id = :sid"),
            {"p": json.dumps(pos_list), "sid": snap_id},
        )

    # 3. positions 테이블 DROP
    op.drop_index("idx_positions_snapshot_notnull", table_name="positions")
    op.drop_index("idx_positions_account_snapshot", table_name="positions")
    op.drop_table("positions")
