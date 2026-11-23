"""낙폭 추매 안내(plans/147·148) — 여윳돈을 지수별 규칙 몫·낙폭 구간으로 나눠 추매 금액과 살 ETF를 안내한다.

- **주문하지 않는다.** 자동 적립 금액·경로도 바꾸지 않는다. 사용자가 직접 사고 "추매했어요"로 기록한다.
- 여윳돈은 사용자당 하나(`DipBuySettings`), 포트폴리오와 무관하다. 규칙(`DipBuyRule`)은 지수(QQQ·SPY)마다 하나.
- 낙폭: `technical_signal_service.get_technical_signals`의 52주 고점 대비(마감 종가, 전술과 같은 캐시).
- 살 종목: 목표 조정 › 추천의 등록 후보 ETF(`UserSettings.goal_candidate_tickers`) 중 그 지수를 추종하는 ETF
  (레버리지·커버드콜 제외). 같은 지수 ETF끼리는 **대안 목록**(계좌에 맞는 것 하나를 고른다) — 나눠 사는 분할이
  아니다. 후보 목록이 아직 시딩 전이어도 여기서 시딩하지 않는다(조회 경로에서 쓰기 금지).
- 사이클 초기화(고점 근처 회복)는 조회·알림 잡에서 낙폭을 볼 때마다 반영한다.
- 전술 연동 적립 자동매수가 방어 국면이라 보류 중이면 그 포트폴리오를 함께 알린다(추매는 그대로 안내).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import OVERSEAS_MARKETS
from app.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.alert import RebalancingAlert
from app.models.dip_buy import DipBuyRule, DipBuySettings
from app.models.portfolio import Portfolio
from app.models.user import UserSettings
from app.services.dca_cash_shortfall_service import DCA_AUTO_BUY_PRESET
from app.services.dip_buy_calculator import (
    DIP_BUY_INDEX_TICKERS,
    INDEX_KEY_BY_TICKER,
    TierStatus,
    cycle_spent,
    due_amount,
    due_tiers,
    next_notify_date,
    reserve_pool,
    rule_base,
    should_reset,
    shrink_allocations,
    tier_price,
    tier_statuses,
    validate_allocations,
    validate_tiers,
)
from app.utils.kst import today_kst
from app.utils.market_hours import is_krx_trading_day

logger = structlog.get_logger()


@dataclass
class EtfOption:
    """안내 금액으로 이 ETF만 산다면 — 같은 지수 ETF끼리는 대안이다."""

    ticker: str
    name: str
    market: str
    price_krw: float
    shares: int
    amount_krw: float
    amount_usd: float | None = None
    price_usd: float | None = None  # 해외 종목 1주 달러가(환율 실값일 때만)
    # 규칙 구간 순서대로 그 구간 도달 시 1주 가격 추정(`tier_price`) — 낙폭을 모르면 빈 목록
    tier_price_krw: list[float] = field(default_factory=list)
    tier_price_usd: list[float] | None = None  # 해외 종목·환율 실값일 때만


@dataclass
class RuleSummary:
    rule: DipBuyRule
    drawdown_pct: float | None
    statuses: list[TierStatus]
    base_krw: float  # 이 규칙 몫(사이클 중이면 고정 기준액)
    spent_krw: float  # 이번 사이클 추매액
    due_amount_krw: float
    due_tiers: list[int]
    etfs: list[EtfOption] = field(default_factory=list)

    @property
    def remaining_krw(self) -> float:
        return max(0.0, self.base_krw - self.spent_krw)

    @property
    def new_due_tiers(self) -> list[int]:
        """아직 구간 도달 알림을 보내지 않은 DUE 구간(ON_REACH)."""
        sent = {int(t) for t in self.rule.notified_tiers or []}
        return [t for t in self.due_tiers if t not in sent]


@dataclass
class UserDipBuySummary:
    settings: DipBuySettings | None
    rules: list[RuleSummary]
    next_notify_date: date | None  # MONTHLY_DAY일 때만
    dca_held_portfolios: list[str] = field(default_factory=list)
    has_candidates: bool = False
    # 지수별 52주 고점 대비 낙폭 — 규칙이 없는 지수 카드도 낙폭을 보여주려고(조회 경로에서만 채움)
    index_drawdowns: dict[str, float | None] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.settings is not None and bool(self.settings.is_active)

    @property
    def due_amount_krw(self) -> float:
        return sum(r.due_amount_krw for r in self.rules)

    @property
    def due_rules(self) -> list[RuleSummary]:
        return [r for r in self.rules if r.due_amount_krw > 0]

    @property
    def reserve_krw(self) -> float:
        return float(self.settings.reserve_krw or 0) if self.settings else 0.0


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


def _opt(v: Any) -> float | None:
    return float(v) if v is not None else None


def reset_if_recovered(rule: DipBuyRule, drawdown_pct: float | None) -> bool:
    """고점 근처로 회복했으면 완료·알림 기록과 기준액을 지운다(다음 하락 사이클). 바뀌었으면 True — 커밋은 호출부."""
    if not should_reset(drawdown_pct, rule.completed, _opt(rule.cycle_base_krw)):
        return False
    rule.completed = []
    rule.cycle_base_krw = None
    rule.notified_tiers = []
    logger.info("dip_buy_cycle_reset", rule_id=str(rule.id), drawdown_pct=drawdown_pct)
    return True


async def get_settings(db: AsyncSession, user_id: uuid.UUID) -> DipBuySettings | None:
    return await db.scalar(select(DipBuySettings).where(DipBuySettings.user_id == user_id))


async def list_rules(db: AsyncSession, user_id: uuid.UUID) -> list[DipBuyRule]:
    stmt = select(DipBuyRule).where(DipBuyRule.user_id == user_id).order_by(DipBuyRule.created_at)
    return list((await db.execute(stmt)).scalars().all())


def summarize_rules(
    settings: DipBuySettings | None, rules: list[DipBuyRule], drawdowns: dict[str, float | None]
) -> list[RuleSummary]:
    """규칙별 몫·구간·안내 금액(순수, DB 없음). 동시 발동이면 규칙 순서대로 남은 여윳돈을 차감한다."""
    reserve = float(settings.reserve_krw or 0) if settings else 0.0
    paused = settings is None or not settings.is_active
    pool = reserve_pool(reserve, [r.completed for r in rules])
    left = reserve
    out: list[RuleSummary] = []
    for rule in rules:
        dd = drawdowns.get(rule.index_ticker)
        base = rule_base(pool, float(rule.allocation_pct), _opt(rule.cycle_base_krw))
        spent = cycle_spent(rule.completed)
        statuses = tier_statuses(rule.tiers, rule.completed, dd, base)
        amount = 0.0 if paused or not rule.is_active else due_amount(statuses, min(max(0.0, base - spent), left))
        left -= amount
        out.append(
            RuleSummary(
                rule=rule,
                drawdown_pct=dd,
                statuses=statuses,
                base_krw=base,
                spent_krw=spent,
                due_amount_krw=amount,
                due_tiers=due_tiers(statuses) if amount > 0 else [],
            )
        )
    return out


def candidate_etfs_for_index(candidates: list[dict] | None, index_ticker: str) -> list[dict]:
    """등록 후보 중 그 지수를 그대로 추종하는 ETF(레버리지·커버드콜 제외, 네트워크 없음)."""
    from app.services.etf.etf_index_classifier import classify_holding

    key = INDEX_KEY_BY_TICKER.get(index_ticker)
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for c in candidates or []:
        ticker, market, name = str(c.get("ticker") or ""), str(c.get("market") or ""), str(c.get("name") or "")
        if not ticker or (ticker, market) in seen:
            continue
        cls = classify_holding(ticker, market, name, None)
        if cls.kind == "INDEX" and cls.index_key == key:
            seen.add((ticker, market))
            out.append({"ticker": ticker, "market": market, "name": name or ticker})
    return out


async def load_goal_candidates(db: AsyncSession, user_id: uuid.UUID) -> list[dict] | None:
    return await db.scalar(select(UserSettings.goal_candidate_tickers).where(UserSettings.user_id == user_id))


async def attach_etfs(
    db: AsyncSession,
    cache: Any,
    user_id: uuid.UUID,
    rules: list[RuleSummary],
    candidates: list[dict] | None,
    *,
    include_waiting: bool = False,
) -> None:
    """안내 금액이 있는 규칙에 ETF별 매수 가능 수량·구간별 예상 1주가를 붙인다(시세 조회 포함). 실패하면 금액만 남긴다.

    `include_waiting`이면 추매할 구간이 없는 규칙에도 붙인다(수량 0) — 화면이 대기 구간의 예상 1주가를 보여주려고.
    알림 잡은 안내할 규칙만 넘기므로 기본값을 쓴다.
    """
    from app.services.market_data.price_service import fetch_prices_batch_krw
    from app.utils.currency import get_live_or_cached_usd_krw

    targets = [
        (r, candidate_etfs_for_index(candidates, r.rule.index_ticker))
        for r in rules
        if include_waiting or r.due_amount_krw > 0
    ]
    tickers = sorted({(c["ticker"], c["market"]) for _, cands in targets for c in cands})
    if not tickers:
        return
    try:
        prices = await fetch_prices_batch_krw(user_id, tickers, db, cache)
        rate, rate_is_live = await get_live_or_cached_usd_krw(cache)
    except Exception as exc:
        logger.warning("dip_buy_etf_price_failed", user_id=str(user_id), error=str(exc))
        return
    for summary, cands in targets:
        for c in cands:
            price = float(prices.get(c["ticker"]) or 0)
            if price <= 0:
                continue
            shares = math.floor(summary.due_amount_krw / price)
            value = round(shares * price, 0)
            overseas = c["market"] in OVERSEAS_MARKETS
            usd_live = overseas and rate_is_live and rate > 0
            at_tiers = [tier_price(price, summary.drawdown_pct, t["drawdown_pct"]) for t in summary.rule.tiers or []]
            tier_krw = [round(p, 0) for p in at_tiers if p is not None]
            summary.etfs.append(
                EtfOption(
                    ticker=c["ticker"],
                    name=c["name"],
                    market=c["market"],
                    price_krw=round(price, 2),
                    shares=shares,
                    amount_krw=value,
                    amount_usd=round(value / rate, 2) if usd_live else None,
                    price_usd=round(price / rate, 2) if usd_live else None,
                    tier_price_krw=tier_krw,
                    tier_price_usd=[round(p / rate, 2) for p in tier_krw] if usd_live and tier_krw else None,
                )
            )


async def dca_held_portfolios(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """전술 연동 정기 적립식 자동매수 중 지금 방어 국면이라 매수가 보류되는 포트폴리오 이름."""
    from app.services.rebalancing.order_builder import is_market_signal_blocking_auto_mode, tactical_regime_for_gate

    rows = (
        await db.execute(
            select(RebalancingAlert, Portfolio.name)
            .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
            .where(
                RebalancingAlert.user_id == user_id,
                RebalancingAlert.is_active == True,
                RebalancingAlert.account_id.is_not(None),
                RebalancingAlert.market_condition_mode == "TACTICAL",
                *(getattr(RebalancingAlert, f) == v for f, v in DCA_AUTO_BUY_PRESET.items()),
            )
            .order_by(Portfolio.name)
        )
    ).all()
    names: list[str] = []
    for alert, name in rows:
        if name in names:
            continue
        regime = await tactical_regime_for_gate(alert, db)
        if is_market_signal_blocking_auto_mode("TACTICAL", "GREEN", tactical_regime=regime):
            names.append(name)
    return names


async def summarize_user(
    db: AsyncSession,
    cache: Any,
    user_id: uuid.UUID,
    *,
    with_etfs: bool,
    today: date | None = None,
) -> UserDipBuySummary:
    """사용자 추매 안내 판정. 회복한 규칙은 사이클을 초기화해 저장한다."""
    today = today or today_kst()
    settings = await get_settings(db, user_id)
    rules = await list_rules(db, user_id)
    drawdowns = await index_drawdowns(cache) if rules or with_etfs else {}
    if any([reset_if_recovered(r, drawdowns.get(r.index_ticker)) for r in rules]):
        await db.commit()
    summaries = summarize_rules(settings, rules, drawdowns)
    notify_day = (
        next_notify_date(int(settings.notify_day), today, is_krx_trading_day)
        if settings is not None and settings.notify_mode == "MONTHLY_DAY" and settings.notify_day
        else None
    )
    out = UserDipBuySummary(
        settings=settings, rules=summaries, next_notify_date=notify_day, index_drawdowns=dict(drawdowns)
    )
    if not rules:
        return out
    if with_etfs:
        candidates = await load_goal_candidates(db, user_id)
        out.has_candidates = any(candidate_etfs_for_index(candidates, t) for t in DIP_BUY_INDEX_TICKERS)
        await attach_etfs(db, cache, user_id, summaries, candidates, include_waiting=True)
    if out.due_amount_krw > 0:
        out.dca_held_portfolios = await dca_held_portfolios(db, user_id)
    return out


# ── 설정·규칙 CRUD ─────────────────────────────────────────


def _rebase_cycles(rules: list[DipBuyRule], reserve_krw: float) -> None:
    """여윳돈을 고치면 사이클 중 규칙의 기준액 = (새 여윳돈 + 진행 중 사이클 추매 합) × 배분%."""
    pool = reserve_pool(reserve_krw, [r.completed for r in rules])
    for rule in rules:
        if rule.cycle_base_krw is not None:
            rule.cycle_base_krw = round(pool * float(rule.allocation_pct) / 100, 2)


async def upsert_settings(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    reserve_krw: float,
    notify_mode: str,
    notify_day: int | None,
    is_active: bool,
) -> DipBuySettings:
    if notify_mode == "MONTHLY_DAY" and notify_day is None:
        raise BadRequestError("매달 알림 받을 날짜를 정해주세요.")
    settings = await get_settings(db, user_id)
    if settings is None:
        settings = DipBuySettings(user_id=user_id)
        db.add(settings)
    elif float(reserve_krw) != float(settings.reserve_krw or 0):
        _rebase_cycles(await list_rules(db, user_id), float(reserve_krw))
    settings.reserve_krw = float(reserve_krw)
    settings.notify_mode = notify_mode
    settings.notify_day = notify_day if notify_mode == "MONTHLY_DAY" else None
    settings.is_active = is_active
    await db.commit()
    await db.refresh(settings)
    return settings


def _check_rule_input(tiers: list[dict], allocations: list[float]) -> None:
    error = validate_tiers(tiers) or validate_allocations(allocations)
    if error:
        raise BadRequestError(error)


def _shrink_others(
    others: list[DipBuyRule], allocation_pct: float, settings: DipBuySettings | None, all_rules: list[DipBuyRule]
) -> None:
    """새 배분이 들어가도록 다른 규칙 배분을 비율대로 줄인다. 사이클 중인 규칙은 기준액도 새 배분으로 다시 잡는다."""
    shrunk = shrink_allocations([float(r.allocation_pct) for r in others], float(allocation_pct))
    if shrunk is None:
        raise BadRequestError("다른 규칙 배분을 1% 이상 남길 수 없어요. 배분을 더 낮춰주세요.")
    pool = reserve_pool(float(settings.reserve_krw or 0) if settings else 0.0, [r.completed for r in all_rules])
    for rule, pct in zip(others, shrunk, strict=True):
        if pct == float(rule.allocation_pct):
            continue
        rule.allocation_pct = pct
        if rule.cycle_base_krw is not None:
            rule.cycle_base_krw = round(pool * pct / 100, 2)


def _clean_tiers(tiers: list[dict]) -> list[dict]:
    return [{"drawdown_pct": float(t["drawdown_pct"]), "ratio_pct": float(t["ratio_pct"])} for t in tiers]


async def create_rule(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    index_ticker: str,
    allocation_pct: float,
    tiers: list[dict],
    is_active: bool,
    shrink_others: bool = False,
) -> DipBuyRule:
    """`shrink_others`면 배분 합계가 100을 넘을 때 다른 규칙 배분을 비율대로 줄여 맞춘다(아니면 400)."""
    settings = await get_settings(db, user_id)
    if settings is None:
        raise BadRequestError("여윳돈을 먼저 정해주세요.")
    rules = await list_rules(db, user_id)
    if any(r.index_ticker == index_ticker for r in rules):
        raise ConflictError("이 지수의 추매 규칙이 이미 있어요.")
    if shrink_others:
        _shrink_others(rules, allocation_pct, settings, rules)
    _check_rule_input(tiers, [float(r.allocation_pct) for r in rules] + [float(allocation_pct)])
    rule = DipBuyRule(
        user_id=user_id,
        index_ticker=index_ticker,
        allocation_pct=float(allocation_pct),
        tiers=_clean_tiers(tiers),
        completed=[],
        notified_tiers=[],
        is_active=is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def _owned_rule(db: AsyncSession, user_id: uuid.UUID, rule_id: uuid.UUID) -> DipBuyRule:
    rule = await db.scalar(select(DipBuyRule).where(DipBuyRule.id == rule_id, DipBuyRule.user_id == user_id))
    if rule is None:
        raise NotFoundError("추매 규칙을 찾을 수 없습니다")
    return rule


async def update_rule(
    db: AsyncSession,
    user_id: uuid.UUID,
    rule_id: uuid.UUID,
    *,
    index_ticker: str,
    allocation_pct: float,
    tiers: list[dict],
    is_active: bool,
    shrink_others: bool = False,
) -> DipBuyRule:
    rules = await list_rules(db, user_id)
    rule = next((r for r in rules if r.id == rule_id), None)
    if rule is None:
        raise NotFoundError("추매 규칙을 찾을 수 없습니다")
    if any(r.index_ticker == index_ticker and r.id != rule_id for r in rules):
        raise ConflictError("이 지수의 추매 규칙이 이미 있어요.")
    if shrink_others:
        _shrink_others([r for r in rules if r.id != rule_id], allocation_pct, await get_settings(db, user_id), rules)
    _check_rule_input(tiers, [float(r.allocation_pct) for r in rules if r.id != rule_id] + [float(allocation_pct)])
    if index_ticker != rule.index_ticker:
        # 기준 지수를 바꾸면 이전 지수 기준의 사이클 기록은 의미가 없다
        rule.completed = []
        rule.cycle_base_krw = None
        rule.notified_tiers = []
    else:
        # 구간 수가 줄면 사라진 구간의 기록을 버린다
        rule.completed = [c for c in rule.completed or [] if int(c.get("tier", -1)) < len(tiers)]
        rule.notified_tiers = [t for t in rule.notified_tiers or [] if int(t) < len(tiers)]
        if rule.cycle_base_krw is not None and float(allocation_pct) != float(rule.allocation_pct):
            settings = await get_settings(db, user_id)
            pool = reserve_pool(float(settings.reserve_krw or 0) if settings else 0.0, [r.completed for r in rules])
            rule.cycle_base_krw = round(pool * float(allocation_pct) / 100, 2)
    rule.index_ticker = index_ticker
    rule.allocation_pct = float(allocation_pct)
    rule.tiers = _clean_tiers(tiers)
    rule.is_active = is_active
    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_rule(db: AsyncSession, user_id: uuid.UUID, rule_id: uuid.UUID) -> None:
    rule = await _owned_rule(db, user_id, rule_id)
    await db.delete(rule)
    await db.commit()


async def mark_completed(
    db: AsyncSession,
    cache: Any,
    user_id: uuid.UUID,
    rule_id: uuid.UUID,
    amount_krw: float | None,
) -> DipBuyRule:
    """그 규칙의 지금 도달한 미완료 구간을 완료로 기록하고 여윳돈에서 뺀다.

    구간이 여럿이면 안내 금액 비율로 나눠 적는다.
    """
    settings = await get_settings(db, user_id)
    rules = await list_rules(db, user_id)
    rule = next((r for r in rules if r.id == rule_id), None)
    if rule is None or settings is None:
        raise NotFoundError("추매 규칙을 찾을 수 없습니다")
    drawdowns = await index_drawdowns(cache)
    reset_if_recovered(rule, drawdowns.get(rule.index_ticker))
    if not settings.is_active or not rule.is_active:
        raise BadRequestError("꺼 둔 추매 안내는 기록할 수 없어요.")
    summary = next(s for s in summarize_rules(settings, rules, drawdowns) if s.rule is rule)
    due = [s for s in summary.statuses if s["state"] == "DUE"]
    if not due or summary.due_amount_krw <= 0:
        raise BadRequestError("지금 추매할 구간이 없어요.")
    spent = float(amount_krw) if amount_krw is not None else summary.due_amount_krw
    if rule.cycle_base_krw is None:
        rule.cycle_base_krw = summary.base_krw
    weight_total = sum(s["amount_krw"] for s in due) or 1.0
    now = datetime.now(UTC).isoformat()
    rule.completed = [
        *(rule.completed or []),
        *(
            {"tier": s["tier"], "amount_krw": round(spent * s["amount_krw"] / weight_total, 0), "done_at": now}
            for s in due
        ),
    ]
    reserve = float(settings.reserve_krw or 0)
    settings.reserve_krw = round(max(0.0, reserve - spent), 2)
    await db.commit()
    await db.refresh(rule)
    logger.info("dip_buy_completed", rule_id=str(rule.id), tiers=[s["tier"] for s in due], amount_krw=spent)
    return rule
