"""달러 환전 계획 — 환율의 1년 통계적 위치와 해외 적립에 필요한 달러로 분할 환전 구간을 제안한다(plans/96).

- 위치·범위는 예측이 아니라 과거 1년 종가 분포와 변동성으로 계산한 참고치다.
- 현재값은 앱 전역 실시간 캐시(`get_live_or_cached_usd_krw`)를 쓰고, Yahoo 1년 일봉은 통계 계산에만 쓴다.
  실값이 없으면(콜드스타트+Yahoo 장애) 설정 fallback 대신 1년 일봉 마지막 종가로 대체한다 —
  고정 fallback(1300원)이면 "1년 최저" 판정과 그 아래 목표 환율이 나온다(plans/97 A2).
- 아무것도 저장하지 않는다. 구간 목표 환율의 알림 등록은 프론트가 기존 `POST /alerts/exchange-rate`로 한다.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import CASH_EQUIVALENT_MARKET, DOMESTIC_MARKETS
from app.exceptions import NotFoundError
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import UserSettings
from app.services.accounts._account_queries import active_broker_accounts_stmt
from app.services.dca_cash_shortfall_service import DCA_AUTO_BUY_PRESET, buy_market
from app.utils.cache_keys import (
    TTL_USD_KRW_HISTORY,
    CacheStoreType,
    get_cached_json,
    set_cached_json,
    usd_krw_history_key,
)
from app.utils.currency import get_live_or_cached_usd_krw
from app.utils.kst import today_kst

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


def compute_fx_plan(position: FxPosition | None, need_usd: float, live_rate: float) -> list[FxTranche]:
    """필요 달러를 "지금" + 목표 환율 2구간으로 나눈다. 위치를 모르면 전액을 적립일 환전 1구간으로 둔다."""
    if need_usd <= 0:
        return []
    if position is None:
        return [FxTranche("적립일에 환전", None, round(need_usd, 2), round(need_usd * live_rate))]

    now_usd = need_usd * _NOW_SHARE_BY_ZONE[position.zone]
    rest_each = (need_usd - now_usd) / len(_TARGET_SIGMA_MULTIPLIERS)
    # σ가 작으면 0.5σ·1σ 목표가 10원 내림 후 같아진다 — 같은 목표는 한 구간으로 합친다(plans/97 B1).
    # 목표는 현재 환율보다 최소 한 단계 아래(이미 닿은 값으로 알림을 걸지 않게).
    ceiling = math.ceil(live_rate / _TARGET_RATE_STEP) * _TARGET_RATE_STEP - _TARGET_RATE_STEP
    usd_by_target: dict[int, float] = {}
    for mult in _TARGET_SIGMA_MULTIPLIERS:
        target = math.floor((live_rate - position.sigma_1m * mult) / _TARGET_RATE_STEP) * _TARGET_RATE_STEP
        target = min(target, ceiling)
        usd_by_target[target] = usd_by_target.get(target, 0.0) + rest_each

    tranches = [FxTranche("지금", None, round(now_usd, 2), round(now_usd * live_rate))]
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


async def _held_usd(db: AsyncSession, user_id: uuid.UUID, portfolio: Portfolio) -> float:
    """포트폴리오 연결 계좌(없으면 활성 브로커 계좌 전체)의 달러 예수금 합."""
    linked_ids = [pa.account_id for pa in portfolio.linked_accounts]
    stmt = active_broker_accounts_stmt(user_id)
    if linked_ids:
        stmt = stmt.where(AssetAccount.id.in_(linked_ids))
    accounts = (await db.execute(stmt)).scalars().all()
    return sum(float(a.deposit_usd or 0) for a in accounts)


async def get_fx_plan(
    db: AsyncSession,
    cache: CacheStoreType,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    months: int,
) -> dict[str, Any]:
    live_rate, rate_is_live = await get_live_or_cached_usd_krw(cache)
    closes = await fetch_usd_krw_closes(cache)
    if not rate_is_live and closes:
        live_rate = closes[-1]
    position = compute_fx_position(closes, live_rate) if closes else None

    portfolio, candidates = await _pick_portfolio(db, user_id, portfolio_id)
    if portfolio_id is not None and portfolio is None:
        raise NotFoundError(detail="포트폴리오를 찾을 수 없습니다")

    result: dict[str, Any] = {
        "position": asdict(position) if position else None,
        "rate_is_live": rate_is_live,
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
    }
    if portfolio is None:
        result["status"] = "NO_PORTFOLIO"
        return result

    overseas_pct = overseas_weight_pct(portfolio)
    result["overseas_weight_pct"] = round(overseas_pct, 2)
    if overseas_pct <= 0:
        result["status"] = "NO_OVERSEAS"
        return result

    monthly_deposit = await db.scalar(
        select(UserSettings.monthly_deposit_amount).where(UserSettings.user_id == user_id)
    )
    if not monthly_deposit or float(monthly_deposit) <= 0:
        result["status"] = "NO_DEPOSIT_GOAL"
        return result

    # 실시간·캐시 환율도 1년 종가도 없으면 live_rate는 설정 fallback(1300)이다 — 그 값으로 달러를 계산하면
    # 실제 수치처럼 보인다 (plans/99 A6)
    if not rate_is_live and not closes:
        result["status"] = "NO_RATE"
        return result

    monthly_need_usd = float(monthly_deposit) * overseas_pct / 100 / live_rate
    held_usd = await _held_usd(db, user_id, portfolio)
    need_usd = max(0.0, monthly_need_usd * months - held_usd)
    result.update(
        monthly_deposit_krw=float(monthly_deposit),
        monthly_need_usd=round(monthly_need_usd, 2),
        held_usd=round(held_usd, 2),
        need_usd=round(need_usd, 2),
        tranches=[asdict(t) for t in compute_fx_plan(position, need_usd, live_rate)],
        status="OK" if need_usd > 0 else "SUFFICIENT",
    )
    return result
