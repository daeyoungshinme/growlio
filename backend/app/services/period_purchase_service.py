"""기간별(월/연) 매수 종목과 그 매수분의 수익률 — `GET /trades/period-summary`.

브로커 sync는 체결내역을 가져오지 않으므로 기본은 **일별 스냅샷 포지션 추정**이다.
연속한 두 스냅샷 사이에서 (계좌, ticker, market)별로 보유 수량이 늘면 매수, 줄면 매도로 본다.
- 매수 단가: 이동평균 평단 역산 `(q1·a1 − q0·a0) / Δq`. 해외 종목은 원화 평단이 당일 환율로 매일
  재환산되므로(`providers/base.py`) USD 평단(`avg_price_usd`)으로 역산한 뒤 그 스냅샷의 `usd_rate`로
  환산한다. 역산값이 비정상(≤0, 직후 평단 대비 ±50% 밖)이면 그날 현재가→평단 순으로 대체한다.
- 매도: 이동평균 관례대로 보유분 중 이번 기간 매수분 비율만큼 차감한다. 매도 단가는 그 스냅샷
  현재가로 추정한다(실현손익 추정치).
- 매수는 기간 안에서만 집계하고, 매도는 기간 이후(오늘까지)도 반영한다. "이번 기간에 산 것이 지금
  어떻게 됐나"를 보여주기 위해서다.

사용자가 `TradeRecord`로 기간 내 매매를 직접 기록한 (계좌, ticker, market)은 추정 대신 기록으로
계산한다(source=MANUAL). 수기 매도는 이번 기간 매수분에서 차감한다. 기록상 남은 수량이 현재 보유
수량보다 많으면 현재 보유 수량으로 맞추고 `partially_sold`로 표시한다.

계좌의 기간 시작 이전 스냅샷이 없으면(기간 중 등록), 첫 스냅샷 보유분을 기존 보유로 간주하고
`tracking_started`에 기록한다. 그날 이전 매수는 보이지 않는다.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import POSITION_STOCK_ASSET_TYPES
from app.enums import TradeSide
from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.models.trade import TradeRecord
from app.services._account_queries import active_accounts_stmt

SOURCE_ESTIMATED = "ESTIMATED"
SOURCE_MANUAL = "MANUAL"

_IMPLIED_PRICE_TOLERANCE = 0.5  # 역산 단가가 직후 평단의 ±50% 밖이면 비정상으로 본다
_QTY_EPS = 1e-6

Key = tuple[str, str]  # (ticker, market)


@dataclass
class PosState:
    """스냅샷 1개 시점의 종목 상태(계산에 필요한 필드만)."""

    qty: float
    avg_price: float  # KRW
    avg_price_usd: float | None = None
    current_price: float | None = None  # KRW
    usd_rate: float | None = None
    name: str = ""


@dataclass
class Lot:
    """이번 기간 매수분 누적 상태."""

    bought_qty: float = 0.0
    bought_cost: float = 0.0
    qty: float = 0.0
    cost: float = 0.0
    realized_pnl: float = 0.0
    realized_basis: float = 0.0
    first_buy_date: date | None = None
    partially_sold: bool = False
    price_estimated: bool = False

    def buy(self, qty: float, unit_price: float, on: date, fee: float = 0.0) -> None:
        amount = qty * unit_price + fee
        self.bought_qty += qty
        self.bought_cost += amount
        self.qty += qty
        self.cost += amount
        if self.first_buy_date is None or on < self.first_buy_date:
            self.first_buy_date = on

    def sell(self, qty: float, unit_price: float | None, fee: float = 0.0) -> None:
        """lot에서 qty만큼 이동평균 원가로 차감. unit_price가 없으면 실현손익 0으로 처리."""
        qty = min(qty, self.qty)
        if qty <= _QTY_EPS:
            return
        basis = self.cost * qty / self.qty
        proceeds = qty * unit_price - fee if unit_price else basis
        self.realized_pnl += proceeds - basis
        self.realized_basis += basis
        self.qty -= qty
        self.cost -= basis
        self.partially_sold = True
        if self.qty <= _QTY_EPS:
            self.qty = 0.0
            self.cost = 0.0


def _implied_unit_price_krw(prev: PosState | None, cur: PosState, added_qty: float) -> tuple[float, bool]:
    """수량 증가분의 매수 단가(KRW)와 대체 사용 여부를 반환한다."""
    q0 = prev.qty if prev else 0.0
    if cur.avg_price_usd and cur.usd_rate and (prev is None or prev.avg_price_usd is not None):
        a0_usd = (prev.avg_price_usd or 0.0) if prev else 0.0
        implied_usd = (cur.qty * cur.avg_price_usd - q0 * a0_usd) / added_qty
        implied = implied_usd * cur.usd_rate
        reference = cur.avg_price_usd * cur.usd_rate
    else:
        a0 = prev.avg_price if prev else 0.0
        implied = (cur.qty * cur.avg_price - q0 * a0) / added_qty
        reference = cur.avg_price

    lo, hi = reference * (1 - _IMPLIED_PRICE_TOLERANCE), reference * (1 + _IMPLIED_PRICE_TOLERANCE)
    if implied > 0 and (reference <= 0 or lo <= implied <= hi):
        return implied, False
    fallback = cur.current_price or cur.avg_price or 0.0
    return float(fallback), True


def estimate_lots(
    series: list[tuple[date, dict[Key, PosState]]],
    start: date,
    end: date,
) -> dict[Key, Lot]:
    """날짜순 스냅샷 시계열(첫 원소=기준 스냅샷)에서 기간 [start, end] 매수분 lot을 추정한다.

    순수 함수. series[0]은 기준(이 시점 보유분은 기존 보유)이며, 그 이후 원소 사이의 변화만 매매로 본다.
    """
    lots: dict[Key, Lot] = {}
    if not series:
        return lots
    prev_states = series[0][1]
    for snap_date, states in series[1:]:
        for key in set(prev_states) | set(states):
            prev = prev_states.get(key)
            cur = states.get(key)
            q0 = prev.qty if prev else 0.0
            q1 = cur.qty if cur else 0.0
            delta = q1 - q0
            if delta > _QTY_EPS and cur is not None and start <= snap_date <= end:
                unit, fallback = _implied_unit_price_krw(prev, cur, delta)
                lot = lots.setdefault(key, Lot())
                lot.buy(delta, unit, snap_date)
                lot.price_estimated = lot.price_estimated or fallback
            elif delta < -_QTY_EPS and key in lots and q0 > _QTY_EPS:
                lot = lots[key]
                sold_from_lot = -delta * (lot.qty / q0)
                sell_price = (cur.current_price if cur else None) or (prev.current_price if prev else None)
                lot.sell(sold_from_lot, sell_price)
        prev_states = states
    return lots


def lots_from_trades(trades: list[Any], start: date, end: date) -> dict[Key, Lot]:
    """수기 매매 기록으로 lot 계산(순수 함수). BUY는 기간 내만, SELL은 기간 시작 이후 전부 반영."""
    lots: dict[Key, Lot] = {}
    for t in sorted(trades, key=lambda t: (t.trade_date, 0 if t.side == TradeSide.BUY else 1)):
        key = (t.ticker, t.market)
        qty = float(t.qty)
        price = float(t.price_krw)
        fee = float(t.fee or 0)
        if t.side == TradeSide.BUY:
            if start <= t.trade_date <= end:
                lots.setdefault(key, Lot()).buy(qty, price, t.trade_date, fee)
        elif t.trade_date >= start and key in lots:
            lots[key].sell(qty, price, fee)
    return lots


def _build_item(
    account: AssetAccount,
    key: Key,
    lot: Lot,
    current: PosState | None,
    source: str,
    name: str,
) -> dict[str, Any]:
    held_qty = lot.qty
    held_cost = lot.cost
    if source == SOURCE_MANUAL:
        # 기록 밖에서(브로커 앱 등) 판 경우: 현재 보유 수량으로 상한
        now_qty = current.qty if current else 0.0
        if held_qty > now_qty + _QTY_EPS:
            held_cost = held_cost * (now_qty / held_qty) if held_qty else 0.0
            held_qty = now_qty
            lot.partially_sold = True
    cur_price = (current.current_price or current.avg_price) if current else None
    # 현재가를 알 수 없으면 원가로 평가(손익 0) — 음수 손익으로 왜곡하지 않는다
    value = held_qty * cur_price if cur_price is not None else held_cost
    unrealized = value - held_cost if held_qty > _QTY_EPS else 0.0
    total_pnl = unrealized + lot.realized_pnl
    basis = held_cost + lot.realized_basis
    return {
        "account_id": account.id,
        "account_name": account.name,
        "ticker": key[0],
        "market": key[1],
        "name": name,
        "source": source,
        "bought_qty": round(lot.bought_qty, 4),
        "bought_amount_krw": round(lot.bought_cost, 2),
        "avg_buy_price_krw": round(lot.bought_cost / lot.bought_qty, 2) if lot.bought_qty else 0.0,
        "held_qty": round(held_qty, 4),
        "held_cost_krw": round(held_cost, 2),
        "current_price_krw": cur_price,
        "value_krw": round(value, 2),
        "unrealized_pnl_krw": round(unrealized, 2),
        "realized_pnl_krw": round(lot.realized_pnl, 2),
        "total_pnl_krw": round(total_pnl, 2),
        "cost_basis_krw": round(basis, 2),
        "return_pct": round(total_pnl / basis * 100, 2) if basis > 0 else None,
        "first_buy_date": lot.first_buy_date,
        "partially_sold": lot.partially_sold,
        "price_estimated": lot.price_estimated,
    }


def _summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    bought = sum(i["bought_amount_krw"] for i in items)
    held_cost = sum(i["held_cost_krw"] for i in items)
    value = sum(i["value_krw"] for i in items)
    realized = sum(i["realized_pnl_krw"] for i in items)
    total_pnl = sum(i["total_pnl_krw"] for i in items)
    basis = sum(i["cost_basis_krw"] for i in items)
    return {
        "bought_amount_krw": round(bought, 2),
        "held_cost_krw": round(held_cost, 2),
        "value_krw": round(value, 2),
        "realized_pnl_krw": round(realized, 2),
        "total_pnl_krw": round(total_pnl, 2),
        "return_pct": round(total_pnl / basis * 100, 2) if basis > 0 else None,
    }


def _to_state(p: Position) -> PosState:
    return PosState(
        qty=float(p.qty or 0),
        avg_price=float(p.avg_price or 0),
        avg_price_usd=float(p.avg_price_usd) if p.avg_price_usd else None,
        current_price=float(p.current_price) if p.current_price else None,
        usd_rate=float(p.usd_rate) if p.usd_rate else None,
        name=p.name or "",
    )


def _merge_state(states: dict[Key, PosState], p: Position) -> None:
    """같은 스냅샷 안 동일 ticker+market 행(국내/해외 분리 등)은 수량 가중 합산."""
    key = (p.ticker, p.market)
    s = _to_state(p)
    existing = states.get(key)
    if existing is None:
        states[key] = s
        return
    total = existing.qty + s.qty
    if total > 0:
        existing.avg_price = (existing.avg_price * existing.qty + s.avg_price * s.qty) / total
        if existing.avg_price_usd is not None and s.avg_price_usd is not None:
            existing.avg_price_usd = (existing.avg_price_usd * existing.qty + s.avg_price_usd * s.qty) / total
    existing.qty = total
    existing.current_price = existing.current_price or s.current_price


async def _load_series(
    db: AsyncSession, account_ids: list[uuid.UUID], start: date, today: date
) -> tuple[dict[uuid.UUID, list[tuple[date, dict[Key, PosState]]]], set[uuid.UUID]]:
    """계좌별 [기준 스냅샷] + 기간 시작~오늘 스냅샷 시계열과, 기준 스냅샷이 없던 계좌 집합을 반환."""
    baseline_rows = await db.execute(
        select(AssetSnapshot.account_id, func.max(AssetSnapshot.snapshot_date))
        .where(AssetSnapshot.account_id.in_(account_ids), AssetSnapshot.snapshot_date < start)
        .group_by(AssetSnapshot.account_id)
    )
    baseline_date: dict[uuid.UUID, date] = {acc_id: d for acc_id, d in baseline_rows.all()}
    lower = min([start, *baseline_date.values()])

    snap_rows = await db.execute(
        select(AssetSnapshot.id, AssetSnapshot.account_id, AssetSnapshot.snapshot_date).where(
            AssetSnapshot.account_id.in_(account_ids),
            AssetSnapshot.snapshot_date >= lower,
            AssetSnapshot.snapshot_date <= today,
        )
    )
    snap_meta: dict[uuid.UUID, tuple[uuid.UUID, date]] = {}
    for snap_id, acc_id, snap_date in snap_rows.all():
        floor = baseline_date.get(acc_id, start)
        if snap_date >= floor:
            snap_meta[snap_id] = (acc_id, snap_date)

    states_by_snap: dict[uuid.UUID, dict[Key, PosState]] = defaultdict(dict)
    if snap_meta:
        pos_rows = await db.execute(
            select(Position)
            .join(AssetSnapshot, Position.snapshot_id == AssetSnapshot.id)
            .where(
                AssetSnapshot.account_id.in_(account_ids),
                AssetSnapshot.snapshot_date >= lower,
                AssetSnapshot.snapshot_date <= today,
            )
        )
        for p in pos_rows.scalars().all():
            if p.snapshot_id in snap_meta:
                _merge_state(states_by_snap[p.snapshot_id], p)

    series: dict[uuid.UUID, list[tuple[date, dict[Key, PosState]]]] = defaultdict(list)
    for snap_id, (acc_id, snap_date) in snap_meta.items():
        series[acc_id].append((snap_date, states_by_snap.get(snap_id, {})))
    for acc_series in series.values():
        acc_series.sort(key=lambda x: x[0])
    tracking_started = {acc_id for acc_id in series if acc_id not in baseline_date}
    return series, tracking_started


async def _load_current_positions(
    db: AsyncSession, account_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[Key, PosState]]:
    """스냅샷이 없는 계좌용 현재 포지션(snapshot_id IS NULL)."""
    result: dict[uuid.UUID, dict[Key, PosState]] = defaultdict(dict)
    if not account_ids:
        return result
    rows = await db.execute(
        select(Position).where(Position.account_id.in_(account_ids), Position.snapshot_id.is_(None))
    )
    for p in rows.scalars().all():
        _merge_state(result[p.account_id], p)
    return result


async def get_period_purchases(
    db: AsyncSession,
    user_id: uuid.UUID,
    start: date,
    end: date,
    today: date,
    account_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """기간 [start, end] 매수 종목별 현황과 합계. today는 매도·현재가 반영 상한(KST 오늘)."""
    end = min(end, today)
    stmt = active_accounts_stmt(user_id).where(AssetAccount.asset_type.in_(POSITION_STOCK_ASSET_TYPES))
    if account_id:
        stmt = stmt.where(AssetAccount.id == account_id)
    accounts = list((await db.execute(stmt)).scalars().all())
    empty = {"start": start, "end": end, "items": [], "summary": _summarize([]), "tracking_started": []}
    if not accounts or start > end:
        return empty

    account_ids = [a.id for a in accounts]
    series, tracking_started = await _load_series(db, account_ids, start, today)

    trade_rows = await db.execute(
        select(TradeRecord).where(
            TradeRecord.user_id == user_id,
            TradeRecord.account_id.in_(account_ids),
            TradeRecord.trade_date >= start,
            TradeRecord.trade_date <= today,
        )
    )
    trades_by_account: dict[uuid.UUID, list[TradeRecord]] = defaultdict(list)
    for t in trade_rows.scalars().all():
        if t.account_id is not None:
            trades_by_account[t.account_id].append(t)

    no_snapshot_ids = [a.id for a in accounts if not series.get(a.id)]
    current_fallback = await _load_current_positions(db, no_snapshot_ids)

    items: list[dict[str, Any]] = []
    for account in accounts:
        acc_series = series.get(account.id, [])
        current_states = acc_series[-1][1] if acc_series else current_fallback.get(account.id, {})
        estimated = estimate_lots(acc_series, start, end)
        manual = lots_from_trades(trades_by_account.get(account.id, []), start, end)
        manual_keys = {(t.ticker, t.market) for t in trades_by_account.get(account.id, [])}

        for key, lot in estimated.items():
            if key in manual_keys:
                continue
            current = current_states.get(key)
            name = _name_for(key, current, acc_series)
            items.append(_build_item(account, key, lot, current, SOURCE_ESTIMATED, name))
        for key, lot in manual.items():
            current = current_states.get(key)
            trade_name = next(
                (t.name for t in trades_by_account[account.id] if (t.ticker, t.market) == key and t.name), ""
            )
            name = trade_name or _name_for(key, current, acc_series)
            items.append(_build_item(account, key, lot, current, SOURCE_MANUAL, name))

    items.sort(key=lambda i: i["bought_amount_krw"], reverse=True)
    return {
        "start": start,
        "end": end,
        "items": items,
        "summary": _summarize(items),
        "tracking_started": [
            {"account_id": a.id, "account_name": a.name, "since": series[a.id][0][0]}
            for a in accounts
            if a.id in tracking_started
        ],
    }


def _name_for(key: Key, current: PosState | None, acc_series: list[tuple[date, dict[Key, PosState]]]) -> str:
    if current and current.name:
        return current.name
    for _, states in reversed(acc_series):
        s = states.get(key)
        if s and s.name:
            return s.name
    return key[0]


def resolve_period(period: str, year: int, month: int | None) -> tuple[date, date]:
    """period=month|year → (start, end) — end는 말일 포함."""
    if period == "month":
        if month is None:
            raise ValueError("month is required for period=month")
        next_first = date(year + (month == 12), (month % 12) + 1, 1)
        return date(year, month, 1), next_first - timedelta(days=1)
    return date(year, 1, 1), date(year, 12, 31)
