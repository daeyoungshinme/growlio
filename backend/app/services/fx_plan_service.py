"""달러 환전 계획 — 환율의 1년 통계적 위치와 해외 적립에 필요한 달러로 분할 환전 구간을 제안한다(plans/96).

- 위치·범위는 예측이 아니라 과거 1년 종가 분포와 변동성으로 계산한 참고치다.
- 현재값은 앱 전역 실시간 캐시(`get_live_or_cached_usd_krw`)를 쓰고, Yahoo 1년 일봉은 통계 계산에만 쓴다.
  실값이 없으면(콜드스타트+Yahoo 장애) 설정 fallback 대신 1년 일봉 마지막 종가로 대체한다 —
  고정 fallback(1300원)이면 "1년 최저" 판정과 그 아래 목표 환율이 나온다(plans/97 A2).
- 계획 자체는 저장하지 않는다. 구간 목표 환율 알림은 `sync_fx_plan_alerts`가 FX_PLAN 출처로 맞춘다(plans/121) —
  발동 메일·푸시에 구간 금액이 실리고, 다시 등록하면 옛 목표 알림이 교체된다.
"""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Literal

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import (
    BROKER_API_ASSET_TYPES,
    CASH_EQUIVALENT_MARKET,
    DOMESTIC_MARKETS,
    FX_PLAN_ACTION_DAYS,
    FX_PLAN_ALERT_SOURCE,
    MAX_EXCHANGE_RATE_ALERTS_PER_USER,
    ORDER_EXECUTABLE_ASSET_TYPES,
    POSITION_STOCK_ASSET_TYPES,
    uses_krw_overseas_order,
)
from app.core.cache_store import CacheStore
from app.core.database import release_read_connection
from app.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.alert import ExchangeRateAlert, RebalancingAlert
from app.models.asset import AssetAccount
from app.models.fx_extra_need import FxExtraNeed
from app.models.portfolio import Portfolio
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanLeg
from app.models.user import UserSettings
from app.services.accounts._account_queries import active_accounts_stmt
from app.services.dca_cash_shortfall_service import DCA_AUTO_BUY_PRESET, buy_market, fixed_amount_needs
from app.utils.cache_keys import (
    TTL_USD_KRW_HISTORY,
    CacheStoreType,
    get_cached_json,
    set_cached_json,
    usd_krw_history_key,
)
from app.utils.currency import get_live_or_cached_usd_krw
from app.utils.inproc_lock import inproc_lock
from app.utils.kst import kst_day_start, today_kst

logger = structlog.get_logger()

_FX_SYMBOL = "USDKRW=X"
_MIN_OBSERVATIONS = 60
_TRADING_DAYS_PER_MONTH = 21
_TARGET_RATE_STEP = 10
_NOW_SHARE_BY_ZONE: dict[str, float] = {"CHEAP": 0.5, "NEUTRAL": 0.34, "EXPENSIVE": 0.2}
_TARGET_SIGMA_MULTIPLIERS = (0.5, 1.0)

FxZone = Literal["CHEAP", "NEUTRAL", "EXPENSIVE"]


@dataclass(frozen=True)
class FxPosition:
    rate: float
    low_1y: float
    high_1y: float
    percentile_1y: float
    ma20: float
    ma60: float
    deviation_ma20_pct: float
    deviation_ma60_pct: float
    sigma_1m: float
    range_1m_low: float
    range_1m_high: float
    zone: FxZone


@dataclass(frozen=True)
class FxTranche:
    label: str
    target_rate: float | None
    usd: float
    krw_estimate: float


def _zone(percentile: float) -> FxZone:
    if percentile < 33:
        return "CHEAP"
    if percentile > 67:
        return "EXPENSIVE"
    return "NEUTRAL"


def compute_fx_position(closes: list[float], live_rate: float) -> FxPosition | None:
    """1년 종가와 현재 환율로 위치(백분위)·이동평균 이격도·1개월 ±1σ 범위를 계산한다. 관측치 부족이면 None."""
    closes = [c for c in closes if c > 0 and math.isfinite(c)]
    if len(closes) < _MIN_OBSERVATIONS or live_rate <= 0:
        return None

    percentile = sum(1 for c in closes if c < live_rate) / len(closes) * 100
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    log_returns = [math.log(b / a) for a, b in zip(closes, closes[1:], strict=False)]
    mean = sum(log_returns) / len(log_returns)
    daily_sd = math.sqrt(sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1))
    sigma_1m = daily_sd * math.sqrt(_TRADING_DAYS_PER_MONTH) * live_rate

    return FxPosition(
        rate=round(live_rate, 2),
        low_1y=round(min(closes), 2),
        high_1y=round(max(closes), 2),
        percentile_1y=round(percentile, 1),
        ma20=round(ma20, 2),
        ma60=round(ma60, 2),
        deviation_ma20_pct=round((live_rate - ma20) / ma20 * 100, 2),
        deviation_ma60_pct=round((live_rate - ma60) / ma60 * 100, 2),
        sigma_1m=round(sigma_1m, 2),
        range_1m_low=round(live_rate - sigma_1m, 2),
        range_1m_high=round(live_rate + sigma_1m, 2),
        zone=_zone(percentile),
    )


def compute_fx_plan(
    position: FxPosition | None, need_usd: float, live_rate: float, urgent_usd: float = 0.0
) -> list[FxTranche]:
    """필요 달러를 "지금" + 목표 환율 2구간으로 나눈다. 위치를 모르면 전액을 적립일 환전 1구간으로 둔다.

    `urgent_usd`: 지금 바로 환전해야 하는 금액(환전 대기 중인 적립 매수의 부족분, plans/121 B) —
    "지금" 구간을 최소 이만큼으로 늘린다(필요 달러를 넘지 않게).
    """
    if need_usd <= 0:
        return []
    urgent = min(max(urgent_usd, 0.0), need_usd)
    if position is None:
        if urgent <= 0:
            return [FxTranche("적립일에 환전", None, round(need_usd, 2), round(need_usd * live_rate))]
        tranches = [FxTranche("지금", None, round(urgent, 2), round(urgent * live_rate))]
        rest = need_usd - urgent
        if rest > 0.005:
            tranches.append(FxTranche("적립일에 환전", None, round(rest, 2), round(rest * live_rate)))
        return tranches

    now_usd = max(need_usd * _NOW_SHARE_BY_ZONE[position.zone], urgent)
    rest_each = (need_usd - now_usd) / len(_TARGET_SIGMA_MULTIPLIERS)
    tranches = [FxTranche("지금", None, round(now_usd, 2), round(now_usd * live_rate))]
    if rest_each <= 0.005:
        return tranches
    # σ가 작으면 0.5σ·1σ 목표가 10원 내림 후 같아진다 — 같은 목표는 한 구간으로 합친다(plans/97 B1).
    # 목표는 현재 환율보다 최소 한 단계 아래(이미 닿은 값으로 알림을 걸지 않게).
    ceiling = math.ceil(live_rate / _TARGET_RATE_STEP) * _TARGET_RATE_STEP - _TARGET_RATE_STEP
    usd_by_target: dict[int, float] = {}
    for mult in _TARGET_SIGMA_MULTIPLIERS:
        target = math.floor((live_rate - position.sigma_1m * mult) / _TARGET_RATE_STEP) * _TARGET_RATE_STEP
        target = min(target, ceiling)
        usd_by_target[target] = usd_by_target.get(target, 0.0) + rest_each

    for target, usd in usd_by_target.items():
        tranches.append(FxTranche(f"{target:,.0f}원 이하", float(target), round(usd, 2), round(usd * target)))
    return tranches


def _sync_usd_krw_closes() -> list[float]:
    from app.services.market_data.market_data_fetcher import fetch_yf_close_series

    end = today_kst()
    series = fetch_yf_close_series([_FX_SYMBOL], end - timedelta(days=365), end).get(_FX_SYMBOL)
    if series is None:
        return []
    return [float(v) for v in series.tolist()]


async def fetch_usd_krw_closes(cache: CacheStoreType) -> list[float] | None:
    """USD/KRW 1년 일봉 종가(6h 캐시). 관측치가 부족하면 캐시하지 않고 None."""
    key = usd_krw_history_key()
    cached = await get_cached_json(cache, key)
    if isinstance(cached, list) and cached:
        return [float(v) for v in cached]

    from app.services.market_data.yahoo_price import run_yf_bounded

    try:
        closes = await run_yf_bounded(_sync_usd_krw_closes)
    except Exception as e:
        logger.warning("usd_krw_history_fetch_failed", error=str(e))
        return None
    if len(closes) < _MIN_OBSERVATIONS:
        logger.warning("usd_krw_history_insufficient", observations=len(closes))
        return None
    await set_cached_json(cache, key, closes, TTL_USD_KRW_HISTORY)
    return closes


def overseas_weight_pct(portfolio: Portfolio) -> float:
    """포트폴리오 목표 비중 중 실제로 해외 종목을 사는 비중(%). ISA·연금의 국내 대체 매수는 해외에서 뺀다."""
    total = 0.0
    for item in portfolio.items:
        market = (buy_market(item, portfolio.tax_type) or "").upper()
        if market not in DOMESTIC_MARKETS and market != CASH_EQUIVALENT_MARKET:
            total += float(item.weight or 0)
    return total


async def _pick_portfolio(
    db: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID | None
) -> tuple[Portfolio | None, list[Portfolio]]:
    """(선택된 포트폴리오, 해외 비중이 있는 후보 목록). 순서: 지정 → 적립 자동매수 → 해외 비중 있는 첫 포트폴리오."""
    portfolios = (
        (
            await db.execute(
                select(Portfolio)
                .where(Portfolio.user_id == user_id)
                .options(selectinload(Portfolio.items), selectinload(Portfolio.linked_accounts))
                .order_by(Portfolio.sort_order, Portfolio.created_at)
            )
        )
        .scalars()
        .all()
    )
    candidates = [p for p in portfolios if overseas_weight_pct(p) > 0]

    if portfolio_id is not None:
        return next((p for p in portfolios if p.id == portfolio_id), None), candidates

    dca_portfolio_id = await db.scalar(
        select(RebalancingAlert.portfolio_id)
        .where(
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.is_active == True,
            *(getattr(RebalancingAlert, field) == value for field, value in DCA_AUTO_BUY_PRESET.items()),
        )
        .limit(1)
    )
    picked = next((p for p in candidates if p.id == dca_portfolio_id), None)
    return picked or (candidates[0] if candidates else None), candidates


async def _fixed_dca_alerts(
    db: AsyncSession, user_id: uuid.UUID, portfolio: Portfolio
) -> list[tuple[RebalancingAlert, AssetAccount]]:
    """이 포트폴리오의 활성 정액 적립 자동매수 알림(plans/120 `dca_amount_krw`)과 실행 계좌."""
    rows = (
        await db.execute(
            select(RebalancingAlert, AssetAccount)
            .join(AssetAccount, AssetAccount.id == RebalancingAlert.account_id)
            .where(
                RebalancingAlert.user_id == user_id,
                RebalancingAlert.portfolio_id == portfolio.id,
                RebalancingAlert.is_active == True,
                RebalancingAlert.dca_amount_krw.is_not(None),
                *(getattr(RebalancingAlert, field) == value for field, value in DCA_AUTO_BUY_PRESET.items()),
                AssetAccount.is_active == True,
            )
        )
    ).all()
    return [(alert, account) for alert, account in rows if float(alert.dca_amount_krw or 0) > 0]


HeldUsdSource = Literal["SYNCED", "MANUAL"]


@dataclass(frozen=True)
class HeldUsdAccount:
    account: AssetAccount
    usd: float
    source: HeldUsdSource
    synced_at: datetime | None = None  # 브로커 계좌의 마지막 동기화 시각(수기는 None)
    reserved_usd: float = 0.0  # 추가 환전 항목이 이 계좌에 둔 달러 — `usd`는 이미 이만큼 뺀 값이다


async def _held_usd(db: AsyncSession, user_id: uuid.UUID) -> list[HeldUsdAccount]:
    """활성 증권 계좌 전체(수기 포함)의 계좌별 달러 예수금 — 계좌관리에 저장된 `deposit_usd` 그대로.

    증권사 실시간 조회는 하지 않는다(plans/127) — 카드를 열 때마다 토큰 + 해외잔고(최대 3거래소)를 기다렸다.
    환전 직후 반영은 카드의 "달러 예수금 새로 받기"(계좌 동기화)로 한다. 실제 재매수 판정(WAITING_FX)은
    `usd_buying_power`가 실행 직전에 따로 실시간으로 확인한다.
    """
    stmt = active_accounts_stmt(user_id).where(AssetAccount.asset_type.in_(POSITION_STOCK_ASSET_TYPES))
    accounts = (await db.execute(stmt)).scalars().all()
    reserved = await reserved_usd_by_account(db, user_id)
    held = [
        HeldUsdAccount(account, float(account.deposit_usd or 0), "SYNCED", account.last_synced_at)
        if account.asset_type in BROKER_API_ASSET_TYPES
        else HeldUsdAccount(account, float(account.deposit_usd or 0), "MANUAL")
        for account in accounts
    ]
    return [_minus_reserved(h, reserved.get(h.account.id, 0.0)) for h in held]


async def reserved_usd_by_account(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, float]:
    """추가 환전 항목(plans/123)이 증권 계좌에 둔 달러 — 계좌별 `exchanged_usd` 합.

    필요일이 지난 항목은 여행에 쓴 것으로 보고 세지 않는다(남은 달러는 다시 적립용으로 센다).
    """
    rows = (
        await db.execute(
            select(FxExtraNeed.reserved_account_id, func.sum(FxExtraNeed.exchanged_usd))
            .where(
                FxExtraNeed.user_id == user_id,
                FxExtraNeed.reserved_account_id.is_not(None),
                FxExtraNeed.due_date >= today_kst(),
            )
            .group_by(FxExtraNeed.reserved_account_id)
        )
    ).all()
    return {account_id: float(total or 0) for account_id, total in rows if account_id is not None}


def _minus_reserved(held: HeldUsdAccount, reserved: float) -> HeldUsdAccount:
    """여행 등으로 둔 달러를 적립용 보유 달러에서 뺀다(계좌별 0 하한)."""
    if reserved <= 0:
        return held
    return replace(held, usd=max(0.0, held.usd - reserved), reserved_usd=round(reserved, 2))


def _held_synced_at(held: list[HeldUsdAccount]) -> datetime | None:
    """달러가 있는 브로커 계좌 중 가장 오래된 동기화 시각 — 보유 달러가 언제 기준인지."""
    times = [h.synced_at for h in held if h.source == "SYNCED" and h.usd + h.reserved_usd > 0 and h.synced_at]
    return min(times) if times else None


async def _waiting_fx_required_usd(
    db: AsyncSession, user_id: uuid.UUID, portfolio: Portfolio
) -> list[tuple[uuid.UUID | None, float]]:
    """이 포트폴리오에서 환전을 기다리는(WAITING_FX, plans/120) 적립 해외 매수 leg들의 실행 계좌별 필요 달러.

    키움 원화주문 계좌의 leg는 뺀다 — 그 계좌는 달러 부족분을 원화로 결제하므로 아직 대기 중이면 원화까지 모자란
    것이고, 풀 방법은 달러 환전이 아니라 원화 입금이다(plans/129 A2).
    """
    rows = (
        await db.execute(
            select(
                RebalancingPlan.account_id,
                AssetAccount.asset_type,
                AssetAccount.krw_overseas_order,
                func.coalesce(func.sum(RebalancingPlanLeg.required_usd), 0),
            )
            .join(RebalancingPlan, RebalancingPlan.id == RebalancingPlanLeg.plan_id)
            .outerjoin(AssetAccount, AssetAccount.id == RebalancingPlan.account_id)
            .where(
                RebalancingPlan.user_id == user_id,
                RebalancingPlan.portfolio_id == portfolio.id,
                RebalancingPlanLeg.status == "WAITING_FX",
            )
            .group_by(RebalancingPlan.account_id, AssetAccount.asset_type, AssetAccount.krw_overseas_order)
        )
    ).all()
    return [
        (account_id, float(usd or 0))
        for account_id, asset_type, krw_order, usd in rows
        if not uses_krw_overseas_order(SimpleNamespace(asset_type=asset_type, krw_overseas_order=krw_order))
    ]


def _waiting_fx_shortfall(waiting: list[tuple[uuid.UUID | None, float]], held: list[HeldUsdAccount]) -> float:
    """환전 대기 매수를 진행하려면 지금 더 필요한 달러 — leg의 **실행 계좌** 달러로만 상쇄한다.

    재매수 판정(`usd_buying_power`)은 그 계좌의 달러만 본다. 다른 계좌(다른 증권사·수기 계좌)에 달러가 있어도
    그 leg는 진행되지 않으므로, 합쳐서 상쇄하면 "지금" 구간이 사라진 채 leg가 만료된다(plans/128 C2).
    계좌를 모르는 옛 플랜(account_id 없음)만 주문 실행 계좌 달러 합으로 상쇄한다.
    """
    executable = {h.account.id: h.usd for h in held if h.account.asset_type in ORDER_EXECUTABLE_ASSET_TYPES}
    total_executable = sum(executable.values())
    return sum(
        max(0.0, need - (executable.get(account_id, 0.0) if account_id is not None else total_executable))
        for account_id, need in waiting
    )


@dataclass(frozen=True)
class FxRateContext:
    rate: float
    rate_is_live: bool
    position: FxPosition | None
    # 실시간·캐시 환율도 1년 종가도 없으면 rate는 설정 fallback(1300)이다 — 그 값으로 달러를 원화로 계산하면
    # 실제 수치처럼 보인다(plans/99 A6)
    has_rate: bool


async def load_fx_rate_context(cache: CacheStoreType) -> FxRateContext:
    """현재 환율(실시간·캐시, 없으면 1년 일봉 마지막 종가)과 1년 위치. 적립 계획·추가 환전(plans/123)이 함께 쓴다."""
    # 둘은 독립이다 — 캐시 미스면 각각 Yahoo를 기다리므로 함께 기다린다(plans/124 C)
    (live_rate, rate_is_live), closes = await asyncio.gather(
        get_live_or_cached_usd_krw(cache), fetch_usd_krw_closes(cache)
    )
    if not rate_is_live and closes:
        live_rate = closes[-1]
    position = compute_fx_position(closes, live_rate) if closes else None
    return FxRateContext(live_rate, rate_is_live, position, has_rate=rate_is_live or bool(closes))


async def get_fx_plan(
    db: AsyncSession,
    cache: CacheStoreType,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    months: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    # 환율(캐시 미스면 Yahoo)은 DB 읽기와 독립이다 — 먼저 출발시켜 두고 필요한 시점에 기다린다(plans/127)
    rate_task = asyncio.create_task(load_fx_rate_context(cache))
    try:
        result = await _build_fx_plan(db, user_id, portfolio_id, months, rate_task)
        # 조기 반환한 상태(NO_PORTFOLIO 등)도 환율 위치는 보여 준다
        await release_read_connection(db)
        ctx = await rate_task
    finally:
        if not rate_task.done():
            rate_task.cancel()
    result.update(position=asdict(ctx.position) if ctx.position else None, rate_is_live=ctx.rate_is_live)
    logger.info(
        "fx_plan_timing",
        status=result["status"],
        accounts=result.pop("_accounts", 0),
        ms=_elapsed_ms(started),
    )
    return result


async def _build_fx_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    months: int,
    rate_task: asyncio.Task[FxRateContext],
) -> dict[str, Any]:
    """계획 본문. `position`·`rate_is_live`는 호출부가 채운다. 환율은 DB 읽기를 모두 마친 뒤에 기다린다."""
    portfolio, candidates = await _pick_portfolio(db, user_id, portfolio_id)
    if portfolio_id is not None and portfolio is None:
        raise NotFoundError(detail="포트폴리오를 찾을 수 없습니다")

    result: dict[str, Any] = {
        "position": None,
        "rate_is_live": True,
        "status": "OK",
        "portfolio_id": portfolio.id if portfolio else None,
        "portfolio_name": portfolio.name if portfolio else None,
        "portfolio_options": [{"id": p.id, "name": p.name} for p in candidates],
        "months": months,
        "overseas_weight_pct": 0.0,
        "monthly_deposit_krw": None,
        "monthly_need_usd": 0.0,
        "held_usd": 0.0,
        "need_usd": 0.0,
        "tranches": [],
        # plans/121 B — 필요 달러 기준(정액 적립 / 월 적립액), 환전 대기 매수 부족분
        "deposit_source": None,
        "held_usd_synced_at": None,  # 보유 달러 기준 시각(plans/127 — 계좌 동기화 값)
        "held_usd_accounts": [],
        "waiting_fx_usd": 0.0,
        "krw_order_accounts": [],  # 원화주문 계좌라 필요 달러에서 뺀 정액 적립 실행 계좌 이름
        "reserved_usd": 0.0,  # 추가 환전 항목이 증권 계좌에 둔 달러 — 보유 달러에서 뺐다(plans/123 후속)
    }
    if portfolio is None:
        result["status"] = "NO_PORTFOLIO"
        return result

    overseas_pct = overseas_weight_pct(portfolio)
    result["overseas_weight_pct"] = round(overseas_pct, 2)
    if overseas_pct <= 0:
        result["status"] = "NO_OVERSEAS"
        return result

    # 정액 적립 알림이 있으면 실제 매수 금액의 해외 몫이 기준이다 — 사용자 월 적립액은 계좌·포트폴리오 구분이 없다
    fixed = await _fixed_dca_alerts(db, user_id, portfolio)
    monthly_deposit: float | None = None
    if fixed:
        monthly_deposit = sum(float(alert.dca_amount_krw or 0) for alert, _ in fixed)
    else:
        raw = await db.scalar(select(UserSettings.monthly_deposit_amount).where(UserSettings.user_id == user_id))
        monthly_deposit = float(raw) if raw else None
    if not monthly_deposit or monthly_deposit <= 0:
        result["status"] = "NO_DEPOSIT_GOAL"
        return result

    held = await _held_usd(db, user_id)
    waiting_required = await _waiting_fx_required_usd(db, user_id, portfolio)
    # DB 읽기는 여기까지 — 환율을 기다리는 동안 커넥션을 쥐지 않는다
    await release_read_connection(db)
    ctx = await rate_task
    if not ctx.has_rate:
        result["status"] = "NO_RATE"
        return result
    live_rate = ctx.rate

    if fixed:
        # 키움 원화주문 계좌는 증권사가 원화로 결제(자동 환전)하므로 미리 바꿀 달러가 아니다
        krw_order_names = sorted({account.name for _, account in fixed if uses_krw_overseas_order(account)})
        result["krw_order_accounts"] = krw_order_names
        # ISA·연금 계좌는 해외 종목 대신 다른 종목을 사므로(`dca_allocation`) 계좌별로 해외 몫을 나눈다
        monthly_need_usd = sum(
            fixed_amount_needs(float(alert.dca_amount_krw or 0), account, portfolio, live_rate)[1]
            for alert, account in fixed
            if not uses_krw_overseas_order(account)
        )
        if monthly_need_usd <= 0:
            result.update(
                status="KRW_ORDER" if krw_order_names else "NO_OVERSEAS",
                deposit_source="DCA_AMOUNT",
                monthly_deposit_krw=monthly_deposit,
            )
            return result
    else:
        monthly_need_usd = monthly_deposit * overseas_pct / 100 / live_rate

    # 추가 환전 항목이 둔 달러는 이미 뺀 값이다(`_held_usd`) — WAITING_FX 상쇄도 여행 달러를 쓰지 않는다
    held_usd = sum(h.usd for h in held)
    # 대기 중인 매수는 그 실행 계좌의 달러로 먼저 채운다 — 남는 부족분만 "지금" 환전해야 매수가 다시 진행된다
    waiting_fx_usd = _waiting_fx_shortfall(waiting_required, held)
    need_usd = max(0.0, monthly_need_usd * months - held_usd, waiting_fx_usd)
    result.update(
        deposit_source="DCA_AMOUNT" if fixed else "MONTHLY_GOAL",
        monthly_deposit_krw=monthly_deposit,
        monthly_need_usd=round(monthly_need_usd, 2),
        held_usd=round(held_usd, 2),
        held_usd_synced_at=_held_synced_at(held),
        held_usd_accounts=[
            {
                "account_id": h.account.id,
                "name": h.account.name,
                "usd": round(h.usd, 2),
                "source": h.source,
                "synced_at": h.synced_at,
                "reserved_usd": h.reserved_usd,
            }
            for h in sorted(held, key=lambda h: h.usd, reverse=True)
            # 다 빼서 0이 된 계좌도 보여 준다 — 왜 보유 달러가 0인지 알 수 있게
            if h.usd > 0 or h.reserved_usd > 0
        ],
        reserved_usd=round(sum(h.reserved_usd for h in held), 2),
        waiting_fx_usd=round(waiting_fx_usd, 2),
        need_usd=round(need_usd, 2),
        tranches=[asdict(t) for t in compute_fx_plan(ctx.position, need_usd, live_rate, waiting_fx_usd)],
        status="OK" if need_usd > 0 else "SUFFICIENT",
        _accounts=len(held),
    )
    return result


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


_SYNC_LOCK_TTL_SECONDS = 30


@dataclass(frozen=True)
class FxPlanAlertSyncResult:
    created: int
    updated: int
    removed: int
    skipped_manual: int
    skipped_shared: int = 0


def _rate_key(rate: float) -> int:
    """Numeric(10,2) 목표 환율을 비교 키로(센트 단위 정수) — float 오차로 같은 목표가 달라 보이지 않게."""
    return round(float(rate) * 100)


async def _check_scope_owned(
    db: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    fx_need_id: uuid.UUID | None,
    has_targets: bool,
) -> None:
    if (portfolio_id is None) == (fx_need_id is None):
        raise ValueError("portfolio_id와 fx_need_id 중 하나만 지정한다")
    if portfolio_id is not None:
        owned = await db.scalar(select(Portfolio.id).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id))
        if owned is None:
            raise NotFoundError(detail="포트폴리오를 찾을 수 없습니다")
        return
    due = await db.scalar(
        select(FxExtraNeed.due_date).where(FxExtraNeed.id == fx_need_id, FxExtraNeed.user_id == user_id)
    )
    if due is None:
        raise NotFoundError(detail="추가 환전 항목을 찾을 수 없습니다")
    # 지난 항목의 알림은 발송하지 않는다 — 새로 만들지도 않는다(해제는 허용)
    if has_targets and due < today_kst():
        raise BadRequestError(detail="필요일이 지난 항목에는 알림을 등록할 수 없습니다")


def _in_scope(alert: ExchangeRateAlert, portfolio_id: uuid.UUID | None, fx_need_id: uuid.UUID | None) -> bool:
    """계획 알림이 이번 맞추기 범위인지 — 추가 환전 항목 알림은 portfolio_id가 없다."""
    if fx_need_id is not None:
        return alert.fx_need_id == fx_need_id
    return alert.portfolio_id == portfolio_id and alert.fx_need_id is None


def _is_shareable_portfolio_alert(alert: ExchangeRateAlert) -> bool:
    """다른 포트폴리오 적립 계획의 활성·미발동 알림인지 — 같은 목표면 새로 만들지 않고 함께 쓴다.

    추가 환전 항목 알림은 항목 이름이 실려 따로 둔다. 프론트 `utils/fxPlanAlerts.sharedWith`와 같은 규칙.
    """
    return alert.fx_need_id is None and alert.is_active and alert.direction == "BELOW" and alert.triggered_at is None


def _classify_alerts(
    alerts: Sequence[ExchangeRateAlert], portfolio_id: uuid.UUID | None, fx_need_id: uuid.UUID | None
) -> tuple[dict[int, ExchangeRateAlert], list[ExchangeRateAlert], set[int], set[int]]:
    """맞추기 대상 알림을 나눈다 — (이 범위 미발동 계획 알림[목표 키별 하나], 지울 이 범위 계획 알림,
    직접 등록한 활성 BELOW 목표, 다른 포트폴리오 계획의 활성·미발동 목표[포트폴리오 범위에서만])."""
    triggered_cutoff = kst_day_start(today_kst() - timedelta(days=FX_PLAN_ACTION_DAYS - 1))
    plan_alerts: dict[int, ExchangeRateAlert] = {}
    stale: list[ExchangeRateAlert] = []
    manual_keys: set[int] = set()
    shared_keys: set[int] = set()
    for alert in alerts:
        key = _rate_key(alert.target_rate)
        if alert.source != FX_PLAN_ALERT_SOURCE:
            manual_keys.add(key)
        elif not _in_scope(alert, portfolio_id, fx_need_id):
            # 다른 포트폴리오·추가 환전 항목의 계획 알림은 그 계획이 관리한다
            if fx_need_id is None and _is_shareable_portfolio_alert(alert):
                shared_keys.add(key)
        elif alert.triggered_at is not None:
            fired = alert.triggered_at
            if (fired if fired.tzinfo else fired.replace(tzinfo=UTC)) < triggered_cutoff:
                stale.append(alert)
        # 같은 목표가 둘이면(동시 등록 경합의 흔적) 하나만 남긴다
        elif key in plan_alerts:
            stale.append(alert)
        else:
            plan_alerts[key] = alert
    return plan_alerts, stale, manual_keys, shared_keys


async def sync_fx_plan_alerts(
    db: AsyncSession,
    cache: CacheStore,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    targets: list[tuple[float, float]],
    *,
    fx_need_id: uuid.UUID | None = None,
) -> FxPlanAlertSyncResult:
    """한 계획 범위의 알림(FX_PLAN, 활성·미발동)을 `targets`[(목표 환율, 달러)]에 맞춘다(plans/121).

    범위는 포트폴리오 적립 계획(`portfolio_id`) 또는 추가 환전 항목(`fx_need_id`, plans/123) 중 하나다 —
    한 범위의 맞추기는 다른 범위의 계획 알림을 건드리지 않는다.

    - 같은 목표가 이미 있으면 금액만 갱신, 새 목표면 BELOW 1회 알림 생성, 목표에서 빠진 계획 알림은 삭제.
    - 같은 목표의 **직접 등록한(MANUAL) 활성 BELOW 알림**이 있으면 만들지 않는다(중복 발송 방지).
      MANUAL 알림은 계획이 지우거나 바꾸지 않는다.
    - 포트폴리오 적립 계획끼리는 목표 환율이 같으면 알림을 하나만 둔다 — 다른 포트폴리오 계획의 활성·미발동
      알림이 그 목표에 있으면 만들지 않고, 이 계획에 이미 있던 같은 목표 알림은 지운다(먼저 맞춘 쪽이 남는다).
      같은 환율에 메일·푸시가 두 번 오지 않게 한다. 추가 환전 항목(`fx_need_id`) 알림은 항목 이름이 실려 따로 둔다.
    - 일시정지한 미발동 계획 알림도 계획 알림이다 — 목표에 있으면 다시 켜고, 없으면 지운다(중복 생성 방지).
    - 발동된 계획 알림은 "지금 할 일"이 보이는 동안(`FX_PLAN_ACTION_DAYS`) 두고, 그보다 오래된 것은 지운다 —
      쌓이면 사용자당 알림 상한(50)에 걸려 맞추기·직접 등록이 모두 409가 된다(plans/122 B5).
      발동 기록은 알림 이력에 남는다.
    """
    await _check_scope_owned(db, user_id, portfolio_id, fx_need_id, bool(targets))
    scope_filter = (
        ExchangeRateAlert.fx_need_id == fx_need_id
        if fx_need_id is not None
        else and_(ExchangeRateAlert.portfolio_id == portfolio_id, ExchangeRateAlert.fx_need_id.is_(None))
    )

    async with inproc_lock(cache, f"lock:fx_plan_alerts:{user_id}", ttl=_SYNC_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            raise ConflictError(detail="환전 계획 알림을 등록하는 중입니다. 잠시 후 다시 시도해 주세요")

        alerts = (
            (
                await db.execute(
                    select(ExchangeRateAlert).where(
                        ExchangeRateAlert.user_id == user_id,
                        or_(
                            and_(ExchangeRateAlert.is_active == True, ExchangeRateAlert.direction == "BELOW"),
                            and_(ExchangeRateAlert.source == FX_PLAN_ALERT_SOURCE, scope_filter),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        plan_alerts, stale, manual_keys, shared_keys = _classify_alerts(alerts, portfolio_id, fx_need_id)

        wanted = {_rate_key(rate): (rate, usd) for rate, usd in targets}
        # 다른 포트폴리오 계획과 겹친 목표의 이 계획 알림도 지운다 — 같은 환율 알림을 하나로
        stale.extend(alert for key, alert in plan_alerts.items() if key not in wanted or key in shared_keys)

        to_create: list[tuple[float, float]] = []
        updated = skipped = shared = 0
        for key, (rate, usd) in wanted.items():
            if key in shared_keys:
                shared += 1
            elif key in plan_alerts:
                plan_alerts[key].planned_usd = round(usd, 2)
                plan_alerts[key].is_active = True
                updated += 1
            elif key in manual_keys:
                skipped += 1
            else:
                to_create.append((rate, usd))

        total = await db.scalar(
            select(func.count()).select_from(ExchangeRateAlert).where(ExchangeRateAlert.user_id == user_id)
        )
        if (total or 0) - len(stale) + len(to_create) > MAX_EXCHANGE_RATE_ALERTS_PER_USER:
            await db.rollback()
            raise ConflictError(
                detail=(
                    f"환율 알림은 {MAX_EXCHANGE_RATE_ALERTS_PER_USER}개까지 만들 수 있습니다. 안 쓰는 알림은 지워주세요"
                )
            )

        for alert in stale:
            await db.delete(alert)
        for rate, usd in to_create:
            db.add(
                ExchangeRateAlert(
                    user_id=user_id,
                    target_rate=rate,
                    direction="BELOW",
                    max_trigger_count=1,
                    source=FX_PLAN_ALERT_SOURCE,
                    planned_usd=round(usd, 2),
                    portfolio_id=portfolio_id,
                    fx_need_id=fx_need_id,
                )
            )
        await db.commit()

    logger.info(
        "fx_plan_alerts_synced",
        user_id=str(user_id),
        scope="fx_need" if fx_need_id is not None else "portfolio",
        created=len(to_create),
        updated=updated,
        removed=len(stale),
        skipped_manual=skipped,
        skipped_shared=shared,
    )
    return FxPlanAlertSyncResult(len(to_create), updated, len(stale), skipped, shared)
