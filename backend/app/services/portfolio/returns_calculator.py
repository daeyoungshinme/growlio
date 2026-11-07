"""수익률 및 XIRR 계산 — 순수 수학 함수 + DB 조회."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import and_, asc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Transaction
from app.utils.kst import today_kst

_XIRR_INITIAL_RATE = 0.1
_XIRR_MAX_ITERATIONS = 200
# 새 계좌 첫 스냅샷일 ±이 기간 안에 다른 계좌 평가액이 줄었으면 계좌 간 이전으로 본다.
# 동기화가 매일 되지 않는 경우(앱을 며칠 안 연 사용자)를 감안한 폭이다.
_TRANSFER_WINDOW_DAYS = 7


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
        # 기초 잔액이 0이면(입금 전 동기화) 당일 입금은 스냅샷에 반영되지 않은 실제 유출이라 남긴다(plans/117 A3).

    for account_flows in by_account.values():
        cashflows.extend((d, -amount if tx_type == "DEPOSIT" else amount) for d, tx_type, amount in account_flows)
    cashflows.sort(key=lambda cf: cf[0])
    cashflows.append((today, current_total))
    return cashflows


def offset_transfer_openings(
    openings: dict[uuid.UUID, tuple[date, float]],
    snapshots: dict[uuid.UUID, list[tuple[date, float]]],
    flows: list[tuple[uuid.UUID | None, date, str, float]],
    window_days: int = _TRANSFER_WINDOW_DAYS,
) -> dict[uuid.UUID, tuple[date, float]]:
    """계좌 간 이전으로 보이는 만큼 새 계좌의 기초 잔액을 줄인다(plans/117 A2).

    입출금 기록 없이 A를 비우고 새 계좌 B로 옮기면 A·B의 첫 스냅샷이 둘 다 기초 유출로 잡혀
    같은 돈이 두 번 투자금이 된다. B의 첫 스냅샷일 d0 기준으로, 그 전에 이미 있던 다른 계좌 X의
    평가액이 창(d0±창) 안 첫 스냅샷 → d0 이후 첫 스냅샷(없으면 창 안 마지막) 사이에 줄어든 만큼(그 사이 X의 기록된
    출금은 이미 유입으로 잡히므로 뺀다)을 B 기초 잔액에서 상쇄한다. 한 번 상쇄에 쓴 감소분은 다른 새 계좌가
    다시 쓰지 않는다. 시장 하락분이 섞일 수 있지만 상쇄액은 B 기초 잔액을 넘지 않는다.

    snapshots: {account_id: [(날짜, 평가액)] 날짜 오름차순} — 각 d0 주변 창 안의 스냅샷이면 충분하다.
    """
    window = timedelta(days=window_days)
    withdrawals: dict[uuid.UUID, list[tuple[date, float]]] = {}
    for account_id, d, tx_type, amount in flows:
        if account_id is not None and tx_type == "WITHDRAWAL":
            withdrawals.setdefault(account_id, []).append((d, amount))

    consumed: dict[uuid.UUID, float] = {}
    adjusted = dict(openings)
    for new_id, (d0, opening) in sorted(openings.items(), key=lambda kv: kv[1][0]):
        if opening <= 0:
            continue
        available = 0.0
        drops: list[tuple[uuid.UUID, float]] = []
        for other_id, (other_d0, _) in openings.items():
            if other_id == new_id or other_d0 >= d0:
                continue
            series = snapshots.get(other_id, [])
            in_window = [(d, v) for d, v in series if d0 - window <= d <= d0 + window]
            if not in_window or in_window[0][0] >= d0:
                continue
            # 창 안 첫 값(이전 전) → d0 이후 첫 값(없으면 창 안 마지막 값, 이전 후)
            before_d, before_v = in_window[0]
            after_d, after_v = next(((d, v) for d, v in in_window if d >= d0), in_window[-1])
            if after_d <= before_d:
                continue
            recorded = sum(a for d, a in withdrawals.get(other_id, []) if before_d < d <= after_d)
            drop = max(0.0, before_v - after_v - recorded - consumed.get(other_id, 0.0))
            if drop > 0:
                drops.append((other_id, drop))
                available += drop
        offset = min(opening, available)
        if offset <= 0:
            continue
        adjusted[new_id] = (d0, opening - offset)
        remaining = offset
        for other_id, drop in drops:
            use = min(drop, remaining)
            consumed[other_id] = consumed.get(other_id, 0.0) + use
            remaining -= use
            if remaining <= 0:
                break
    return adjusted


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


async def get_transfer_window_snapshots(
    db: AsyncSession, openings: dict[uuid.UUID, tuple[date, float]]
) -> dict[uuid.UUID, list[tuple[date, float]]]:
    """`offset_transfer_openings`용 — 각 첫 스냅샷일 ±창 안의 스냅샷만 한 번에 조회한다."""
    first_dates = sorted({d0 for d0, _ in openings.values()})
    if len(first_dates) < 2:
        return {}  # 첫 스냅샷일이 하나뿐이면 "먼저 있던 계좌"가 없어 상쇄할 대상이 없다
    window = timedelta(days=_TRANSFER_WINDOW_DAYS)
    rows = await db.execute(
        select(AssetSnapshot.account_id, AssetSnapshot.snapshot_date, AssetSnapshot.amount_krw)
        .where(
            AssetSnapshot.account_id.in_(list(openings)),
            or_(*[AssetSnapshot.snapshot_date.between(d - window, d + window) for d in first_dates[1:]]),
        )
        .order_by(asc(AssetSnapshot.snapshot_date))
    )
    result: dict[uuid.UUID, list[tuple[date, float]]] = {}
    for row in rows.all():
        if row.account_id is not None:
            result.setdefault(row.account_id, []).append((row.snapshot_date, float(row.amount_krw or 0)))
    return result


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

    # 사용자 전체 수익률에서만 계좌 간 이전을 상쇄한다 — 계좌 단위 조회(external_queries)에선
    # 이전도 그 계좌의 실제 유입이다.
    openings = offset_transfer_openings(openings, await get_transfer_window_snapshots(db, openings), flows)
    cashflows = anchored_cashflows(flows, openings, current_total, today_kst())
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, xirr_from_cashflows, cashflows), not flows
