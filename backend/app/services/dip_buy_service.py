"""낙폭 추매 안내(plans/147) — 여윳돈을 지수 낙폭 구간별로 나눠 이번 적립일의 추매 금액·종목을 산정한다.

- **주문하지 않는다.** 자동 적립 금액·경로도 바꾸지 않는다. 사용자가 직접 사고 "추매했어요"로 기록한다.
- 낙폭: `technical_signal_service.get_technical_signals`의 52주 고점 대비(마감 종가, 전술과 같은 캐시).
- 종목 분할: 그 포트폴리오 정기 적립식 알림의 계좌 범위·분할 규칙(`plan_generation.dca_items_for_amount`) —
  자동 적립과 같은 규칙이라 "평소 사던 비율대로" 더 산다. 적립식 알림이 없으면 금액만 안내한다.
- 사이클 초기화(고점 근처 회복)는 조회·알림 잡에서 낙폭을 볼 때마다 반영한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import OVERSEAS_MARKETS
from app.exceptions import BadRequestError, NotFoundError
from app.models.alert import RebalancingAlert
from app.models.dip_buy import DipBuyPlan
from app.models.portfolio import Portfolio
from app.services.alerts.calculator import is_auto_schedule_day, next_auto_schedule_date
from app.services.dca_cash_shortfall_service import DCA_AUTO_BUY_PRESET
from app.services.dip_buy_calculator import (
    DIP_BUY_INDEX_TICKERS,
    TierStatus,
    base_amount,
    due_amount,
    due_tiers,
    should_reset,
    tier_statuses,
    validate_tiers,
)
from app.utils.kst import today_kst

logger = structlog.get_logger()


@dataclass
class DipBuyItemRow:
    ticker: str
    name: str
    market: str
    shares: float
    amount_krw: float
    price_krw: float
    amount_usd: float | None = None


@dataclass
class DipBuySummary:
    """한 플랜의 현재 판정 — 종목 분할(`items`)은 `allocate=True`로 만들 때만 채운다."""

    plan: DipBuyPlan
    portfolio: Portfolio
    alert: RebalancingAlert | None
    drawdown_pct: float | None
    statuses: list[TierStatus]
    due_amount_krw: float
    due_tiers: list[int]
    next_run_date: date | None
    is_run_day: bool
    items: list[DipBuyItemRow] = field(default_factory=list)
    leftover_krw: float = 0.0


async def index_drawdowns(cache: Any) -> dict[str, float | None]:
    """지수별 52주 고점 대비 낙폭(%). 조회 실패면 None — 추매를 안내하지 않는다."""
    from app.services.market_signal.technical_signal_service import get_technical_signals

    try:
        signals = await get_technical_signals(cache)
    except Exception as exc:  # 시세 실패가 카드·잡 전체를 깨뜨리지 않게
        logger.warning("dip_buy_drawdown_fetch_failed", error=str(exc))
        return dict.fromkeys(DIP_BUY_INDEX_TICKERS)
    out: dict[str, float | None] = {}
    for ticker in DIP_BUY_INDEX_TICKERS:
        snap = signals.get(ticker)
        value = snap.get("drawdown_pct") if snap else None
        out[ticker] = float(value) if value is not None else None
    return out


async def dca_alert_for_portfolio(
    db: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID
) -> RebalancingAlert | None:
    """이 포트폴리오의 활성 정기 적립식 자동매수 알림(실행 계좌가 있는 첫 행)."""
    return await db.scalar(
        select(RebalancingAlert)
        .where(
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.is_active == True,
            RebalancingAlert.account_id.is_not(None),
            *(getattr(RebalancingAlert, f) == v for f, v in DCA_AUTO_BUY_PRESET.items()),
        )
        .order_by(RebalancingAlert.created_at)
        .limit(1)
    )


def reset_if_recovered(plan: DipBuyPlan, drawdown_pct: float | None) -> bool:
    """고점 근처로 회복했으면 완료 기록·기준액을 지운다(다음 하락 사이클). 바뀌었으면 True — 커밋은 호출부."""
    if not should_reset(drawdown_pct, plan.completed, _opt(plan.cycle_base_krw)):
        return False
    plan.completed = []
    plan.cycle_base_krw = None
    logger.info("dip_buy_cycle_reset", plan_id=str(plan.id), drawdown_pct=drawdown_pct)
    return True


def _opt(v: Any) -> float | None:
    return float(v) if v is not None else None


def _run_dates(alert: RebalancingAlert | None, today: date) -> tuple[date | None, bool]:
    if alert is None:
        return None, False
    if is_auto_schedule_day(alert, today):
        return today, True
    return next_auto_schedule_date(alert, today), False


async def summarize_plan(
    db: AsyncSession,
    plan: DipBuyPlan,
    portfolio: Portfolio,
    drawdown_pct: float | None,
    *,
    today: date | None = None,
) -> DipBuySummary:
    """종목 분할 없이 구간·금액·적립일만 판정한다(DB 조회 1회 — 홈 할 일·잡 사전 판정용)."""
    today = today or today_kst()
    alert = await dca_alert_for_portfolio(db, plan.user_id, plan.portfolio_id)
    reserve = float(plan.reserve_krw or 0)
    statuses = tier_statuses(plan.tiers, plan.completed, drawdown_pct, reserve, _opt(plan.cycle_base_krw))
    amount = due_amount(statuses, reserve) if plan.is_active else 0.0
    next_run, is_run_day = _run_dates(alert, today)
    return DipBuySummary(
        plan=plan,
        portfolio=portfolio,
        alert=alert,
        drawdown_pct=drawdown_pct,
        statuses=statuses,
        due_amount_krw=amount,
        due_tiers=due_tiers(statuses) if amount > 0 else [],
        next_run_date=next_run,
        is_run_day=is_run_day,
    )


async def allocate_items(db: AsyncSession, cache: Any, summary: DipBuySummary) -> None:
    """추매 금액을 정기 적립식과 같은 규칙으로 종목별 수량으로 나눈다(시세 조회 포함). 실패하면 금액만 남긴다."""
    from app.services.rebalancing.plan_generation import dca_items_for_amount
    from app.utils.currency import get_live_or_cached_usd_krw

    alert = summary.alert
    if alert is None or summary.due_amount_krw <= 0:
        return
    try:
        prepared = await dca_items_for_amount(
            alert, summary.portfolio, db, alert.account_id, cache, summary.due_amount_krw
        )
    except Exception as exc:
        logger.warning("dip_buy_allocate_failed", plan_id=str(summary.plan.id), error=str(exc))
        summary.leftover_krw = summary.due_amount_krw
        return
    rows = prepared[2] if prepared else []
    rate, rate_is_live = await get_live_or_cached_usd_krw(cache)
    spent = 0.0
    for item in rows:
        shares = float(item.shares_to_trade or 0)
        price = float(item.current_price_krw or 0)
        value = round(shares * price, 0)
        spent += value
        overseas = item.market in OVERSEAS_MARKETS
        summary.items.append(
            DipBuyItemRow(
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                shares=shares,
                amount_krw=value,
                price_krw=price,
                amount_usd=round(value / rate, 2) if overseas and rate_is_live and rate > 0 else None,
            )
        )
    summary.leftover_krw = round(max(0.0, summary.due_amount_krw - spent), 0)


async def _load_portfolios(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, Portfolio]:
    if not ids:
        return {}
    rows = (
        (
            await db.execute(
                select(Portfolio)
                .where(Portfolio.id.in_(ids))
                .options(selectinload(Portfolio.items), selectinload(Portfolio.linked_accounts))
            )
        )
        .scalars()
        .all()
    )
    return {p.id: p for p in rows}


async def list_plans(db: AsyncSession, user_id: uuid.UUID, *, active_only: bool = False) -> list[DipBuyPlan]:
    stmt = select(DipBuyPlan).where(DipBuyPlan.user_id == user_id)
    if active_only:
        stmt = stmt.where(DipBuyPlan.is_active == True)
    return list((await db.execute(stmt.order_by(DipBuyPlan.created_at))).scalars().all())


async def summarize_user_plans(
    db: AsyncSession,
    cache: Any,
    user_id: uuid.UUID,
    *,
    allocate: bool,
    active_only: bool = False,
    today: date | None = None,
) -> list[DipBuySummary]:
    """사용자 플랜 전부의 판정. 회복한 플랜은 사이클을 초기화해 저장한다."""
    plans = await list_plans(db, user_id, active_only=active_only)
    if not plans:
        return []
    drawdowns = await index_drawdowns(cache)
    if any([reset_if_recovered(p, drawdowns.get(p.index_ticker)) for p in plans]):
        await db.commit()
    portfolios = await _load_portfolios(db, [p.portfolio_id for p in plans])
    out: list[DipBuySummary] = []
    for plan in plans:
        portfolio = portfolios.get(plan.portfolio_id)
        if portfolio is None:
            continue
        summary = await summarize_plan(db, plan, portfolio, drawdowns.get(plan.index_ticker), today=today)
        if allocate:
            await allocate_items(db, cache, summary)
        out.append(summary)
    return out


async def _owned_portfolio(db: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> Portfolio:
    portfolio = await db.scalar(select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id))
    if portfolio is None:
        raise NotFoundError("포트폴리오를 찾을 수 없습니다")
    return portfolio


async def _get_plan(db: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> DipBuyPlan | None:
    return await db.scalar(
        select(DipBuyPlan).where(DipBuyPlan.user_id == user_id, DipBuyPlan.portfolio_id == portfolio_id)
    )


def _completed_total(completed: list | None) -> float:
    return sum(float(c.get("amount_krw") or 0) for c in completed or [])


async def upsert_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    *,
    index_ticker: str,
    reserve_krw: float,
    tiers: list[dict],
    is_active: bool,
) -> DipBuyPlan:
    error = validate_tiers(tiers)
    if error:
        raise BadRequestError(error)
    await _owned_portfolio(db, user_id, portfolio_id)
    plan = await _get_plan(db, user_id, portfolio_id)
    if plan is None:
        plan = DipBuyPlan(user_id=user_id, portfolio_id=portfolio_id, completed=[])
        db.add(plan)
    else:
        if index_ticker != plan.index_ticker:
            # 기준 지수를 바꾸면 이전 지수 기준의 완료 기록은 의미가 없다
            plan.completed = []
            plan.cycle_base_krw = None
        else:
            # 구간 수가 줄면 사라진 구간의 완료 기록을 버린다
            plan.completed = [c for c in plan.completed or [] if int(c.get("tier", -1)) < len(tiers)]
            if plan.cycle_base_krw is not None and float(reserve_krw) != float(plan.reserve_krw or 0):
                # 사이클 중 여윳돈을 고치면 기준액 = 새 잔액 + 이번 사이클에 이미 추매한 금액
                plan.cycle_base_krw = round(float(reserve_krw) + _completed_total(plan.completed), 2)
    plan.index_ticker = index_ticker
    plan.reserve_krw = float(reserve_krw)
    plan.tiers = [{"drawdown_pct": float(t["drawdown_pct"]), "ratio_pct": float(t["ratio_pct"])} for t in tiers]
    plan.is_active = is_active
    await db.commit()
    await db.refresh(plan)
    return plan


async def delete_plan(db: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID) -> None:
    plan = await _get_plan(db, user_id, portfolio_id)
    if plan is None:
        raise NotFoundError("추매 안내 설정을 찾을 수 없습니다")
    await db.delete(plan)
    await db.commit()


async def mark_completed(
    db: AsyncSession,
    cache: Any,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    amount_krw: float | None,
) -> DipBuyPlan:
    """지금 도달한 미완료 구간을 완료로 기록하고 여윳돈에서 뺀다. 구간이 여럿이면 안내 금액 비율로 나눠 적는다."""
    plan = await _get_plan(db, user_id, portfolio_id)
    if plan is None:
        raise NotFoundError("추매 안내 설정을 찾을 수 없습니다")
    drawdown = (await index_drawdowns(cache)).get(plan.index_ticker)
    reset_if_recovered(plan, drawdown)
    reserve = float(plan.reserve_krw or 0)
    statuses = tier_statuses(plan.tiers, plan.completed, drawdown, reserve, _opt(plan.cycle_base_krw))
    due = [s for s in statuses if s["state"] == "DUE"]
    if not due:
        raise BadRequestError("지금 추매할 구간이 없어요.")
    planned = due_amount(statuses, reserve)
    spent = float(amount_krw) if amount_krw is not None else planned
    if plan.cycle_base_krw is None:
        plan.cycle_base_krw = base_amount(reserve, None)
    weight_total = sum(s["amount_krw"] for s in due) or 1.0
    now = datetime.now(UTC).isoformat()
    plan.completed = [
        *(plan.completed or []),
        *(
            {"tier": s["tier"], "amount_krw": round(spent * s["amount_krw"] / weight_total, 0), "done_at": now}
            for s in due
        ),
    ]
    plan.reserve_krw = round(max(0.0, reserve - spent), 2)
    await db.commit()
    await db.refresh(plan)
    logger.info("dip_buy_completed", plan_id=str(plan.id), tiers=[s["tier"] for s in due], amount_krw=spent)
    return plan
