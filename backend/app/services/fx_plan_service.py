"""달러 환전 계획 — 환율의 1년 통계적 위치와 해외 적립에 필요한 달러로 분할 환전 구간을 제안한다(plans/96).

- 위치·범위는 예측이 아니라 과거 1년 종가 분포와 변동성으로 계산한 참고치다.
- 현재값은 앱 전역 실시간 캐시(`get_live_or_cached_usd_krw`)를 쓰고, Yahoo 1년 일봉은 통계 계산에만 쓴다.
  실값이 없으면(콜드스타트+Yahoo 장애) 설정 fallback 대신 1년 일봉 마지막 종가로 대체한다 —
  고정 fallback(1300원)이면 "1년 최저" 판정과 그 아래 목표 환율이 나온다(plans/97 A2).
- 계획 자체는 저장하지 않는다. 구간 목표 환율 알림은 `sync_fx_plan_alerts`가 FX_PLAN 출처로 맞춘다(plans/121) —
  발동 메일·푸시에 구간 금액이 실리고, 다시 등록하면 옛 목표 알림이 교체된다.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Literal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import (
    CASH_EQUIVALENT_MARKET,
    DOMESTIC_MARKETS,
    FX_PLAN_ALERT_SOURCE,
    MAX_EXCHANGE_RATE_ALERTS_PER_USER,
    ORDER_EXECUTABLE_ASSET_TYPES,
)
from app.core.cache_store import CacheStore
from app.exceptions import ConflictError, NotFoundError
from app.models.alert import ExchangeRateAlert, RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanLeg
from app.models.user import UserSettings
from app.services.accounts._account_queries import active_broker_accounts_stmt
from app.services.dca_cash_shortfall_service import DCA_AUTO_BUY_PRESET, buy_market, fixed_amount_needs
from app.services.rebalancing.usd_buying_power import fetch_usd_buying_power
from app.utils.cache_keys import (
    TTL_USD_BUYING_POWER,
    TTL_USD_KRW_HISTORY,
    CacheStoreType,
    get_cached_json,
    set_cached_json,
    usd_buying_power_key,
    usd_krw_history_key,
)
from app.utils.currency import get_live_or_cached_usd_krw
from app.utils.inproc_lock import inproc_lock
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


def _can_fetch_live_usd(account: AssetAccount) -> bool:
    """증권사 API로 실시간 달러 예수금을 조회할 수 있는 계좌(KIS·키움, 계좌번호 있음)."""
    if account.asset_type == "STOCK_KIS":
        return bool(account.kis_account_no)
    if account.asset_type == "STOCK_KIWOOM":
        return bool(account.kiwoom_account_no)
    return False


async def _account_usd(
    db: AsyncSession, cache: CacheStoreType, user_id: uuid.UUID, account: AssetAccount
) -> tuple[float, bool]:
    """(달러 예수금, 실시간 여부). KIS·키움은 증권사 실시간 조회(2분 캐시), 실패·그 외 계좌는 동기화 값."""
    synced = float(account.deposit_usd or 0)
    if account.asset_type not in ORDER_EXECUTABLE_ASSET_TYPES or not _can_fetch_live_usd(account):
        return synced, False
    key = usd_buying_power_key(user_id, account.id)
    cached = await get_cached_json(cache, key)
    if isinstance(cached, int | float):
        return float(cached), True
    live = await fetch_usd_buying_power(account.id, user_id, db, cache)
    if live is None:
        return synced, False
    await set_cached_json(cache, key, live, TTL_USD_BUYING_POWER)
    return live, True


async def _held_usd(
    db: AsyncSession,
    cache: CacheStoreType,
    user_id: uuid.UUID,
    portfolio: Portfolio,
    extra_accounts: list[AssetAccount],
) -> tuple[float, bool]:
    """포트폴리오 연결 계좌(없으면 활성 브로커 계좌 전체)와 정액 적립 실행 계좌의 달러 예수금 합, 전부 실시간인지.

    환전 직후 동기화(하루 1~2회) 전이면 보유 달러가 옛 값이라 같은 돈을 또 환전하라고 하게 된다(plans/121 B) —
    주문 가능한 계좌는 증권사에서 실시간으로 읽는다.
    """
    linked_ids = [pa.account_id for pa in portfolio.linked_accounts]
    stmt = active_broker_accounts_stmt(user_id)
    if linked_ids:
        stmt = stmt.where(AssetAccount.id.in_(linked_ids))
    accounts: dict[uuid.UUID, AssetAccount] = {a.id: a for a in (await db.execute(stmt)).scalars().all()}
    for account in extra_accounts:
        accounts.setdefault(account.id, account)

    total = 0.0
    all_live = bool(accounts)
    for account in accounts.values():
        usd, is_live = await _account_usd(db, cache, user_id, account)
        total += usd
        # 달러가 없는 수기·토스 계좌까지 "실시간 아님"으로 표시할 이유는 없다
        if not is_live and usd > 0:
            all_live = False
    return total, all_live


async def _waiting_fx_required_usd(db: AsyncSession, user_id: uuid.UUID, portfolio: Portfolio) -> float:
    """이 포트폴리오에서 환전을 기다리는(WAITING_FX, plans/120) 적립 해외 매수 leg들의 필요 달러 합."""
    total = await db.scalar(
        select(func.coalesce(func.sum(RebalancingPlanLeg.required_usd), 0))
        .join(RebalancingPlan, RebalancingPlan.id == RebalancingPlanLeg.plan_id)
        .where(
            RebalancingPlan.user_id == user_id,
            RebalancingPlan.portfolio_id == portfolio.id,
            RebalancingPlanLeg.status == "WAITING_FX",
        )
    )
    return float(total or 0)


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
        # plans/121 B — 필요 달러 기준(정액 적립 / 월 적립액), 보유 달러 실시간 여부, 환전 대기 매수 부족분
        "deposit_source": None,
        "held_usd_is_live": False,
        "waiting_fx_usd": 0.0,
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

    # 실시간·캐시 환율도 1년 종가도 없으면 live_rate는 설정 fallback(1300)이다 — 그 값으로 달러를 계산하면
    # 실제 수치처럼 보인다 (plans/99 A6)
    if not rate_is_live and not closes:
        result["status"] = "NO_RATE"
        return result

    if fixed:
        # ISA·연금 계좌는 해외 종목 대신 다른 종목을 사므로(`dca_allocation`) 계좌별로 해외 몫을 나눈다
        monthly_need_usd = sum(
            fixed_amount_needs(float(alert.dca_amount_krw or 0), account, portfolio, live_rate)[1]
            for alert, account in fixed
        )
        if monthly_need_usd <= 0:
            result.update(status="NO_OVERSEAS", deposit_source="DCA_AMOUNT", monthly_deposit_krw=monthly_deposit)
            return result
    else:
        monthly_need_usd = monthly_deposit * overseas_pct / 100 / live_rate

    held_usd, held_is_live = await _held_usd(db, cache, user_id, portfolio, [account for _, account in fixed])
    waiting_required = await _waiting_fx_required_usd(db, user_id, portfolio)
    # 대기 중인 매수는 보유 달러로 먼저 채운다 — 남는 부족분만 "지금" 환전해야 매수가 다시 진행된다
    waiting_fx_usd = max(0.0, waiting_required - held_usd)
    need_usd = max(0.0, monthly_need_usd * months - held_usd, waiting_fx_usd)
    result.update(
        deposit_source="DCA_AMOUNT" if fixed else "MONTHLY_GOAL",
        monthly_deposit_krw=monthly_deposit,
        monthly_need_usd=round(monthly_need_usd, 2),
        held_usd=round(held_usd, 2),
        held_usd_is_live=held_is_live,
        waiting_fx_usd=round(waiting_fx_usd, 2),
        need_usd=round(need_usd, 2),
        tranches=[asdict(t) for t in compute_fx_plan(position, need_usd, live_rate, waiting_fx_usd)],
        status="OK" if need_usd > 0 else "SUFFICIENT",
    )
    return result


_SYNC_LOCK_TTL_SECONDS = 30


@dataclass(frozen=True)
class FxPlanAlertSyncResult:
    created: int
    updated: int
    removed: int
    skipped_manual: int


def _rate_key(rate: float) -> int:
    """Numeric(10,2) 목표 환율을 비교 키로(센트 단위 정수) — float 오차로 같은 목표가 달라 보이지 않게."""
    return round(float(rate) * 100)


async def sync_fx_plan_alerts(
    db: AsyncSession,
    cache: CacheStore,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    targets: list[tuple[float, float]],
) -> FxPlanAlertSyncResult:
    """포트폴리오의 계획 알림(FX_PLAN, 활성·미발동)을 `targets`[(목표 환율, 달러)]에 맞춘다(plans/121).

    - 같은 목표가 이미 있으면 금액만 갱신, 새 목표면 BELOW 1회 알림 생성, 목표에서 빠진 계획 알림은 삭제.
    - 같은 목표의 **직접 등록한(MANUAL) 활성 BELOW 알림**이 있으면 만들지 않는다(중복 발송 방지).
      MANUAL 알림은 계획이 지우거나 바꾸지 않는다.
    - 발동된 계획 알림은 이력이라 건드리지 않는다.
    """
    owned = await db.scalar(select(Portfolio.id).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id))
    if owned is None:
        raise NotFoundError(detail="포트폴리오를 찾을 수 없습니다")

    async with inproc_lock(cache, f"lock:fx_plan_alerts:{user_id}", ttl=_SYNC_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            raise ConflictError(detail="환전 계획 알림을 등록하는 중입니다. 잠시 후 다시 시도해 주세요")

        alerts = (
            (
                await db.execute(
                    select(ExchangeRateAlert).where(
                        ExchangeRateAlert.user_id == user_id,
                        ExchangeRateAlert.is_active == True,
                        ExchangeRateAlert.direction == "BELOW",
                    )
                )
            )
            .scalars()
            .all()
        )
        plan_alerts: dict[int, ExchangeRateAlert] = {}
        stale: list[ExchangeRateAlert] = []
        manual_keys: set[int] = set()
        for alert in alerts:
            key = _rate_key(alert.target_rate)
            if alert.source != FX_PLAN_ALERT_SOURCE:
                manual_keys.add(key)
            elif alert.portfolio_id == portfolio_id and alert.triggered_at is None:
                # 같은 목표가 둘이면(동시 등록 경합의 흔적) 하나만 남긴다
                if key in plan_alerts:
                    stale.append(alert)
                else:
                    plan_alerts[key] = alert

        wanted = {_rate_key(rate): (rate, usd) for rate, usd in targets}
        stale.extend(alert for key, alert in plan_alerts.items() if key not in wanted)

        to_create: list[tuple[float, float]] = []
        updated = skipped = 0
        for key, (rate, usd) in wanted.items():
            if key in plan_alerts:
                plan_alerts[key].planned_usd = round(usd, 2)
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
                )
            )
        await db.commit()

    logger.info(
        "fx_plan_alerts_synced",
        user_id=str(user_id),
        created=len(to_create),
        updated=updated,
        removed=len(stale),
        skipped_manual=skipped,
    )
    return FxPlanAlertSyncResult(len(to_create), updated, len(stale), skipped)
