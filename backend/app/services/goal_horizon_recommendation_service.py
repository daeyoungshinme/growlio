"""투자기간별(단기/중기/장기 × 세제유형) 목표 역산 포트폴리오 추천 서비스.

`goal_recommendation_service.py`(전체 자산 기준 진입점)의 서브모듈 — 2026-09-01 분리
(`goal_age_recommendation_service.py`(연령대별, 2026-08-13 분리)와 동일 패턴).

목표금액/목표연도 역산을 **하지 않는다** — `_NON_BINDING_RETURN_FLOOR`로 required_return_pct
하한 제약을 사실상 무효화하고, 오직 기간별 리스크 성향(단기=보수/중기=중립/장기=공격)과
세제유형별 투자 가능 시장/규제(IRP 안전자산 30% 하한 등)만으로 결과를 결정한다.

공유 헬퍼(`_fetch_dividend_yields`/`_attach_dividend_yield`/`_suggest_for_dividend_goal`/
`_fetch_market_signal_level`/`_equity_class_bounds`/`_cash_equivalent_daily_returns` +
`_CASH_EQUIVALENT_*`/`_NON_BINDING_RETURN_FLOOR`/`_DEFAULT_CAGR_LOOKBACK_YEARS` 상수)는
`_goal_recommendation_common.py`(`_grc`)에 있고 이 모듈이 `_grc.fn()` 모듈 참조로 호출한다.
`get_horizon_recommendations` 소비자는 `api/v1/rebalancing.py`,
`alerts/recommendation_drift_alert_service.py`.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DOMESTIC_MARKETS
from app.enums import AccountTaxType, InvestmentHorizon
from app.models.asset import AssetAccount
from app.models.user import UserSettings
from app.schemas.rebalancing import (
    GoalRecommendationItem,
    HorizonGoalRecommendation,
    HorizonRecommendationResponse,
    SuggestedGoalCandidate,
)
from app.services import _goal_recommendation_common as _grc
from app.services.goal_candidate_service import (
    _TAX_TYPE_MARKET_GROUP,
    _apply_index_region_preference,
    _get_or_seed_candidates,
    _matches_index_region_preference,
    _persist_added_candidates,
    detect_duplicate_tracking_index_note,
    existing_items_from_positions,
)
from app.services.goal_portfolio_optimizer import _MAX_WEIGHT, _MIN_CANDIDATES, _optimize_goal_portfolio
from app.services.market_data_fetcher import fetch_yf_daily_returns
from app.services.portfolio_service import (
    build_portfolio_overview,
    compute_total_assets_krw,
    prefetch_accounts_snapshot_positions,
)
from app.services.position_aggregator import query_latest_position_map
from app.services.price_service import get_historical_returns
from app.services.recommendation_universe import MAX_GOAL_CANDIDATE_TICKERS
from app.services.yahoo_price import _yfinance_sem, to_yf_symbol
from app.utils.cache_keys import (
    TTL_GOAL_RECOMMENDATION,
    CacheStoreType,
    get_cached_json,
    goal_recommendation_horizon_key,
    set_cached_json,
)
from app.utils.inproc_lock import single_flight_fetch

logger = structlog.get_logger()

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


async def _build_horizon_candidate_universe(
    cache: CacheStoreType,
    eligible_candidates: list[dict[str, str]],
    cagr_lookback_years: int,
    is_irp: bool,
    horizon: str,
) -> tuple[list[tuple[str, tuple[str, str, str], float, bool, float]], dict[tuple[str, str], float], bool]:
    """(기간, 세제유형) 조합의 후보 유니버스를 구성한다.

    CAGR 데이터가 확보된 후보만 남기고, IRP는 실보유 안전자산 후보가 하나도 없을 때만,
    SHORT_TERM은 항상 현금성 자산 합성 후보를 포함시킨다(`_build_horizon_result` 독스트링 참고).
    """
    candidates = [(c["ticker"], c["name"], c["market"], c.get("asset_class", "EQUITY")) for c in eligible_candidates]
    tickers_only = [(t, m) for t, _, m, _ in candidates]

    cagr_map, dividend_map = (
        await asyncio.gather(
            get_historical_returns(tickers_only, cache=cache, years=cagr_lookback_years),
            _grc._fetch_dividend_yields(cache, tickers_only),
        )
        if tickers_only
        else ({}, {})
    )
    filtered = [
        (
            to_yf_symbol(t, m),
            (t, name, m),
            cagr_map[(t, m)]["cagr_pct"],
            asset_class == "EQUITY",
            dividend_map.get((t, m), 0.0),
        )
        for t, name, m, asset_class in candidates
        if (t, m) in cagr_map and cagr_map[(t, m)].get("cagr_pct") is not None
    ]
    has_real_safe_asset = any(not is_eq for _, _, _, is_eq, _ in filtered)
    include_cash_equivalent = (not has_real_safe_asset) if is_irp else (horizon == "SHORT_TERM")
    if include_cash_equivalent:
        filtered.append(
            (
                _grc._CASH_EQUIVALENT_TICKER,
                (_grc._CASH_EQUIVALENT_TICKER, _grc._CASH_EQUIVALENT_NAME, _grc._CASH_EQUIVALENT_MARKET),
                _grc._CASH_EQUIVALENT_CAGR_PCT,
                False,
                0.0,
            )
        )
    return filtered, dividend_map, include_cash_equivalent


def _single_candidate_horizon_result(
    single: tuple[str, tuple[str, str, str], float, bool, float],
    horizon: str,
    tax_type: str,
    base_krw: float,
    account_count: int,
    risk_tolerance: str,
    max_weight: float,
    market_signal_level: str | None,
    combine_note: Callable[[str | None], str | None],
    required_dividend_yield_pct: float | None = None,
) -> HorizonGoalRecommendation:
    """유효 후보가 1개뿐일 때 옵티마이저 없이 전액 배분하는 조기 반환 결과를 만든다.

    현금성 자산 합성 후보만 남았을 수도(등록 후보 없음/시세 미확보) 있고, 실보유 안전자산 후보
    하나만 유효했을 수도 있다 — `is_synthetic`으로 구분해 안내 문구를 다르게 붙인다.
    """
    _, (tk, name, mk), cagr, _, dividend = single
    is_synthetic = tk == _grc._CASH_EQUIVALENT_TICKER
    return HorizonGoalRecommendation(
        investment_horizon=horizon,
        tax_type=tax_type,
        base_krw=base_krw,
        account_count=account_count,
        recommended_items=[
            GoalRecommendationItem(
                ticker=tk, name=name, market=mk, weight=100.0, dividend_yield_pct=dividend if dividend > 0 else None
            )
        ],
        required_dividend_yield_pct=required_dividend_yield_pct,
        expected_return_pct=cagr,
        expected_dividend_yield_pct=dividend if dividend > 0 else None,
        risk_tolerance=risk_tolerance,
        max_weight_pct=round(max_weight * 100, 2),
        market_signal_level=market_signal_level,
        includes_cash_equivalent=is_synthetic,
        note=combine_note(
            (
                "채권/현금성 ETF 후보가 등록되어 있지 않아 현금성 자산(CMA·파킹통장 등)으로 전액 "
                "배분을 권장합니다. 후보 ETF 관리에서 채권/현금성 ETF를 등록하면 함께 분석해 비중을 조정합니다."
            )
            if is_synthetic
            else None
        ),
    )


async def _build_horizon_result(
    cache: CacheStoreType,
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
    required_dividend_yield_pct: float | None = None,
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

    `required_dividend_yield_pct`가 주어지면(배당 목표 설정 시, 전체 자산 기준과 동일한 퍼센트를
    모든 조합에 동일 적용 — `_compute_horizon_recommendations` 참고) 배당 하한 제약으로도 반영한다.
    배당수익률은 목표 설정 여부와 무관하게 항상 조회해 `expected_dividend_yield_pct`로 표시한다
    (전체 자산 기준 경로와 동일한 동작).
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
            required_dividend_yield_pct=required_dividend_yield_pct,
            risk_tolerance=risk_tolerance,
            max_weight_pct=round(max_weight * 100, 2),
            market_signal_level=market_signal_level,
            note=_combine_note(note),
        )

    filtered, dividend_map, include_cash_equivalent = await _build_horizon_candidate_universe(
        cache, eligible_candidates, cagr_lookback_years, is_irp, horizon
    )

    if not filtered:
        return HorizonGoalRecommendation(
            investment_horizon=horizon,
            tax_type=tax_type,
            base_krw=base_krw,
            account_count=len(account_ids),
            required_dividend_yield_pct=required_dividend_yield_pct,
            risk_tolerance=risk_tolerance,
            max_weight_pct=round(max_weight * 100, 2),
            market_signal_level=market_signal_level,
            note=_combine_note("추천에 필요한 수익률 데이터를 가져오지 못했습니다"),
        )

    if len(filtered) == 1:
        return _single_candidate_horizon_result(
            filtered[0],
            horizon,
            tax_type,
            base_krw,
            len(account_ids),
            risk_tolerance,
            max_weight,
            market_signal_level,
            _combine_note,
            required_dividend_yield_pct=required_dividend_yield_pct,
        )

    f_symbols = [f[0] for f in filtered]
    f_tickers = [f[1] for f in filtered]
    f_cagrs = [f[2] for f in filtered]
    f_is_equity = [f[3] for f in filtered]
    f_asset_classes = ["EQUITY" if is_eq else "OTHER" for is_eq in f_is_equity]
    f_dividends = [f[4] for f in filtered]

    loop = asyncio.get_running_loop()
    real_symbols = [s for s in f_symbols if s != _grc._CASH_EQUIVALENT_TICKER]
    if real_symbols:
        async with _yfinance_sem:
            returns_map = await loop.run_in_executor(None, fetch_yf_daily_returns, real_symbols)
    else:
        returns_map = {}
    if include_cash_equivalent:
        returns_map[_grc._CASH_EQUIVALENT_TICKER] = _grc._cash_equivalent_daily_returns()

    equity_floor: float | None = None
    equity_ceiling: float | None = None
    if is_irp:
        equity_ceiling = 1.0 - _DEFAULT_IRP_SAFE_ASSET_FLOOR_PCT / 100
    elif include_cash_equivalent and any(f_is_equity):
        equity_floor = short_term_equity_floor

    # 자산군 단위 비중 제약 일반화(`_optimize_goal_portfolio`의 `class_bounds`) — 이 경로는
    # EQUITY vs 그 외(OTHER)의 기존 이분법 그대로 매핑한다(단기 주식 하한 / IRP 주식 상한).
    class_bounds = _grc._equity_class_bounds(equity_floor, equity_ceiling)

    items, expected_return_pct, expected_volatility_pct, opt_note = await loop.run_in_executor(
        None,
        functools.partial(
            _optimize_goal_portfolio,
            f_symbols,
            f_tickers,
            f_cagrs,
            returns_map,
            _grc._NON_BINDING_RETURN_FLOOR,
            max_weight=max_weight,
            risk_tolerance=risk_tolerance,
            asset_classes=f_asset_classes,
            class_bounds=class_bounds,
            market_signal_level=market_signal_level,
            dividend_yields=f_dividends,
            required_dividend_yield_pct=required_dividend_yield_pct,
        ),
    )

    includes_cash_equivalent = any(i["ticker"] == _grc._CASH_EQUIVALENT_TICKER for i in items)
    expected_dividend_yield_pct = None
    if items:
        expected_dividend_yield_pct = round(
            sum(i["weight"] * dividend_map.get((i["ticker"], i["market"]), 0.0) for i in items) / 100, 2
        )

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
        recommended_items=_grc._attach_dividend_yield(items, dividend_map),
        required_dividend_yield_pct=required_dividend_yield_pct,
        expected_return_pct=expected_return_pct,
        expected_dividend_yield_pct=expected_dividend_yield_pct,
        expected_volatility_pct=expected_volatility_pct,
        risk_tolerance=risk_tolerance,
        max_weight_pct=round(max_weight * 100, 2),
        includes_cash_equivalent=includes_cash_equivalent,
        market_signal_level=market_signal_level,
        note=_combine_note(opt_note),
    )


async def get_horizon_recommendations(
    cache: CacheStoreType,
    db: AsyncSession,
    user_id: uuid.UUID,
    settings_row: UserSettings,
) -> HorizonRecommendationResponse:
    """`_compute_horizon_recommendations()` 결과를 유저당 TTL_GOAL_RECOMMENDATION(1시간) 캐싱한다.

    최대 15개(투자기간×세제유형) 조합에 대해 후보 필터링(순차, 조합 간 상태 의존) 후 조합별
    SLSQP 최적화를 수행하는 무거운 계산이라 캐싱 효과가 크다. 계좌/스냅샷/포지션 DB 조회는
    조합마다 반복하지 않고 루프 진입 전 한 번만 수행한다(`prefetch_accounts_snapshot_positions`).
    무효화 조건은 `get_goal_recommendation`과 동일.

    조합 중 하나라도 `recommended_items`가 비어 있으면(예: 해외전용 조합만 Yahoo 서킷브레이커에
    걸려 시세 데이터를 못 가져온 경우) 응답 전체를 캐싱하지 않는다 — 15개 조합이 하나의 캐시
    키로 묶여 있어, 그대로 캐싱하면 일시적으로 실패한 조합 하나 때문에 나머지 정상 조합까지
    TTL 동안 통째로 그 실패 상태를 계속 반환하게 된다.

    콜드 캐시에서 동일 유저의 동시 요청은 `single_flight_fetch`로 한 건만 실제 계산한다 — 이
    경로는 최대 15콤보를 동시 실행하는 가장 무거운 계산이라 중복 실행을 막는 효과가 특히 크다.
    """
    cache_key = goal_recommendation_horizon_key(user_id)

    async def _read_cache() -> HorizonRecommendationResponse | None:
        cached = await get_cached_json(cache, cache_key)
        return HorizonRecommendationResponse(**cached) if cached is not None else None

    cached = await _read_cache()
    if cache is not None and cached is not None:
        return cached

    async def _fetch_and_cache() -> HorizonRecommendationResponse:
        result = await _compute_horizon_recommendations(cache, db, user_id, settings_row)
        if all(rec.recommended_items for rec in result.recommendations):
            await set_cached_json(cache, cache_key, result.model_dump(mode="json"), TTL_GOAL_RECOMMENDATION)
        return result

    if cache is None:
        return await _fetch_and_cache()

    return await single_flight_fetch(cache, cache_key, _read_cache, _fetch_and_cache)


async def _compute_horizon_recommendations(
    cache: CacheStoreType,
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
    cagr_lookback_years = int(
        getattr(settings_row, "goal_cagr_lookback_years", None) or _grc._DEFAULT_CAGR_LOOKBACK_YEARS
    )
    short_term_equity_floor_pct_raw = getattr(settings_row, "goal_short_term_equity_floor_pct", None)
    short_term_equity_floor = (
        float(short_term_equity_floor_pct_raw)
        if short_term_equity_floor_pct_raw is not None
        else _DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT
    ) / 100

    all_pos_map = await query_latest_position_map(user_id, db, include_name=True)
    existing_items = existing_items_from_positions(all_pos_map)
    candidate_dicts = await _get_or_seed_candidates(db, settings_row, existing_items)

    # 배당목표(annual_dividend_goal)가 있으면 전체 자산 기준(오버롤 경로)과 동일한 필요배당수익률(%)을
    # 계산해 모든 (기간,세제유형) 조합에 동일하게 적용한다 — 조합별 자산총액으로 비례배분해도 결과가
    # 같은 퍼센트로 나오므로(목표배당금 × 조합비중 ÷ 조합자산 = 목표배당금 ÷ 전체자산) 조합마다
    # 다시 계산할 필요가 없다.
    required_dividend_yield_pct: float | None = None
    annual_dividend_goal = getattr(settings_row, "annual_dividend_goal", None)
    if annual_dividend_goal:
        overall_overview = await build_portfolio_overview(user_id, db, account_ids=None, cache=cache)
        total_assets_krw = float(overall_overview.get("total_assets_krw", 0))
        if total_assets_krw > 0:
            required_dividend_yield_pct = round(float(annual_dividend_goal) / total_assets_krw * 100, 2)

    rows = (
        await db.execute(
            select(AssetAccount.investment_horizon, AssetAccount.tax_type, AssetAccount.id).where(
                AssetAccount.user_id == user_id,
                AssetAccount.is_active == True,
                AssetAccount.investment_horizon.isnot(None),
            )
        )
    ).all()
    accounts_by_pair: dict[tuple[str, str], list[uuid.UUID]] = {}
    for horizon_value, tax_type_value, account_id in rows:
        key = (horizon_value, tax_type_value or AccountTaxType.GENERAL.value)
        accounts_by_pair.setdefault(key, []).append(account_id)

    # 1단계: 후보 필터링(`candidate_dicts` 누적)은 조합 간 상태 의존(`_apply_index_region_preference`가
    # 앞선 조합에서 추가한 큐레이션 후보를 뒤따르는 조합의 capacity_remaining에 반영)이 있어 순차 계산이
    # 불가피하다. 다만 그 계산에 필요한 계좌/스냅샷/포지션 데이터는 조합마다 재조회(`build_portfolio_overview`
    # 재호출, 최대 15회 × 쿼리 3~4개)하지 않고 루프 진입 전에 관련 계좌 전체를 한 번만 조회해 재사용한다
    # (`prefetch_accounts_snapshot_positions` + `compute_total_assets_krw`).
    all_account_ids = [acc_id for ids in accounts_by_pair.values() for acc_id in ids]
    accounts_by_id, snap_by_acc, snap_pos_map, cur_pos_map = await prefetch_accounts_snapshot_positions(
        all_account_ids, db
    )

    combos: list[
        tuple[
            str,
            str,
            list[uuid.UUID],
            float,
            list[dict[str, str]],
            str | None,
            Callable[[dict[str, str]], bool],
        ]
    ] = []
    all_added: list[dict[str, str]] = []
    for horizon in InvestmentHorizon:
        for tax_type in AccountTaxType:
            account_ids = accounts_by_pair.get((horizon.value, tax_type.value))
            if not account_ids:
                continue

            combo_accounts = [accounts_by_id[acc_id] for acc_id in account_ids if acc_id in accounts_by_id]
            base_krw = compute_total_assets_krw(combo_accounts, snap_by_acc, snap_pos_map, cur_pos_map)

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
            duplicate_index_note = detect_duplicate_tracking_index_note(eligible_candidates, existing_items)
            preference_fallback_note = (
                f"{preference_fallback_note} {duplicate_index_note}"
                if preference_fallback_note and duplicate_index_note
                else preference_fallback_note or duplicate_index_note
            )

            def _market_filter(
                c: dict[str, str],
                market_group: str = market_group,
                eligible_classes: set[str] = eligible_classes,
                tax_type_value: str = tax_type.value,
            ) -> bool:
                return (
                    c.get("asset_class", "EQUITY") in eligible_classes
                    and (c["market"].upper() in DOMESTIC_MARKETS) == (market_group == "DOMESTIC")
                    and _matches_index_region_preference(c, tax_type_value)
                )

            combos.append(
                (
                    horizon.value,
                    tax_type.value,
                    account_ids,
                    base_krw,
                    eligible_candidates,
                    preference_fallback_note,
                    _market_filter,
                )
            )

    if all_added:
        await _persist_added_candidates(db, user_id, all_added)

    # 15개 조합이 동일한 시장 신호 스냅샷을 공유하도록 조합별 반복 조회 대신 한 번만 조회한다.
    market_signal_level = await _grc._fetch_market_signal_level(cache)

    # 2단계: DB에 의존하지 않는 외부 I/O(Yahoo/pykrx 수익률 조회 + SLSQP 최적화)는 조합 수(최대 15개)만큼
    # 동시 실행한다 — `_build_horizon_result`는 `db`를 사용하지 않으므로 AsyncSession 동시성 제약이 없다.
    results = await asyncio.gather(
        *(
            _build_horizon_result(
                cache,
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
                required_dividend_yield_pct=required_dividend_yield_pct,
            )
            for (
                horizon_value,
                tax_type_value,
                account_ids,
                base_krw,
                eligible_candidates,
                preference_fallback_note,
                _market_filter,
            ) in combos
        )
    )

    # 배당 제안 판정은 각 조합의 최적화 결과(`result.expected_dividend_yield_pct`)가 나온 뒤에야
    # 가능하므로 gather 이후에 수행한다 — 이미 달성한 조합에도 "더 나은 옵션" 제안이 필요할 수 있다
    # (`_suggest_for_dividend_goal` 참고). capacity는 전체 등록 후보 수(최종, 조합 간 공유) 기준.
    dividend_capacity_remaining = MAX_GOAL_CANDIDATE_TICKERS - len(candidate_dicts)
    for result, combo in zip(results, combos, strict=True):
        eligible_candidates = combo[4]
        market_filter = combo[6]
        suggested, dividend_note, dividend_goal_status = await _grc._suggest_for_dividend_goal(
            cache,
            eligible_candidates,
            required_dividend_yield_pct,
            result.expected_dividend_yield_pct,
            max_weight,
            capacity_remaining=dividend_capacity_remaining,
            market_filter=market_filter,
        )
        result.suggested_candidates = [SuggestedGoalCandidate(**s) for s in suggested]
        result.dividend_goal_status = dividend_goal_status
        if dividend_note:
            result.note = f"{result.note} {dividend_note}" if result.note else dividend_note

    return HorizonRecommendationResponse(
        generated_at=datetime.now(UTC).isoformat(),
        recommendations=list(results),
    )
