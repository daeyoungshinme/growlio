"""목표 역산 포트폴리오 추천 서비스 (로드맵 A 3단계).

투자 목표(목표금액/월적립액/목표연도)를 역산해 필요 연평균 수익률을 구하고,
사용자가 "후보 ETF 관리"에서 등록한 후보 종목(`UserSettings.goal_candidate_tickers`) 중에서
그 수익률 이상을 만족하는 최소분산 포트폴리오를 Mean-Variance Optimization으로 추천한다.
`portfolio_optimizer.py`의 SLSQP 골격을 재사용하되, 기대수익률은 CAGR(기본 10년 — 진단화면에
노출되는 target_weighted_cagr_10y_pct와 달리 `goal_cagr_lookback_years` 설정에 따라 3/5/10년
중 선택 가능)을 사용하고 목표수익률 이상을 제약으로 둔다.

후보 종목을 한 번도 등록한 적 없으면(`goal_candidate_tickers is None`) 보유 종목 + 큐레이션
ETF 후보(`recommendation_universe.py`)로 초기 후보 목록을 구성해 DB에 저장한 뒤 사용한다 —
이후에는 사용자가 "후보 ETF 관리"에서 편집한 목록만이 유일한 계산 대상이다(자동 병합 없음).

`UserSettings.goal_risk_tolerance`(CONSERVATIVE/BALANCED/AGGRESSIVE)는 제약 없는 최소분산
포트폴리오의 자연 수익률과 종목당 최대 비중 제약 하 달성 가능한 최대 가중평균 CAGR 사이를
성향 비율로 보간한 지점을 등식 제약으로 고정해 더 높은 기대수익(및 변동성)을 갖는 해로 유도한다.
CONSERVATIVE는 오늘까지의 동작과 동일하게 부등식 제약(필요수익률 이상)만 사용하므로 순수
최소분산 결과가 그대로 유지된다. 실행가능성 하드체크는 원래 필요수익률로 판단하므로, 리스크
성향을 올린다고 이전에 가능하던 목표가 에러로 바뀌지 않는다.
`UserSettings.goal_max_weight_pct`는 종목당 최대 비중 상한(기본 40%)을 사용자가 조정할 수 있게 한다.

배당 목표(`UserSettings.annual_dividend_goal`)가 설정돼 있으면 필요 배당수익률(`required_dividend_yield_pct`)
을 `_optimize_goal_portfolio`의 부등식 제약으로도 전달해 실제 비중 계산에 반영한다 — 큐레이션
후보만으로 달성 불가능하면 제약을 적용하지 않고 note로 안내한다(fail-soft, 자산 목표 계산 자체는
막지 않음). `get_horizon_recommendations`(투자기간별)은 목표금액 역산을 하지 않는 별도 경로라 배당
목표를 반영하지 않는다.

자동 반영되지 않음 — 프론트엔드에서 사용자가 확인 후 수동으로 포트폴리오 편집기에 적용한다.

MVO 최적화 엔진은 `goal_portfolio_optimizer.py`, 후보 종목 관리/영속화는 `goal_candidate_service.py`
로 분리되어 있다 — 이 파일에는 API 진입점(전체 자산 기준 `get_goal_recommendation`, 투자기간별
`get_horizon_recommendations`)과 그 사이에서 공유되는 소규모 헬퍼만 남아 있다.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from datetime import UTC, date, datetime

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    CASH_EQUIVALENT_MARKET,
    CASH_EQUIVALENT_NAME,
    CASH_EQUIVALENT_TICKER,
    DOMESTIC_MARKETS,
)
from app.enums import AccountTaxType, InvestmentHorizon
from app.models.asset import AssetAccount
from app.models.user import UserSettings
from app.schemas.rebalancing import (
    GoalRecommendation,
    GoalRecommendationItem,
    HorizonGoalRecommendation,
    HorizonRecommendationResponse,
)
from app.services.dividend.constants import is_korean_etf
from app.services.dividend.sync_sources import (
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.goal_candidate_service import (
    _TAX_TYPE_MARKET_GROUP,
    _active_account_tax_types,
    _apply_index_region_preference,
    _get_or_seed_candidates,
    _persist_added_candidates,
    existing_items_from_positions,
)
from app.services.goal_portfolio_optimizer import _MAX_WEIGHT, _MIN_CANDIDATES, _optimize_goal_portfolio
from app.services.goal_return_solver import solve_required_annual_return_pct
from app.services.market_data_fetcher import fetch_yf_daily_returns
from app.services.market_signal_service import get_market_signal
from app.services.portfolio_service import build_portfolio_overview
from app.services.position_aggregator import query_latest_position_map
from app.services.price_service import get_historical_returns
from app.services.recommendation_universe import MAX_GOAL_CANDIDATE_TICKERS
from app.services.yahoo_price import _yfinance_sem, to_yf_symbol
from app.utils.cache_keys import (
    TTL_GOAL_RECOMMENDATION,
    RedisType,
    get_cached_json,
    goal_recommendation_horizon_key,
    goal_recommendation_key,
    set_cached_json,
)

logger = structlog.get_logger()

_DIVIDEND_FETCH_CONCURRENCY = 8
_DEFAULT_CAGR_LOOKBACK_YEARS = 10

_HORIZON_RISK_TOLERANCE: dict[str, str] = {
    "SHORT_TERM": "CONSERVATIVE",
    "MID_TERM": "BALANCED",
    "LONG_TERM": "AGGRESSIVE",
}
_HORIZON_ELIGIBLE_ASSET_CLASSES: dict[str, set[str]] = {
    "SHORT_TERM": {"BOND", "EQUITY", "CASH"},
    "MID_TERM": {"BOND", "EQUITY", "CASH"},
    "LONG_TERM": {"EQUITY"},
}
_NON_BINDING_RETURN_FLOOR = -50.0
"""기간별 추천은 목표 역산이 아니므로 required_return_pct 하한 제약을 사실상 무효화한다."""

_CASH_EQUIVALENT_TICKER = CASH_EQUIVALENT_TICKER
"""실제 시세 없는 합성 후보 식별자 — app.constants의 공유 정의 재노출(하위 호환 별칭)."""
_CASH_EQUIVALENT_NAME = CASH_EQUIVALENT_NAME
_CASH_EQUIVALENT_MARKET = CASH_EQUIVALENT_MARKET
_CASH_EQUIVALENT_CAGR_PCT = 3.0
"""CMA/파킹통장 평균 금리 가정치(%) — 실제 상품별로 상이하고 시세 데이터가 없어 고정값을 사용한다.
CONSERVATIVE 리스크 성향은 required_return_pct 부등식 제약이 비구속적(_NON_BINDING_RETURN_FLOOR)이므로
이 값은 비중 계산에 거의 영향을 주지 않고 주로 expected_return_pct 표시용으로 쓰인다."""
_CASH_EQUIVALENT_RETURN_DAYS = 252

_DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT = 80.0
"""단기(최대 3년) 목표는 안전자산 위주가 아니라 주식을 최소 이 비율까지 담아 다소 공격적으로
구성한다 — 사용자가 UserSettings.goal_short_term_equity_floor_pct로 조정 가능, NULL이면 이 기본값
사용. 등록된 주식 후보가 하나도 없으면 이 제약은 적용하지 않고 기존(안전자산만으로 최소분산)
동작을 유지한다."""

_DEFAULT_IRP_SAFE_ASSET_FLOOR_PCT = 30.0
"""IRP(개인형퇴직연금) 계좌는 실제 퇴직연금 규제(위험자산 투자한도 70%)에 근거해 안전자산
(채권+현금성) 비중을 투자기간과 무관하게 항상 이 비율 이상 유지하도록 강제한다. 법규에 근거한
고정 규칙이라 `_DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT`와 달리 UserSettings 오버라이드 필드를
두지 않는다. 단기(SHORT_TERM) 조합에서는 이 규칙이 `_DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT`(주식
최소 80%)와 정면 충돌하므로 IRP가 우선하고 단기 주식 하한 규칙은 적용하지 않는다."""


def _cash_equivalent_daily_returns() -> list[float]:
    """변동성 0으로 가정한 합성 일별수익률 시계열 — MVO 공분산 계산에 참여시키기 위함."""
    return [_CASH_EQUIVALENT_CAGR_PCT / 100 / _CASH_EQUIVALENT_RETURN_DAYS] * _CASH_EQUIVALENT_RETURN_DAYS


async def _fetch_market_signal_level(redis: RedisType) -> str | None:
    """추천 비중 계산에 반영할 시장 위험 신호 등급을 안전하게 조회한다.

    조회 실패 또는 `data_freshness="STALE"`(신뢰 불가)이면 감쇠 없이(None) 기존 동작을 유지한다
    — 참고용 제안이라 fail-open이 적절하며, AUTO 실행 게이트(`is_market_signal_blocking_auto_mode`)와
    달리 실패 시 보수적으로 차단할 필요가 없다.
    """
    try:
        signal = await get_market_signal(redis)
    except Exception as e:
        logger.warning("goal_recommendation_market_signal_failed", error=str(e))
        return None
    if signal.get("data_freshness") == "STALE":
        return None
    return signal.get("composite_level")


def _months_until_year_end(target_year: int) -> int:
    today = date.today()
    delta = relativedelta(date(target_year, 12, 31), today)
    return delta.years * 12 + delta.months


def _not_configured(note: str) -> GoalRecommendation:
    return GoalRecommendation(
        generated_at=datetime.now(UTC).isoformat(),
        is_configured=False,
        note=note,
    )


def _no_recommendation(
    note: str,
    required_return_pct: float | None = None,
    required_dividend_yield_pct: float | None = None,
) -> GoalRecommendation:
    return GoalRecommendation(
        generated_at=datetime.now(UTC).isoformat(),
        is_configured=True,
        required_return_pct=required_return_pct,
        required_dividend_yield_pct=required_dividend_yield_pct,
        note=note,
    )


async def _fetch_dividend_yields(candidates: list[tuple[str, str]]) -> dict[tuple[str, str], float]:
    """후보 종목의 배당수익률(%)을 실시간 조회한다.

    `api/v1/rebalancing.py`의 `_collect_dividend_map`과 동일한 소스(Naver/Yahoo)를 쓰되,
    임의의 후보 티커 목록(포트폴리오 미보유 큐레이션 ETF 포함)을 대상으로 한다는 점이 다르다.
    """
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(_DIVIDEND_FETCH_CONCURRENCY)
    result: dict[tuple[str, str], float] = {}

    async def _fetch_one(ticker: str, market: str) -> None:
        try:
            async with sem:
                if market.upper() in DOMESTIC_MARKETS:
                    fn = (
                        sync_naver_etf_dividend_info
                        if is_korean_etf(ticker, market)
                        else sync_naver_stock_dividend_info
                    )
                    info = await loop.run_in_executor(None, fn, ticker)
                else:
                    info = await loop.run_in_executor(None, sync_yahoo_dividend_info, to_yf_symbol(ticker, market))
            if info["dividend_yield"] > 0:
                result[(ticker, market)] = info["dividend_yield"] * 100
        except Exception as e:
            logger.warning("goal_recommendation_dividend_fetch_failed", ticker=ticker, market=market, error=str(e))

    await asyncio.gather(*[_fetch_one(t, m) for t, m in candidates])
    return result


async def get_goal_recommendation(
    redis: RedisType,
    base_krw: float,
    existing_items: list[tuple[str, str, str]],
    settings_row: UserSettings | None,
    db: AsyncSession,
) -> GoalRecommendation:
    """`_compute_goal_recommendation()` 결과를 유저당 TTL_GOAL_RECOMMENDATION(10분) 캐싱한다.

    계산 자체가 CAGR/배당수익률 외부 조회 + SLSQP 최적화를 포함해 무겁고, 진단탭 마운트 시
    무조건 호출되므로 짧은 TTL로도 체감 속도 개선 효과가 크다. 목표 설정·후보 ETF 변경,
    계좌 sync(포지션 변경) 시 `invalidate_goal_recommendation_caches()`/`invalidate_account_caches()`가
    캐시를 무효화한다 — 그 외의 사소한 자산평가액 변동은 TTL 만료까지 반영되지 않는다(허용된 트레이드오프).

    `recommended_items`가 비어 있는 결과(목표 미설정·달성불가·후보부족·Yahoo 서킷브레이커 등으로
    시세 데이터 조회 실패 등)는 캐싱하지 않는다 — 이런 실패는 대부분 일시적 외부 API 장애이며,
    캐싱하면 다음 요청부터 서킷브레이커가 복구된 뒤에도 TTL 동안 계속 같은 실패를 반환하게 된다.
    """
    user_id = getattr(settings_row, "user_id", None)
    if user_id is not None:
        cached = await get_cached_json(redis, goal_recommendation_key(user_id))
        if cached is not None:
            return GoalRecommendation(**cached)

    result = await _compute_goal_recommendation(redis, base_krw, existing_items, settings_row, db)

    if user_id is not None and result.recommended_items:
        await set_cached_json(
            redis, goal_recommendation_key(user_id), result.model_dump(mode="json"), TTL_GOAL_RECOMMENDATION
        )
    return result


async def _compute_goal_recommendation(
    redis: RedisType,
    base_krw: float,
    existing_items: list[tuple[str, str, str]],
    settings_row: UserSettings | None,
    db: AsyncSession,
) -> GoalRecommendation:
    """기준 자산총액과 유저 목표를 받아 목표 역산 추천을 계산한다."""
    if not settings_row or not settings_row.goal_amount or not settings_row.retirement_target_year:
        return _not_configured("목표금액·목표연도를 설정하면 추천을 받을 수 있습니다")

    pmt = float(settings_row.monthly_deposit_amount or 0)
    if not pmt and settings_row.annual_deposit_goal:
        pmt = float(settings_row.annual_deposit_goal) / 12
    goal_amount = float(settings_row.goal_amount)
    target_year = int(settings_row.retirement_target_year)

    pv = base_krw
    n_months = _months_until_year_end(target_year)

    required_dividend_yield_pct = (
        round(float(settings_row.annual_dividend_goal) / pv * 100, 2)
        if settings_row.annual_dividend_goal and pv > 0
        else None
    )

    if n_months <= 0:
        return _no_recommendation("목표 연도가 이미 지났습니다 — 목표연도를 다시 설정해주세요")
    if pv >= goal_amount:
        return _no_recommendation(
            "이미 목표 금액을 달성했습니다", required_dividend_yield_pct=required_dividend_yield_pct
        )

    required_return_pct = solve_required_annual_return_pct(pv, pmt, n_months, goal_amount)
    if required_return_pct is None:
        return _no_recommendation(
            "현재 조건(적립액·기간)으로는 달성이 매우 어려운 목표입니다",
            required_dividend_yield_pct=required_dividend_yield_pct,
        )

    candidate_dicts = await _get_or_seed_candidates(db, settings_row, existing_items)

    if not candidate_dicts:
        return _no_recommendation(
            "등록된 후보 종목이 없습니다 — 후보 ETF를 추가해주세요",
            required_return_pct,
            required_dividend_yield_pct,
        )

    preference_fallback_note: str | None = None
    computed_candidates = candidate_dicts
    user_id = getattr(settings_row, "user_id", None)
    if user_id is not None:
        tax_type_rows = await _active_account_tax_types(db, user_id)
        distinct_tax_types = {t or AccountTaxType.GENERAL.value for t in tax_type_rows}
        if len(distinct_tax_types) == 1:
            capacity_remaining = MAX_GOAL_CANDIDATE_TICKERS - len(candidate_dicts)
            computed_candidates, preference_fallback_note, added = _apply_index_region_preference(
                candidate_dicts, next(iter(distinct_tax_types)), capacity_remaining
            )
            if added:
                await _persist_added_candidates(db, user_id, added)

    def _combine_note(msg: str | None) -> str | None:
        if preference_fallback_note and msg:
            return f"{preference_fallback_note} {msg}"
        return preference_fallback_note or msg

    risk_tolerance = getattr(settings_row, "goal_risk_tolerance", None) or "CONSERVATIVE"
    max_weight_pct_raw = getattr(settings_row, "goal_max_weight_pct", None)
    max_weight = float(max_weight_pct_raw) / 100 if max_weight_pct_raw else _MAX_WEIGHT
    cagr_lookback_years = int(getattr(settings_row, "goal_cagr_lookback_years", None) or _DEFAULT_CAGR_LOOKBACK_YEARS)

    candidates = [(c["ticker"], c["name"], c["market"]) for c in computed_candidates]
    tickers_only = [(t, m) for t, _, m in candidates]

    cagr_map, dividend_map, market_signal_level = await asyncio.gather(
        get_historical_returns(tickers_only, redis=redis, years=cagr_lookback_years),
        _fetch_dividend_yields(tickers_only),
        _fetch_market_signal_level(redis),
    )

    filtered = [
        (to_yf_symbol(t, m), (t, name, m), cagr_map[(t, m)]["cagr_pct"], dividend_map.get((t, m), 0.0))
        for t, name, m in candidates
        if (t, m) in cagr_map and cagr_map[(t, m)].get("cagr_pct") is not None
    ]
    if len(filtered) < _MIN_CANDIDATES:
        result = _no_recommendation(
            "추천에 필요한 수익률 데이터를 가져오지 못했습니다",
            required_return_pct,
            required_dividend_yield_pct,
        )
        result.note = _combine_note(result.note)
        return result

    f_symbols = [f[0] for f in filtered]
    f_tickers = [f[1] for f in filtered]
    f_cagrs = [f[2] for f in filtered]
    f_dividends = [f[3] for f in filtered]

    loop = asyncio.get_running_loop()
    async with _yfinance_sem:
        returns_map = await loop.run_in_executor(None, fetch_yf_daily_returns, f_symbols)
    items, expected_return_pct, opt_note = await loop.run_in_executor(
        None,
        functools.partial(
            _optimize_goal_portfolio,
            f_symbols,
            f_tickers,
            f_cagrs,
            returns_map,
            required_return_pct,
            max_weight=max_weight,
            risk_tolerance=risk_tolerance,
            market_signal_level=market_signal_level,
            dividend_yields=f_dividends,
            required_dividend_yield_pct=required_dividend_yield_pct,
        ),
    )

    expected_dividend_yield_pct = None
    if items:
        expected_dividend_yield_pct = round(
            sum(i["weight"] * dividend_map.get((i["ticker"], i["market"]), 0.0) for i in items) / 100, 2
        )

    return GoalRecommendation(
        generated_at=datetime.now(UTC).isoformat(),
        is_configured=True,
        required_return_pct=required_return_pct,
        required_dividend_yield_pct=required_dividend_yield_pct,
        recommended_items=[GoalRecommendationItem(**i) for i in items],
        expected_return_pct=expected_return_pct,
        expected_dividend_yield_pct=expected_dividend_yield_pct,
        note=_combine_note(opt_note),
        cagr_lookback_years=cagr_lookback_years,
        risk_tolerance=risk_tolerance,
        max_weight_pct=round(max_weight * 100, 2),
        market_signal_level=market_signal_level,
    )


async def _build_horizon_result(
    redis: RedisType,
    horizon: str,
    tax_type: str,
    account_ids: list[uuid.UUID],
    base_krw: float,
    eligible_candidates: list[dict[str, str]],
    risk_tolerance: str,
    max_weight: float,
    cagr_lookback_years: int,
    short_term_equity_floor: float,
    market_signal_level: str | None = None,
    preference_fallback_note: str | None = None,
) -> HorizonGoalRecommendation:
    """필터링된(자산군·시장 적합) 후보 목록으로 (기간, 세제유형) 조합 하나에 대한 추천을 계산한다.

    SHORT_TERM(비IRP)은 등록된 BOND/CASH 후보 개수와 무관하게 현금성 자산(CMA·파킹통장) 합성
    후보를 항상 함께 분석 대상에 포함시킨다. 등록된 주식(EQUITY) 후보가 있으면 `short_term_equity_floor`
    비율 이상을 주식에 배분하도록 강제해 지나치게 안전자산 위주로 수렴하지 않게 한다.

    IRP(개인형퇴직연금)는 투자기간과 무관하게 `_DEFAULT_IRP_SAFE_ASSET_FLOOR_PCT`(안전자산 최소
    30%) 제약을 적용한다 — 퇴직연금 규제(위험자산 투자한도 70%)에 근거한 고정 규칙이라 SHORT_TERM의
    주식 최소 80% 규칙보다 우선한다(동시에 적용 시 상호 모순이라 IRP 조합에서는 단기 주식 하한
    규칙 자체를 적용하지 않는다). 이때 현금성 자산 합성 후보는 **실제로 유효한(시세 데이터가 확보된)
    BOND/CASH 후보가 하나도 없을 때만** 포함시킨다 — 실보유 안전자산 후보가 있는데도 합성 후보를
    함께 넣으면, 분산·공분산이 정확히 0인 합성 후보가 MVO 목적함수(순수 분산 최소화) 상 항상
    우위를 점해 실제로는 절대 비중을 받지 못하고 합성 자산이 30% 전량을 가져가 버리기 때문이다
    (`_cash_equivalent_daily_returns` 참고). 실보유 후보가 있으면 그 후보만으로, 없으면 합성
    자산 100%로 안전자산 몫을 채운다.

    `preference_fallback_note`는 세제유형별 추종지수 선호 필터(`get_horizon_recommendations`)가
    선호 지역 후보 부족으로 전체 후보로 되돌아갔을 때 그 사실을 안내하기 위해 전달된다 — 이후
    계산되는 다른 note와 함께(있으면 앞에 붙여) 표시된다.
    """
    is_irp = tax_type == AccountTaxType.IRP.value
    safety_net_horizon = horizon == "SHORT_TERM" or is_irp

    def _combine_note(msg: str | None) -> str | None:
        if preference_fallback_note and msg:
            return f"{preference_fallback_note} {msg}"
        return preference_fallback_note or msg

    if not safety_net_horizon and len(eligible_candidates) < _MIN_CANDIDATES:
        needs_conservative = horizon == "MID_TERM"
        note = (
            "이 기간에 적합한 후보가 부족합니다 — 후보 ETF 관리에서 채권/현금성 ETF를 추가해주세요"
            if needs_conservative
            else "이 기간에 적합한 후보가 부족합니다 — 후보 ETF를 추가해주세요"
        )
        return HorizonGoalRecommendation(
            investment_horizon=horizon,
            tax_type=tax_type,
            base_krw=base_krw,
            account_count=len(account_ids),
            risk_tolerance=risk_tolerance,
            max_weight_pct=round(max_weight * 100, 2),
            market_signal_level=market_signal_level,
            note=_combine_note(note),
        )

    candidates = [(c["ticker"], c["name"], c["market"], c.get("asset_class", "EQUITY")) for c in eligible_candidates]
    tickers_only = [(t, m) for t, _, m, _ in candidates]

    cagr_map = (
        await get_historical_returns(tickers_only, redis=redis, years=cagr_lookback_years) if tickers_only else {}
    )
    filtered = [
        (to_yf_symbol(t, m), (t, name, m), cagr_map[(t, m)]["cagr_pct"], asset_class == "EQUITY")
        for t, name, m, asset_class in candidates
        if (t, m) in cagr_map and cagr_map[(t, m)].get("cagr_pct") is not None
    ]
    has_real_safe_asset = any(not is_eq for *_, is_eq in filtered)
    include_cash_equivalent = (not has_real_safe_asset) if is_irp else (horizon == "SHORT_TERM")
    if include_cash_equivalent:
        filtered.append(
            (
                _CASH_EQUIVALENT_TICKER,
                (_CASH_EQUIVALENT_TICKER, _CASH_EQUIVALENT_NAME, _CASH_EQUIVALENT_MARKET),
                _CASH_EQUIVALENT_CAGR_PCT,
                False,
            )
        )

    if not filtered:
        return HorizonGoalRecommendation(
            investment_horizon=horizon,
            tax_type=tax_type,
            base_krw=base_krw,
            account_count=len(account_ids),
            risk_tolerance=risk_tolerance,
            max_weight_pct=round(max_weight * 100, 2),
            market_signal_level=market_signal_level,
            note=_combine_note("추천에 필요한 수익률 데이터를 가져오지 못했습니다"),
        )

    if len(filtered) == 1:
        # 유효 후보가 하나뿐인 경우 — 옵티마이저 없이 전액 배분. 현금성 자산 합성 후보만 남았을 수도
        # 있고(등록된 실 후보가 없거나 전부 시세 데이터 미확보), 실보유 안전자산 후보 하나만 유효했을
        # 수도 있다(예: 매칭되는 EQUITY 후보가 없어 BOND 후보 1개만 남음) — 둘을 구분해 안내한다.
        _, (tk, name, mk), cagr, _ = filtered[0]
        is_synthetic = tk == _CASH_EQUIVALENT_TICKER
        return HorizonGoalRecommendation(
            investment_horizon=horizon,
            tax_type=tax_type,
            base_krw=base_krw,
            account_count=len(account_ids),
            recommended_items=[GoalRecommendationItem(ticker=tk, name=name, market=mk, weight=100.0)],
            expected_return_pct=cagr,
            risk_tolerance=risk_tolerance,
            max_weight_pct=round(max_weight * 100, 2),
            market_signal_level=market_signal_level,
            includes_cash_equivalent=is_synthetic,
            note=_combine_note(
                (
                    "채권/현금성 ETF 후보가 등록되어 있지 않아 현금성 자산(CMA·파킹통장 등)으로 전액 "
                    "배분을 권장합니다. 후보 ETF 관리에서 채권/현금성 ETF를 등록하면 함께 분석해 비중을 조정합니다."
                )
                if is_synthetic
                else None
            ),
        )

    f_symbols = [f[0] for f in filtered]
    f_tickers = [f[1] for f in filtered]
    f_cagrs = [f[2] for f in filtered]
    f_is_equity = [f[3] for f in filtered]

    loop = asyncio.get_running_loop()
    real_symbols = [s for s in f_symbols if s != _CASH_EQUIVALENT_TICKER]
    if real_symbols:
        async with _yfinance_sem:
            returns_map = await loop.run_in_executor(None, fetch_yf_daily_returns, real_symbols)
    else:
        returns_map = {}
    if include_cash_equivalent:
        returns_map[_CASH_EQUIVALENT_TICKER] = _cash_equivalent_daily_returns()

    equity_floor: float | None = None
    equity_ceiling: float | None = None
    if is_irp:
        equity_ceiling = 1.0 - _DEFAULT_IRP_SAFE_ASSET_FLOOR_PCT / 100
    elif include_cash_equivalent and any(f_is_equity):
        equity_floor = short_term_equity_floor

    items, expected_return_pct, opt_note = await loop.run_in_executor(
        None,
        functools.partial(
            _optimize_goal_portfolio,
            f_symbols,
            f_tickers,
            f_cagrs,
            returns_map,
            _NON_BINDING_RETURN_FLOOR,
            max_weight=max_weight,
            risk_tolerance=risk_tolerance,
            is_equity=f_is_equity,
            equity_floor=equity_floor,
            equity_ceiling=equity_ceiling,
            market_signal_level=market_signal_level,
        ),
    )

    includes_cash_equivalent = any(i["ticker"] == _CASH_EQUIVALENT_TICKER for i in items)

    if opt_note is None and equity_floor is not None:
        opt_note = (
            f"단기(최대 3년) 목표는 안정적인 주식 위주로 최소 {equity_floor * 100:.0f}%까지 배분하고, "
            f"안전자산은 {100 - equity_floor * 100:.0f}% 이내로 제한합니다."
        )
    elif opt_note is None and equity_ceiling is not None:
        opt_note = (
            f"IRP(개인형퇴직연금) 계좌는 퇴직연금 규정에 따라 위험자산(주식)을 최대 "
            f"{equity_ceiling * 100:.0f}%로 제한하고, 안전자산(채권·현금성)을 최소 "
            f"{100 - equity_ceiling * 100:.0f}% 이상 배분합니다."
        )

    return HorizonGoalRecommendation(
        investment_horizon=horizon,
        tax_type=tax_type,
        base_krw=base_krw,
        account_count=len(account_ids),
        recommended_items=[GoalRecommendationItem(**i) for i in items],
        expected_return_pct=expected_return_pct,
        risk_tolerance=risk_tolerance,
        max_weight_pct=round(max_weight * 100, 2),
        includes_cash_equivalent=includes_cash_equivalent,
        market_signal_level=market_signal_level,
        note=_combine_note(opt_note),
    )


async def get_horizon_recommendations(
    redis: RedisType,
    db: AsyncSession,
    user_id: uuid.UUID,
    settings_row: UserSettings,
) -> HorizonRecommendationResponse:
    """`_compute_horizon_recommendations()` 결과를 유저당 TTL_GOAL_RECOMMENDATION(10분) 캐싱한다.

    최대 15개(투자기간×세제유형) 조합에 대해 순차 DB 조회 후 조합별 SLSQP 최적화를 수행하는
    무거운 계산이라 캐싱 효과가 크다. 무효화 조건은 `get_goal_recommendation`과 동일.

    조합 중 하나라도 `recommended_items`가 비어 있으면(예: 해외전용 조합만 Yahoo 서킷브레이커에
    걸려 시세 데이터를 못 가져온 경우) 응답 전체를 캐싱하지 않는다 — 15개 조합이 하나의 캐시
    키로 묶여 있어, 그대로 캐싱하면 일시적으로 실패한 조합 하나 때문에 나머지 정상 조합까지
    TTL 동안 통째로 그 실패 상태를 계속 반환하게 된다.
    """
    cached = await get_cached_json(redis, goal_recommendation_horizon_key(user_id))
    if cached is not None:
        return HorizonRecommendationResponse(**cached)

    result = await _compute_horizon_recommendations(redis, db, user_id, settings_row)

    if all(rec.recommended_items for rec in result.recommendations):
        await set_cached_json(
            redis, goal_recommendation_horizon_key(user_id), result.model_dump(mode="json"), TTL_GOAL_RECOMMENDATION
        )
    return result


async def _compute_horizon_recommendations(
    redis: RedisType,
    db: AsyncSession,
    user_id: uuid.UUID,
    settings_row: UserSettings,
) -> HorizonRecommendationResponse:
    """투자기간(단기/중기/장기) × 세제유형(ISA/연금저축/IRP/일반/해외전용) 조합별로 계좌를 묶어
    기간별 리스크 성향 + 세제유형별 투자 가능 시장에 맞는 추천을 계산한다.

    목표금액/목표연도 역산은 하지 않는다 — `_NON_BINDING_RETURN_FLOOR`로 required_return_pct 제약을
    사실상 무효화하고, 오직 기간별 리스크 성향(단기=보수/중기=중립/장기=공격)만으로 결과를 결정한다.
    태그된 계좌가 하나도 없는 (기간, 세제유형) 조합은 결과에서 생략한다.
    """
    max_weight_pct_raw = getattr(settings_row, "goal_max_weight_pct", None)
    max_weight = float(max_weight_pct_raw) / 100 if max_weight_pct_raw else _MAX_WEIGHT
    cagr_lookback_years = int(getattr(settings_row, "goal_cagr_lookback_years", None) or _DEFAULT_CAGR_LOOKBACK_YEARS)
    short_term_equity_floor_pct_raw = getattr(settings_row, "goal_short_term_equity_floor_pct", None)
    short_term_equity_floor = (
        float(short_term_equity_floor_pct_raw)
        if short_term_equity_floor_pct_raw is not None
        else _DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT
    ) / 100

    all_pos_map = await query_latest_position_map(user_id, db, include_name=True)
    candidate_dicts = await _get_or_seed_candidates(db, settings_row, existing_items_from_positions(all_pos_map))

    rows = (
        await db.execute(
            select(AssetAccount.investment_horizon, AssetAccount.tax_type, AssetAccount.id).where(
                AssetAccount.user_id == user_id,
                AssetAccount.is_active == True,  # noqa: E712
                AssetAccount.investment_horizon.isnot(None),
            )
        )
    ).all()
    accounts_by_pair: dict[tuple[str, str], list[uuid.UUID]] = {}
    for horizon_value, tax_type_value, account_id in rows:
        key = (horizon_value, tax_type_value or AccountTaxType.GENERAL.value)
        accounts_by_pair.setdefault(key, []).append(account_id)

    # 1단계: DB(AsyncSession, 동시 접근 불가) 의존 부분 — 계좌당 자산총액·후보 필터링을 조합별로
    # 순차 계산한다. `candidate_dicts`는 `_apply_index_region_preference`가 앞선 조합에서 추가한
    # 큐레이션 후보를 뒤따르는 조합의 capacity_remaining/필터링에 반영해야 하므로 병렬화할 수 없다.
    combos: list[tuple[str, str, list[uuid.UUID], float, list[dict[str, str]], str | None]] = []
    all_added: list[dict[str, str]] = []
    for horizon in InvestmentHorizon:
        for tax_type in AccountTaxType:
            account_ids = accounts_by_pair.get((horizon.value, tax_type.value))
            if not account_ids:
                continue

            overview = await build_portfolio_overview(user_id, db, account_ids=account_ids, redis=redis)
            base_krw = float(overview.get("total_assets_krw", 0))

            eligible_classes = _HORIZON_ELIGIBLE_ASSET_CLASSES[horizon.value]
            if tax_type.value == AccountTaxType.IRP.value:
                # IRP는 퇴직연금 규제상 안전자산 최소 30% 하한이 투자기간과 무관하게 적용되므로,
                # LONG_TERM(원래 EQUITY만 허용)에서도 예외적으로 BOND/CASH 후보를 후보군에 포함시킨다.
                eligible_classes = eligible_classes | {"BOND", "CASH"}
            market_group = _TAX_TYPE_MARKET_GROUP[tax_type.value]
            eligible_candidates = [
                c
                for c in candidate_dicts
                if c.get("asset_class", "EQUITY") in eligible_classes
                and (c["market"].upper() in DOMESTIC_MARKETS) == (market_group == "DOMESTIC")
            ]
            capacity_remaining = MAX_GOAL_CANDIDATE_TICKERS - len(candidate_dicts)
            eligible_candidates, preference_fallback_note, added = _apply_index_region_preference(
                eligible_candidates, tax_type.value, capacity_remaining
            )
            if added:
                candidate_dicts.extend(added)
                all_added.extend(added)

            combos.append(
                (horizon.value, tax_type.value, account_ids, base_krw, eligible_candidates, preference_fallback_note)
            )

    if all_added:
        await _persist_added_candidates(db, user_id, all_added)

    # 15개 조합이 동일한 시장 신호 스냅샷을 공유하도록 조합별 반복 조회 대신 한 번만 조회한다.
    market_signal_level = await _fetch_market_signal_level(redis)

    # 2단계: DB에 의존하지 않는 외부 I/O(Yahoo/pykrx 수익률 조회 + SLSQP 최적화)는 조합 수(최대 15개)만큼
    # 동시 실행한다 — `_build_horizon_result`는 `db`를 사용하지 않으므로 AsyncSession 동시성 제약이 없다.
    results = await asyncio.gather(
        *(
            _build_horizon_result(
                redis,
                horizon_value,
                tax_type_value,
                account_ids,
                base_krw,
                eligible_candidates,
                _HORIZON_RISK_TOLERANCE[horizon_value],
                max_weight,
                cagr_lookback_years,
                short_term_equity_floor,
                market_signal_level=market_signal_level,
                preference_fallback_note=preference_fallback_note,
            )
            for (
                horizon_value,
                tax_type_value,
                account_ids,
                base_krw,
                eligible_candidates,
                preference_fallback_note,
            ) in combos
        )
    )

    return HorizonRecommendationResponse(
        generated_at=datetime.now(UTC).isoformat(),
        recommendations=list(results),
    )
