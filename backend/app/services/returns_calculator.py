"""수익률 및 XIRR 계산 — 순수 수학 함수 + DB 조회."""
from __future__ import annotations

import asyncio
import uuid
from datetime import date

from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Transaction

_XIRR_INITIAL_RATE = 0.1
_XIRR_MAX_ITERATIONS = 200


def xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """Newton-Raphson XIRR. cashflows: [(date, amount)] 음수=유출, 양수=유입."""
    if len(cashflows) < 2:
        return None
    amounts = [a for _, a in cashflows]
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    d0 = min(d for d, _ in cashflows)
    days = [(d - d0).days for d, _ in cashflows]

    pairs = list(zip(amounts, days, strict=True))
    rate = _XIRR_INITIAL_RATE
    for _ in range(_XIRR_MAX_ITERATIONS):
        try:
            npv = sum(cf / (1 + rate) ** (d / 365.0) for cf, d in pairs)
            dnpv = sum(
                -cf * (d / 365.0) / (1 + rate) ** (d / 365.0 + 1) for cf, d in pairs
            )
        except (ZeroDivisionError, OverflowError):
            return None
        if abs(dnpv) < 1e-12:
            max_cf = max(abs(cf) for cf, _ in pairs)
            if max_cf > 0 and abs(npv) / max_cf < 1e-6:
                return round(rate * 100, 2)
            return None
        new_rate = rate - npv / dnpv
        if abs(new_rate - rate) < 1e-7:
            result = round(new_rate * 100, 2)
            return result if -99 < result < 1000 else None
        rate = min(max(new_rate, -0.99), 10.0)
    return None


def calc_returns(
    current_total: float, base: float, first_date: date | None
) -> tuple[float | None, float | None]:
    """연환산 수익률과 누적 수익률을 반환. (annualized, cumulative)"""
    if base <= 0 or not first_date:
        return None, None

    today = date.today()
    if first_date >= today:
        return None, None
    months = max((today.year - first_date.year) * 12 + (today.month - first_date.month), 1)
    cumulative = (current_total / base - 1) * 100
    annualized = ((current_total / base) ** (12 / months) - 1) * 100
    return annualized, cumulative


async def calc_xirr(
    user_id: uuid.UUID, current_total: float, db: AsyncSession
) -> tuple[float | None, bool]:
    """Transaction 기반 XIRR 계산. 트랜잭션 없으면 스냅샷으로 추정."""

    result = await db.execute(
        select(Transaction.transaction_date, Transaction.transaction_type, Transaction.amount)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type.in_(["DEPOSIT", "WITHDRAWAL"]),
        )
        .order_by(asc(Transaction.transaction_date))
    )
    rows = result.all()

    if not rows:
        snap_result = await db.execute(
            select(
                AssetSnapshot.snapshot_date,
                func.sum(AssetSnapshot.amount_krw).label("total"),
            )
            .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
            .where(
                AssetSnapshot.user_id == user_id,
                AssetAccount.is_active == True,  # noqa: E712
                AssetAccount.include_in_total == True,  # noqa: E712
            )
            .group_by(AssetSnapshot.snapshot_date)
            .order_by(asc(AssetSnapshot.snapshot_date))
            .limit(1)
        )
        first = snap_result.first()
        today = date.today()
        if not first or float(first.total) <= 0 or first.snapshot_date >= today:
            return None, False
        cashflows: list[tuple[date, float]] = [
            (first.snapshot_date, -float(first.total)),
            (today, current_total),
        ]
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, xirr, cashflows), True

    cashflows = []
    for row in rows:
        if row.transaction_type == "DEPOSIT":
            cashflows.append((row.transaction_date, -float(row.amount)))
        else:
            cashflows.append((row.transaction_date, float(row.amount)))

    cashflows.append((date.today(), current_total))
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, xirr, cashflows), False
