"""수익률 및 XIRR 계산 — 순수 수학 함수 + DB 조회."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date

from sqlalchemy import and_, asc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Transaction
from app.utils.kst import today_kst

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
            dnpv = sum(-cf * (d / 365.0) / (1 + rate) ** (d / 365.0 + 1) for cf, d in pairs)
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
    current_total: float,
    base: float,
    first_date: date | None,
    net_flows: float = 0.0,
) -> tuple[float | None, float | None]:
    """연환산 수익률과 누적 수익률을 반환. (annualized, cumulative)

    net_flows가 있으면 Modified Dietz 공식 적용 — 입금/출금이 기간 중반에
    발생한다고 가정(0.5 가중치)해 순입금을 수익률 계산에서 제거한다.
    90일 미만 기간은 annualized=None, cumulative만 반환.
    """
    if base <= 0 or not first_date:
        return None, None

    today = today_kst()
    days = (today - first_date).days
    if days < 1:
        return None, None

    weighted_base = base + 0.5 * net_flows
    if weighted_base <= 0:
        return None, None

    gain = current_total - base - net_flows
    cumulative = (gain / weighted_base) * 100

    if days < 90:
        return None, cumulative
    ratio = 1.0 + cumulative / 100.0
    if ratio <= 0:
        return None, cumulative
    annualized = (ratio ** (365.0 / days) - 1) * 100
    if not (-99 < annualized < 1000):
        return None, cumulative
    return annualized, cumulative


def anchored_cashflows(
    flows: list[tuple[uuid.UUID | None, date, str, float]],
    openings: dict[uuid.UUID, tuple[date, float]],
    current_total: float,
    today: date,
) -> list[tuple[date, float]]:
    """XIRR 현금흐름 — 계좌별 첫 스냅샷 평가액(기초 잔액)을 첫 유출로, 그 뒤 입출금, 마지막에 현재 총액을 유입으로.

    flows: [(account_id, 날짜, "DEPOSIT"|"WITHDRAWAL", 금액)] / openings: {account_id: (첫 스냅샷일, 평가액)}.
    입금은 투자자 관점의 유출(−), 출금은 유입(+).

    - 기초 잔액을 빼면 증권사 동기화 계좌처럼 입출금 기록이 거의 없는 계좌의 평가액 전체가 소수의 입금에 대한
      "수익"으로 잡혀 XIRR이 수백 %로 튀거나 범위 밖(None)이 된다(plans/116 A1).
    - 첫 스냅샷일 이전·당일 거래는 그 스냅샷에 이미 반영돼 있으므로 버린다(현금 계좌 첫 잔액 수정은 기준값 자체).
    - 단 그 계좌에 첫 스냅샷보다 **앞선** 거래가 있으면 입력된 거래 이력이 기초 잔액까지 설명한다고 보고
      기초 잔액을 넣지 않는다(과거 입금을 직접 기록한 사용자) — 넣으면 이중 계산된다.
    - 계좌 미지정 입출금과 첫 스냅샷이 없는 계좌의 입출금은 그대로 둔다.
    """
    by_account: dict[uuid.UUID | None, list[tuple[date, str, float]]] = {}
    for account_id, d, tx_type, amount in flows:
        by_account.setdefault(account_id, []).append((d, tx_type, amount))

    cashflows: list[tuple[date, float]] = []
    for account_id, (d0, opening) in openings.items():
        account_flows = by_account.get(account_id, [])
        if any(d < d0 for d, _, _ in account_flows):
            continue
        if opening > 0:
            cashflows.append((d0, -opening))
        by_account[account_id] = [f for f in account_flows if f[0] > d0]

    for account_flows in by_account.values():
        cashflows.extend((d, -amount if tx_type == "DEPOSIT" else amount) for d, tx_type, amount in account_flows)
    cashflows.sort(key=lambda cf: cf[0])
    cashflows.append((today, current_total))
    return cashflows


def xirr_from_cashflows(cashflows: list[tuple[date, float]]) -> float | None:
    """모든 흐름이 같은 날이면(기간 0) 계산하지 않는다 — 도함수가 0이라 초기 추정치가 그대로 반환될 수 있다."""
    if len({d for d, _ in cashflows}) < 2:
        return None
    return xirr(cashflows)


async def get_opening_snapshots(db: AsyncSession, account_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[date, float]]:
    """계좌별 첫 스냅샷 (날짜, 평가액). (account_id, snapshot_date)가 유일하므로 계좌당 1행."""
    if not account_ids:
        return {}
    first = (
        select(AssetSnapshot.account_id, func.min(AssetSnapshot.snapshot_date).label("first_date"))
        .where(AssetSnapshot.account_id.in_(account_ids))
        .group_by(AssetSnapshot.account_id)
        .subquery()
    )
    rows = await db.execute(
        select(AssetSnapshot.account_id, AssetSnapshot.snapshot_date, AssetSnapshot.amount_krw).join(
            first,
            and_(AssetSnapshot.account_id == first.c.account_id, AssetSnapshot.snapshot_date == first.c.first_date),
        )
    )
    return {
        row.account_id: (row.snapshot_date, float(row.amount_krw or 0))
        for row in rows.all()
        if row.account_id is not None
    }


async def calc_xirr(user_id: uuid.UUID, current_total: float, db: AsyncSession) -> tuple[float | None, bool]:
    """계좌별 기초 잔액 + 입출금 기반 XIRR. 두 번째 값은 입출금 기록 없이 스냅샷만으로 추정했는지 여부."""
    account_ids = list(
        (
            await db.scalars(
                select(AssetAccount.id).where(
                    AssetAccount.user_id == user_id,
                    AssetAccount.is_active.is_(True),
                    AssetAccount.include_in_total.is_(True),
                )
            )
        ).all()
    )
    result = await db.execute(
        select(Transaction.account_id, Transaction.transaction_date, Transaction.transaction_type, Transaction.amount)
        # 종료값(current_total)은 활성·합산 계좌만 더하므로 입출금도 같은 계좌 집합으로 거른다 —
        # 삭제(soft)·합산 제외 계좌의 입금만 남으면 XIRR이 크게 음수로 왜곡된다. 계좌 미지정 입출금은 유지.
        .outerjoin(AssetAccount, AssetAccount.id == Transaction.account_id)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type.in_(["DEPOSIT", "WITHDRAWAL"]),
            or_(
                Transaction.account_id.is_(None),
                and_(AssetAccount.is_active == True, AssetAccount.include_in_total == True),
            ),
        )
        .order_by(asc(Transaction.transaction_date))
    )
    flows = [(row.account_id, row.transaction_date, row.transaction_type, float(row.amount)) for row in result.all()]
    openings = await get_opening_snapshots(db, account_ids)
    if not flows and not openings:
        return None, False

    cashflows = anchored_cashflows(flows, openings, current_total, today_kst())
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, xirr_from_cashflows, cashflows), not flows
