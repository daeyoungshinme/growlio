"""연령대별 목표 역산 추천 — `goal_recommendation_service.py` 서브모듈 (기술부채 정리, 2026-08-13).

`UserSettings.age_group`(사용자가 직접 선택한 20대/30대/40대/50대/60대 이상 연령대)에 따라,
목표금액 역산 없이 연령대에 맞는 리스크 성향 + 주식비중 상/하한만으로 추천 비중을 계산한다 —
목표 역산을 하지 않는다는 점에서 `get_horizon_recommendations`(투자기간별)와 성격이 같다
(`_NON_BINDING_RETURN_FLOOR`로 required_return_pct 제약을 사실상 무효화한다).

원래 `goal_recommendation_service.py`(1622줄)에 있던 것을 2026-08-13 기술부채 정리에서 분리했다
— `goal_portfolio_optimizer.py`/`goal_candidate_service.py`와 동일한 서브모듈 패턴. 후보 조회·
CAGR/배당수익률 조회·MVO 최적화·배당목표 후보제안 등 공유 헬퍼는 여전히 `goal_recommendation_service.py`
에 남아 있고 이 모듈이 import해서 사용한다(역방향 의존 없음 — `goal_recommendation_service.py`는
이 모듈을 import하지 않는다).
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AgeGroup
from app.models.user import UserSettings
from app.schemas.rebalancing import GoalRecommendation, SuggestedGoalCandidate
from app.services.goal_candidate_service import (
    _get_or_seed_candidates,
    detect_duplicate_tracking_index_note,
    existing_items_from_positions,
)
from app.services.goal_portfolio_optimizer import _MAX_WEIGHT, _MIN_CANDIDATES, _optimize_goal_portfolio
from app.services.goal_recommendation_service import (
    _CASH_EQUIVALENT_CAGR_PCT,
    _CASH_EQUIVALENT_MARKET,
    _CASH_EQUIVALENT_NAME,
    _CASH_EQUIVALENT_TICKER,
    _DEFAULT_CAGR_LOOKBACK_YEARS,
    _NON_BINDING_RETURN_FLOOR,
    _attach_dividend_yield,
    _cash_equivalent_daily_returns,
    _equity_class_bounds,
    _fetch_dividend_yields,
    _fetch_market_signal_level,
    _no_recommendation,
    _not_configured,
    _suggest_for_dividend_goal,
)
from app.services.market_data_fetcher import fetch_yf_daily_returns
from app.services.portfolio_service import build_portfolio_overview
from app.services.position_aggregator import query_latest_position_map
from app.services.price_service import get_historical_returns
from app.services.recommendation_universe import MAX_GOAL_CANDIDATE_TICKERS
from app.services.yahoo_price import _yfinance_sem, to_yf_symbol
from app.utils.cache_keys import (
    TTL_GOAL_RECOMMENDATION,
    CacheStoreType,
    get_cached_json,
    goal_recommendation_age_key,
    set_cached_json,
)
from app.utils.inproc_lock import single_flight_fetch

_AGE_GROUP_PROFILE: dict[str, tuple[str, str, float | None, float | None, float]] = {
    # age_group → (구간 라벨, risk_tolerance, equity_floor, equity_ceiling, 기본 배당수익률 하한%)
    AgeGroup.TWENTIES.value: ("20대", "AGGRESSIVE", 0.8, None, 0.0),
    AgeGroup.THIRTIES.value: ("30대", "AGGRESSIVE", 0.7, None, 0.0),
    AgeGroup.FORTIES.value: ("40대", "BALANCED", 0.55, None, 1.5),
    AgeGroup.FIFTIES.value: ("50대", "BALANCED", None, 0.6, 2.5),
    AgeGroup.SIXTIES_PLUS.value: ("60대 이상", "CONSERVATIVE", None, 0.35, 3.5),
}
"""연령대(`UserSettings.age_group`, 사용자가 직접 선택) → (risk_tolerance, 주식비중 상/하한,
기본 배당수익률 하한%) 매핑 — "나이가 많을수록 안전자산 비중을 늘리고 배당(현금흐름) 안정성에
초점을 둔다"는 생애주기 투자 통념을 이 엔진의 축(risk_tolerance/equity_floor·ceiling/배당수익률
하한)에 얹은 것. 구간마다 `equity_floor`/`equity_ceiling` 중 하나만 설정한다 —
`_optimize_goal_portfolio`는 호출측이 둘을 동시에 넘기지 않는다고 전제한다
(goal_portfolio_optimizer.py의 해당 docstring 참고, bounds 계산이 `elif`로 분기돼 있어 동시 사용
시 제약 간 불일치가 생길 수 있음).

기본 배당수익률 하한은 `UserSettings.annual_dividend_goal`(명시적 배당목표)이 설정돼 있지
않을 때만 적용되는 폴백 값이다(`_compute_age_based_recommendation` 참고) — 명시적 목표가
있으면 그 값이 항상 우선한다. 20~30대는 0(배당 제약 없음, 성장 중심 기존 동작 유지), 40대부터
점진적으로 상향한다. 다른 age_group 값과 마찬가지로 튜닝 가능한 휴리스틱 기본값이며 특정
종목 투자를 권유하는 것은 아니다.

BALANCED/AGGRESSIVE(20~40대)는 프론티어 보간을 위한 등식 제약(목표 수익률 고정)이 추가로 걸리는데,
등록된 주식(EQUITY) 후보 수가 너무 적으면(예: 1~2개) equity_floor 하한과 이 등식 제약이 동시에
정확히 한 점만 허용해 옵티마이저가 해를 못 찾을 수 있다(SLSQP 실패 → "제약 조건을 만족하는
포트폴리오를 찾지 못했습니다" note로 fail-soft 반환). 큐레이션 유니버스는 항상 다수의 EQUITY
후보를 포함하므로 실사용에서는 드문 경우지만, 후보 ETF를 극소수만 등록한 사용자는 겪을 수 있다 —
이미 IRP+LONG_TERM(AGGRESSIVE) 조합에서도 존재하는 동일한 구조적 한계이며 이 엔진의 알려진
트레이드오프다."""


def age_group_from_birth_year(birth_year: int) -> AgeGroup:
    """출생연도로부터 `_AGE_GROUP_PROFILE` 조회에 쓰이는 10년 단위 연령대를 파생한다.

    온보딩에서 사용자가 실제 나이(출생연도)를 입력하면 이 함수로 기존 `age_group` 버킷에
    매핑해 저장한다 — `get_age_based_recommendation` 등 기존 연령대 기반 로직을 그대로 재사용하기
    위함(신규 계산 경로를 만들지 않음). 20세 미만은 TWENTIES로, 60세 이상은 SIXTIES_PLUS로 clamp한다.
    """
    age = datetime.now(UTC).year - birth_year
    if age < 30:
        return AgeGroup.TWENTIES
    if age < 40:
        return AgeGroup.THIRTIES
    if age < 50:
        return AgeGroup.FORTIES
    if age < 60:
        return AgeGroup.FIFTIES
    return AgeGroup.SIXTIES_PLUS


async def get_age_based_recommendation(
    cache: CacheStoreType,
    db: AsyncSession,
    user_id: uuid.UUID,
    settings_row: UserSettings,
) -> GoalRecommendation:
    """`_compute_age_based_recommendation()` 결과를 유저당 TTL_GOAL_RECOMMENDATION(1시간) 캐싱한다.

    무효화 조건은 `get_goal_recommendation`/`get_horizon_recommendations`와 동일 —
    `invalidate_goal_recommendation_caches()`가 `age_group` 변경(설정 저장) 시에도 함께 호출된다.
    콜드 캐시에서 동일 유저의 동시 요청은 `single_flight_fetch`로 한 건만 실제 계산한다.
    """
    cache_key = goal_recommendation_age_key(user_id)

    async def _read_cache() -> GoalRecommendation | None:
        cached = await get_cached_json(cache, cache_key)
        return GoalRecommendation(**cached) if cached is not None else None

    cached = await _read_cache()
    if cache is not None and cached is not None:
        return cached

    async def _fetch_and_cache() -> GoalRecommendation:
        result = await _compute_age_based_recommendation(cache, db, user_id, settings_row)
        if result.recommended_items:
            await set_cached_json(cache, cache_key, result.model_dump(mode="json"), TTL_GOAL_RECOMMENDATION)
        return result

    if cache is None:
        return await _fetch_and_cache()

    return await single_flight_fetch(cache, cache_key, _read_cache, _fetch_and_cache)


async def _compute_age_based_recommendation(
    cache: CacheStoreType,
    db: AsyncSession,
    user_id: uuid.UUID,
    settings_row: UserSettings,
) -> GoalRecommendation:
    """사용자가 직접 선택한 연령대(`UserSettings.age_group`) 기반 추천 — 목표금액 역산 없이
    연령대(`_AGE_GROUP_PROFILE`)에서 유도한 risk_tolerance + 주식비중 상/하한으로 비중을
    계산한다. 후보 필터링·현금성 자산 fallback 로직은 `_build_horizon_result`의 SHORT_TERM
    분기와 동일한 이유로 동일하게 동작한다(실보유 안전자산 후보가 하나도 없는데 `equity_floor`
    구간이면 합성 현금성 자산으로 채움).

    배당수익률 제약(`required_dividend_yield_pct`)도 함께 반영한다 — `UserSettings.annual_dividend_goal`이
    설정돼 있으면 그 값을(전체 자산 기준 경로와 동일한 방식으로) 우선 사용하고, 없으면
    `_AGE_GROUP_PROFILE`의 연령대 기본 배당수익률 하한을 폴백으로 적용한다(20~30대는 0이라
    사실상 미적용). 옵티마이저가 fail-soft로 처리하므로 큐레이션 후보로 달성 불가능하면
    조용히 무시되고 note로만 안내된다.
    """
    if not settings_row.age_group or settings_row.age_group not in _AGE_GROUP_PROFILE:
        return _not_configured("연령대를 설정하면 연령대별 추천을 받을 수 있습니다")

    age_bracket, risk_tolerance, equity_floor, equity_ceiling, default_dividend_floor_pct = _AGE_GROUP_PROFILE[
        settings_row.age_group
    ]

    # 명시적 배당목표(annual_dividend_goal)가 있으면 그 값을 우선 반영하고, 없을 때만 연령대
    # 기본 배당수익률 하한(_AGE_GROUP_PROFILE)을 폴백으로 적용한다 — 전체 자산 기준 경로
    # (_compute_horizon_recommendations)와 동일한 annual_dividend_goal → 필요배당수익률 변환 패턴.
    required_dividend_yield_pct: float | None = None
    age_default_dividend_note: str | None = None
    annual_dividend_goal = getattr(settings_row, "annual_dividend_goal", None)
    if annual_dividend_goal:
        overall_overview = await build_portfolio_overview(user_id, db, account_ids=None, cache=cache)
        total_assets_krw = float(overall_overview.get("total_assets_krw", 0))
        if total_assets_krw > 0:
            required_dividend_yield_pct = round(float(annual_dividend_goal) / total_assets_krw * 100, 2)
    if required_dividend_yield_pct is None and default_dividend_floor_pct > 0:
        required_dividend_yield_pct = default_dividend_floor_pct
        age_default_dividend_note = (
            f"{age_bracket} 연령대 기본 배당목표(연 {default_dividend_floor_pct:.1f}%↑)를 반영했습니다"
        )

    max_weight_pct_raw = getattr(settings_row, "goal_max_weight_pct", None)
    max_weight = float(max_weight_pct_raw) / 100 if max_weight_pct_raw else _MAX_WEIGHT
    cagr_lookback_years = int(getattr(settings_row, "goal_cagr_lookback_years", None) or _DEFAULT_CAGR_LOOKBACK_YEARS)

    all_pos_map = await query_latest_position_map(user_id, db, include_name=True)
    existing_items = existing_items_from_positions(all_pos_map)
    candidate_dicts = await _get_or_seed_candidates(db, settings_row, existing_items)
    dividend_capacity_remaining = MAX_GOAL_CANDIDATE_TICKERS - len(candidate_dicts)
    duplicate_index_note = detect_duplicate_tracking_index_note(candidate_dicts, existing_items)

    def _combine_age_note(msg: str | None) -> str | None:
        if duplicate_index_note and msg:
            return f"{duplicate_index_note} {msg}"
        return duplicate_index_note or msg

    async def _with_bracket(res: GoalRecommendation, expected_dividend_yield_pct: float | None) -> GoalRecommendation:
        """배당 제안 판정은 최적화 결과(`expected_dividend_yield_pct`)가 필요하므로 각 반환 지점에서
        호출한다 — 조기 반환 지점은 `None`(미최적화)을 넘긴다."""
        res.age_bracket = age_bracket
        suggested, dividend_note, dividend_goal_status = await _suggest_for_dividend_goal(
            cache,
            candidate_dicts,
            required_dividend_yield_pct,
            expected_dividend_yield_pct,
            max_weight,
            capacity_remaining=dividend_capacity_remaining,
        )
        res.suggested_candidates = [SuggestedGoalCandidate(**s) for s in suggested]
        res.dividend_goal_status = dividend_goal_status
        if dividend_note:
            res.note = f"{res.note} {dividend_note}" if res.note else dividend_note
        return res

    if not candidate_dicts:
        return await _with_bracket(
            _no_recommendation(
                "등록된 후보 종목이 없습니다 — 후보 ETF를 추가해주세요",
                required_dividend_yield_pct=required_dividend_yield_pct,
            ),
            None,
        )

    market_signal_level = await _fetch_market_signal_level(cache)

    candidates = [(c["ticker"], c["name"], c["market"], c.get("asset_class", "EQUITY")) for c in candidate_dicts]
    tickers_only = [(t, m) for t, _, m, _ in candidates]

    cagr_map, dividend_map = await asyncio.gather(
        get_historical_returns(tickers_only, cache=cache, years=cagr_lookback_years),
        _fetch_dividend_yields(cache, tickers_only),
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
    include_cash_equivalent = equity_floor is not None and not has_real_safe_asset
    if include_cash_equivalent:
        filtered.append(
            (
                _CASH_EQUIVALENT_TICKER,
                (_CASH_EQUIVALENT_TICKER, _CASH_EQUIVALENT_NAME, _CASH_EQUIVALENT_MARKET),
                _CASH_EQUIVALENT_CAGR_PCT,
                False,
                0.0,
            )
        )

    if len(filtered) < _MIN_CANDIDATES:
        no_data_result = _no_recommendation(
            "추천에 필요한 수익률 데이터를 가져오지 못했습니다",
            required_dividend_yield_pct=required_dividend_yield_pct,
        )
        no_data_result.note = _combine_age_note(no_data_result.note)
        return await _with_bracket(no_data_result, None)

    f_symbols = [f[0] for f in filtered]
    f_tickers = [f[1] for f in filtered]
    f_cagrs = [f[2] for f in filtered]
    f_is_equity = [f[3] for f in filtered]
    f_asset_classes = ["EQUITY" if is_eq else "OTHER" for is_eq in f_is_equity]
    f_dividends = [f[4] for f in filtered]

    loop = asyncio.get_running_loop()
    real_symbols = [s for s in f_symbols if s != _CASH_EQUIVALENT_TICKER]
    if real_symbols:
        async with _yfinance_sem:
            returns_map = await loop.run_in_executor(None, fetch_yf_daily_returns, real_symbols)
    else:
        returns_map = {}
    if include_cash_equivalent:
        returns_map[_CASH_EQUIVALENT_TICKER] = _cash_equivalent_daily_returns()

    # `_AGE_GROUP_PROFILE`은 구간마다 equity_floor/equity_ceiling 중 하나만 설정한다(docstring 참고).
    class_bounds = _equity_class_bounds(equity_floor, equity_ceiling)

    items, expected_return_pct, expected_volatility_pct, opt_note = await loop.run_in_executor(
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
            asset_classes=f_asset_classes,
            class_bounds=class_bounds,
            market_signal_level=market_signal_level,
            dividend_yields=f_dividends,
            required_dividend_yield_pct=required_dividend_yield_pct,
        ),
    )

    includes_cash_equivalent = any(i["ticker"] == _CASH_EQUIVALENT_TICKER for i in items)
    expected_dividend_yield_pct = None
    if items:
        expected_dividend_yield_pct = round(
            sum(i["weight"] * dividend_map.get((i["ticker"], i["market"]), 0.0) for i in items) / 100, 2
        )

    # age_default_dividend_note(명시적 목표가 아닌 연령대 기본값을 적용한 경우에만 존재)는
    # opt_note(옵티마이저의 배당 목표 달성 불가 fail-soft 안내)보다 앞에 붙인다.
    note = (
        f"{age_default_dividend_note} {opt_note}"
        if age_default_dividend_note and opt_note
        else (age_default_dividend_note or opt_note)
    )
    note = _combine_age_note(note)

    return await _with_bracket(
        GoalRecommendation(
            generated_at=datetime.now(UTC).isoformat(),
            is_configured=True,
            required_dividend_yield_pct=required_dividend_yield_pct,
            recommended_items=_attach_dividend_yield(items, dividend_map),
            expected_return_pct=expected_return_pct,
            expected_dividend_yield_pct=expected_dividend_yield_pct,
            expected_volatility_pct=expected_volatility_pct,
            note=note,
            cagr_lookback_years=cagr_lookback_years,
            risk_tolerance=risk_tolerance,
            max_weight_pct=round(max_weight * 100, 2),
            market_signal_level=market_signal_level,
            includes_cash_equivalent=includes_cash_equivalent,
        ),
        expected_dividend_yield_pct,
    )
