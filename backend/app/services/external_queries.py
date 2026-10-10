"""자매 앱(nestlio) 전용 외부 API(`api/v1/external.py`)가 쓰는 조회 — 라우터에 SQL을 두지 않기 위해 분리했다.

- `find_by_external_ref`: POST /external/transactions 멱등 처리(같은 사용자·같은 키면 기존 행).
- `monthly_net_deposits_by_account`: 계좌별 월 순입금(DEPOSIT − WITHDRAWAL). nestlio가 이미 push한 내역은
  `external_ref` 접두사로 뺀다 — nestlio는 자기 가계부 거래를 이미 목표 실적에 넣고 있어, 증권사에서 growlio로
  직접 들어온 입금만 더하면 이중 집계 없이 "실제로 모은 돈"이 된다.
- `account_scoped_performance`: 지정 계좌만의 XIRR — 대시보드 XIRR(`returns_calculator.calc_xirr`)은 사용자
  전체 계좌 기준이라 nestlio 목표에 연동된 계좌들의 실제 수익률과 다를 수 있다.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, Transaction
from app.services.returns_calculator import xirr
from app.services.snapshot_service import get_latest_snapshot
from app.utils.kst import today_kst

_FLOW_TYPES = ("DEPOSIT", "WITHDRAWAL")


async def find_by_external_ref(db: AsyncSession, user_id: uuid.UUID, external_ref: str) -> Transaction | None:
    return await db.scalar(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.external_ref == external_ref)
    )


async def monthly_net_deposits_by_account(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_ids: list[uuid.UUID],
    start_month: str,
    exclude_ref_prefix: str | None,
) -> list[dict]:
    """[{account_id, month: "YYYY-MM", net_deposit_krw}] — 순입금이 있는 (계좌, 월)만. 호출자 소유·활성 계좌만
    집계한다(남의 계좌나 삭제(`is_active=False`)된 계좌 id를 넘기면 그 계좌는 빈 결과)."""
    if not account_ids:
        return []
    month = func.to_char(Transaction.transaction_date, "YYYY-MM")
    net = func.sum(case((Transaction.transaction_type == "DEPOSIT", Transaction.amount), else_=-Transaction.amount))
    query = (
        select(Transaction.account_id, month.label("month"), net.label("net"))
        .join(AssetAccount, AssetAccount.id == Transaction.account_id)
        .where(
            Transaction.user_id == user_id,
            AssetAccount.is_active.is_(True),
            Transaction.account_id.in_(account_ids),
            Transaction.transaction_type.in_(_FLOW_TYPES),
            month >= start_month,
        )
        .group_by(Transaction.account_id, month)
        .order_by(month)
    )
    if exclude_ref_prefix:
        query = query.where(
            (Transaction.external_ref.is_(None)) | (~Transaction.external_ref.startswith(exclude_ref_prefix))
        )
    rows = (await db.execute(query)).all()
    return [
        {"account_id": str(row.account_id), "month": row.month, "net_deposit_krw": float(row.net)}
        for row in rows
        if row.net
    ]


def build_account_cashflows(
    flows: list[tuple[date, str, float]], current_value: float, today: date
) -> list[tuple[date, float]]:
    """XIRR 현금흐름 — 입금은 투자자 관점의 유출(−), 출금은 유입(+), 마지막에 현재 평가액을 유입으로.
    `returns_calculator.calc_xirr`와 같은 부호 규칙이다."""
    cashflows = [(d, -amount if tx_type == "DEPOSIT" else amount) for d, tx_type, amount in flows]
    cashflows.append((today, current_value))
    return cashflows


async def account_scoped_performance(db: AsyncSession, user_id: uuid.UUID, account_ids: list[uuid.UUID]) -> dict:
    """{xirr_pct, current_value_krw, net_invested_krw, account_count} — 지정 계좌 중 호출자 소유·활성 계좌만 본다.
    입출금 내역이 없거나 XIRR이 수렴하지 않으면 xirr_pct는 None."""
    owned = (
        await db.scalars(
            select(AssetAccount.id).where(
                AssetAccount.user_id == user_id, AssetAccount.id.in_(account_ids), AssetAccount.is_active.is_(True)
            )
        )
    ).all()
    if not owned:
        return {"xirr_pct": None, "current_value_krw": 0.0, "net_invested_krw": 0.0, "account_count": 0}

    current_value = 0.0
    for account_id in owned:
        snapshot = await get_latest_snapshot(db, account_id)
        if snapshot is not None:
            current_value += float(snapshot.amount_krw)

    rows = (
        await db.execute(
            select(Transaction.transaction_date, Transaction.transaction_type, Transaction.amount)
            .where(
                Transaction.user_id == user_id,
                Transaction.account_id.in_(owned),
                Transaction.transaction_type.in_(_FLOW_TYPES),
            )
            .order_by(Transaction.transaction_date)
        )
    ).all()
    flows = [(row.transaction_date, row.transaction_type, float(row.amount)) for row in rows]
    net_invested = sum(amount if tx_type == "DEPOSIT" else -amount for _, tx_type, amount in flows)
    xirr_pct = None
    if flows:
        cashflows = build_account_cashflows(flows, current_value, today_kst())
        loop = asyncio.get_running_loop()
        xirr_pct = await loop.run_in_executor(None, xirr, cashflows)
    return {
        "xirr_pct": xirr_pct,
        "current_value_krw": current_value,
        "net_invested_krw": net_invested,
        "account_count": len(owned),
    }
