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
막지 않음). 투자기간별(`get_horizon_recommendations`)은 목표금액 역산을 하지 않는 별도 경로로
`goal_horizon_recommendation_service.py`에 분리되어 있으며, 배당 목표는 전체 자산 기준과 동일한
필요배당수익률(%)을 모든 (기간,세제유형) 조합에 동일 적용해 함께 반영한다.

전체 자산 기준 경로(`get_goal_recommendation`)는 자산목표(`goal_amount`+`retirement_target_year`)가
없어도 배당목표만 있으면 동작한다 — 이 경우 `required_return_pct`는 화면에 노출하지 않고(None),
옵티마이저에는 `by-horizon`/`by-age`와 동일한 `_NON_BINDING_RETURN_FLOOR`를 전달해 배당수익률
하한 제약만으로 최소분산 포트폴리오를 계산한다("배당 계획" 탭 전용 진입점).

`_suggest_for_dividend_goal()`은 "등록 후보로 달성 불가능할 때"뿐 아니라, 이미 달성한 경우에도
등록후보 밖에 유의미하게(`_DIVIDEND_IMPROVEMENT_THRESHOLD_PCT` 이상) 더 높은 배당수익률 후보가
있으면 "더 나은 옵션" 제안을 함께 반환한다(`dividend_goal_status`: unreachable/improvable/optimal).
이 판정은 최적화 실행 후 실제 산출된 `expected_dividend_yield_pct`를 기준으로 하므로, 세 호출부
모두 최적화 완료 후(또는 조기 반환 시 `expected_dividend_yield_pct=None`으로) 호출한다.

자동 반영되지 않음 — 프론트엔드에서 사용자가 확인 후 수동으로 포트폴리오 편집기에 적용한다.

MVO 최적화 엔진은 `goal_portfolio_optimizer.py`, 후보 종목 관리/영속화는 `goal_candidate_service.py`,
연령대별 추천(`get_age_based_recommendation`/`age_group_from_birth_year`)은
`goal_age_recommendation_service.py`, 투자기간별 추천(`get_horizon_recommendations`)은
`goal_horizon_recommendation_service.py`로 분리되어 있다. 세 진입점이 공유하는 헬퍼
(`_fetch_dividend_yields`/`_suggest_for_dividend_goal`/`_fetch_market_signal_level`/
`_equity_class_bounds`/`_cash_equivalent_daily_returns`/`_no_recommendation` + `_CASH_EQUIVALENT_*`
등 상수)는 `_goal_recommendation_common.py`가 소유하고 세 파일 모두 `_grc.fn()` 모듈 참조로 호출한다.
이 파일에는 전체 자산 기준 API 진입점 `get_goal_recommendation`(+ 적용 전 비교 미리보기
`compute_portfolio_expected_metrics`, 주간 알림용 `compute_recommendation_drift`)만 남는다.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AccountTaxType
from app.models.user import UserSettings
from app.schemas.rebalancing import (
    GoalRecommendation,
    PortfolioExpectedMetrics,
    SuggestedGoalCandidate,
)
from app.services import _goal_recommendation_common as _grc
from app.services.goal_candidate_service import (
    _active_account_tax_types,
    _apply_index_region_preference,
    _get_or_seed_candidates,
    _matches_index_region_preference,
    _persist_added_candidates,
    detect_duplicate_tracking_index_note,
)
from app.services.goal_portfolio_optimizer import (
    _MAX_WEIGHT,
    _MIN_CANDIDATES,
    _optimize_goal_portfolio,
    compute_weighted_expected_metrics,
)
from app.services.goal_return_solver import months_until_year_end, solve_required_annual_return_pct
from app.services.market_data_fetcher import fetch_yf_daily_returns
from app.services.price_service import get_historical_returns
from app.services.recommendation_universe import MAX_GOAL_CANDIDATE_TICKERS
from app.services.yahoo_price import _yfinance_sem, to_yf_symbol
from app.utils.cache_keys import (
    TTL_GOAL_RECOMMENDATION,
    CacheStoreType,
    get_cached_json,
    goal_recommendation_key,
    set_cached_json,
)
from app.utils.inproc_lock import single_flight_fetch

logger = structlog.get_logger()

_RECOMMENDATION_DRIFT_THRESHOLD_PCT = 3.0
"""`frontend/src/utils/recommendationDrift.ts`의 RECOMMENDATION_DRIFT_THRESHOLD_PCT와 동일하게
유지 — 프론트(화면을 열었을 때 배지)와 백엔드(주간 알림 job)가 같은 기준으로 "유의미한 변화"를
판단하게 하기 위함. 한쪽만 바꾸면 배지와 알림의 민감도가 어긋나므로 항상 함께 바꿀 것."""


def compute_recommendation_drift(
    recommended: list[tuple[str, str, float]],  # (ticker, market, weight 0~100)
    current: list[tuple[str, str, float]],
) -> tuple[float, int]:
    """`frontend/src/utils/recommendationDrift.ts`의 `computeRecommendationDrift()`와 동일한 로직을
    백엔드에 포팅한 것 — ticker+market 키로 매칭해 (최대 비중차이%p, 신규후보개수)를 반환한다.
    "유의미한 변화" 판정(`_RECOMMENDATION_DRIFT_THRESHOLD_PCT` 이상 또는 신규후보 존재)은
    호출측(`recommendation_drift_alert_service.py`)이 담당한다.
    """
    current_by_key = {(t, m): w for t, m, w in current}
    max_delta_pct = 0.0
    new_candidate_count = 0
    for t, m, w in recommended:
        current_weight = current_by_key.get((t, m))
        if current_weight is None:
            new_candidate_count += 1
            continue
        max_delta_pct = max(max_delta_pct, abs(w - current_weight))
    return round(max_delta_pct, 1), new_candidate_count


async def get_goal_recommendation(
    cache: CacheStoreType,
    base_krw: float,
    existing_items: list[tuple[str, str, str]],
    settings_row: UserSettings | None,
    db: AsyncSession,
) -> GoalRecommendation:
    """`_compute_goal_recommendation()` 결과를 유저당 TTL_GOAL_RECOMMENDATION(1시간) 캐싱한다.

    계산 자체가 CAGR/배당수익률 외부 조회 + SLSQP 최적화를 포함해 무겁고, 진단탭 마운트 시
    무조건 호출되므로 짧은 TTL로도 체감 속도 개선 효과가 크다. 목표 설정·후보 ETF 변경,
    계좌 sync(포지션 변경) 시 `invalidate_goal_recommendation_caches()`/`invalidate_account_caches()`가
    캐시를 무효화한다 — 그 외의 사소한 자산평가액 변동은 TTL 만료까지 반영되지 않는다(허용된 트레이드오프).

    `recommended_items`가 비어 있는 결과(목표 미설정·달성불가·후보부족·Yahoo 서킷브레이커 등으로
    시세 데이터 조회 실패 등)는 캐싱하지 않는다 — 이런 실패는 대부분 일시적 외부 API 장애이며,
    캐싱하면 다음 요청부터 서킷브레이커가 복구된 뒤에도 TTL 동안 계속 같은 실패를 반환하게 된다.

    콜드 캐시(TTL 만료·재배포 직후)에서 동일 유저의 요청이 동시에 여러 건 들어오면(다중 기기/탭,
    axios 타임아웃 후 재시도 등) `single_flight_fetch`로 한 건만 실제 계산하고 나머지는 그 결과를
    기다린다 — 안 그러면 무거운 SLSQP+외부API 계산이 동시에 중복 실행되어 서로의 응답을 더 늦춘다.
    """
    user_id = getattr(settings_row, "user_id", None)

    async def _fetch_and_cache() -> GoalRecommendation:
        result = await _compute_goal_recommendation(cache, base_krw, existing_items, settings_row, db)
        if user_id is not None and result.recommended_items:
            await set_cached_json(
                cache, goal_recommendation_key(user_id), result.model_dump(mode="json"), TTL_GOAL_RECOMMENDATION
            )
        return result

    if user_id is None:
        return await _fetch_and_cache()

    cache_key = goal_recommendation_key(user_id)

    async def _read_cache() -> GoalRecommendation | None:
        cached = await get_cached_json(cache, cache_key)
        return GoalRecommendation(**cached) if cached is not None else None

    cached = await _read_cache()
    if cache is not None and cached is not None:
        return cached

    if cache is None:
        return await _fetch_and_cache()

    return await single_flight_fetch(cache, cache_key, _read_cache, _fetch_and_cache)


def _resolve_asset_goal_return_pct(
    settings_row: UserSettings,
    pv: float,
    required_dividend_yield_pct: float | None,
) -> tuple[float | None, GoalRecommendation | None]:
    """자산목표(`goal_amount`+`retirement_target_year`)를 필요 연평균 수익률로 역산한다.

    반환값: (`required_return_pct`, 조기 반환할 결과가 있으면 그 `GoalRecommendation`, 없으면 None).
    `_compute_goal_recommendation()`의 분기 복잡도를 낮추기 위해 분리했다. 호출측이 `has_asset_goal`
    (goal_amount·retirement_target_year 둘 다 설정됨)을 이미 확인했다고 전제한다.
    """
    if settings_row.goal_amount is None or settings_row.retirement_target_year is None:
        raise ValueError("_resolve_asset_goal_return_pct는 has_asset_goal 확인 후에만 호출해야 합니다")
    pmt = float(settings_row.monthly_deposit_amount or 0)
    if not pmt and settings_row.annual_deposit_goal:
        pmt = float(settings_row.annual_deposit_goal) / 12
    goal_amount = float(settings_row.goal_amount)
    target_year = int(settings_row.retirement_target_year)
    n_months = months_until_year_end(target_year)

    if n_months <= 0:
        return None, _grc._no_recommendation("목표 연도가 이미 지났습니다 — 목표연도를 다시 설정해주세요")
    if pv >= goal_amount:
        return None, _grc._no_recommendation(
            "이미 목표 금액을 달성했습니다", required_dividend_yield_pct=required_dividend_yield_pct
        )

    required_return_pct = solve_required_annual_return_pct(pv, pmt, n_months, goal_amount)
    if required_return_pct is None:
        return None, _grc._no_recommendation(
            "현재 조건(적립액·기간)으로는 달성이 매우 어려운 목표입니다",
            required_dividend_yield_pct=required_dividend_yield_pct,
        )
    return required_return_pct, None


async def _apply_tax_type_preference_for_overall(
    db: AsyncSession,
    candidate_dicts: list[dict[str, str]],
    user_id: uuid.UUID | None,
) -> tuple[list[dict[str, str]], str | None, str | None]:
    """활성 계좌가 전부 단일 세제유형일 때만 추종지수 지역 선호 필터를 적용한다(전체 자산 기준 경로 전용).

    반환값: (필터링된 후보, fallback 안내 note, 단일 세제유형 값(있으면, `overall_market_filter`용)).
    `_compute_goal_recommendation()`의 분기 복잡도를 낮추기 위해 분리했다.
    """
    if user_id is None:
        return candidate_dicts, None, None
    tax_type_rows = await _active_account_tax_types(db, user_id)
    distinct_tax_types = {t or AccountTaxType.GENERAL.value for t in tax_type_rows}
    if len(distinct_tax_types) != 1:
        return candidate_dicts, None, None
    single_tax_type = next(iter(distinct_tax_types))
    capacity_remaining = MAX_GOAL_CANDIDATE_TICKERS - len(candidate_dicts)
    computed_candidates, preference_fallback_note, added = _apply_index_region_preference(
        candidate_dicts, single_tax_type, capacity_remaining
    )
    if added:
        await _persist_added_candidates(db, user_id, added)
    return computed_candidates, preference_fallback_note, single_tax_type


async def _fetch_overall_candidate_data(
    cache: CacheStoreType,
    tickers_only: list[tuple[str, str]],
    cagr_lookback_years: int,
) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], float], str | None]:
    """전체 자산 기준 추천용 CAGR·배당수익률·시장신호를 병렬 조회한다."""
    return await asyncio.gather(
        get_historical_returns(tickers_only, cache=cache, years=cagr_lookback_years),
        _grc._fetch_dividend_yields(cache, tickers_only),
        _grc._fetch_market_signal_level(cache),
    )


def _filter_candidates_with_cagr(
    candidates: list[tuple[str, str, str, str]],
    cagr_map: dict[tuple[str, str], dict],
    dividend_map: dict[tuple[str, str], float],
) -> list[tuple[str, tuple[str, str, str], float, float, str]]:
    """CAGR 데이터가 확보된 후보만 남기고, yfinance 심볼·배당수익률·자산군을 함께 묶는다."""
    return [
        (to_yf_symbol(t, m), (t, name, m), cagr_map[(t, m)]["cagr_pct"], dividend_map.get((t, m), 0.0), asset_class)
        for t, name, m, asset_class in candidates
        if (t, m) in cagr_map and cagr_map[(t, m)].get("cagr_pct") is not None
    ]


def _compute_overall_class_bounds(settings_row: UserSettings | None) -> dict[str, tuple[float, float]] | None:
    """전체 자산 기준 추천(`get_goal_recommendation`) 전용 — 사용자가 설정한 채권/현금성 비중
    상한(`goal_bond_ceiling_pct`/`goal_cash_ceiling_pct`, %)을 `_optimize_goal_portfolio`의
    `class_bounds`(자산군별 (하한, 상한) 비율, 0~1)로 변환한다. 상한이 없으면(None) 해당
    자산군은 제약에서 제외 — 상한을 하나도 설정하지 않았으면 전체가 None(기존 동작과 동일하게
    자산군 제약 없이 계산).

    두 상한을 동시에 설정하면(예: 채권 30%↓ + 현금성 20%↓) `_optimize_goal_portfolio`가
    총합=1 제약으로부터 "주식 비중 ≥ 1-채권상한-현금성상한"(여기서는 50%)이라는 묵시적
    하한을 자동으로 유도한다 — EQUITY에 대해 별도 하한을 명시할 필요가 없다.
    """
    bond_ceiling_pct = getattr(settings_row, "goal_bond_ceiling_pct", None)
    cash_ceiling_pct = getattr(settings_row, "goal_cash_ceiling_pct", None)
    class_bounds: dict[str, tuple[float, float]] = {}
    if bond_ceiling_pct is not None:
        class_bounds["BOND"] = (0.0, float(bond_ceiling_pct) / 100)
    if cash_ceiling_pct is not None:
        class_bounds["CASH"] = (0.0, float(cash_ceiling_pct) / 100)
    return class_bounds or None


async def _compute_goal_recommendation(
    cache: CacheStoreType,
    base_krw: float,
    existing_items: list[tuple[str, str, str]],
    settings_row: UserSettings | None,
    db: AsyncSession,
) -> GoalRecommendation:
    """기준 자산총액과 유저 목표(자산목표 또는 배당목표)를 받아 목표 역산 추천을 계산한다.

    자산목표(`goal_amount`+`retirement_target_year`)가 없어도 배당목표(`annual_dividend_goal`)만
    있으면 동작한다 — 이 경우 `required_return_pct`는 None(화면 미노출)이고, 옵티마이저에는
    `_NON_BINDING_RETURN_FLOOR`를 전달해 배당수익률 하한 제약만으로 최소분산 포트폴리오를 계산한다.
    """
    has_asset_goal = bool(settings_row and settings_row.goal_amount and settings_row.retirement_target_year)
    has_dividend_goal = bool(settings_row and settings_row.annual_dividend_goal)
    if not settings_row or not (has_asset_goal or has_dividend_goal):
        return _grc._not_configured("목표금액·목표연도 또는 배당목표를 설정하면 추천을 받을 수 있습니다")

    pv = base_krw
    required_dividend_yield_pct = (
        round(float(settings_row.annual_dividend_goal) / pv * 100, 2)
        if settings_row.annual_dividend_goal and pv > 0
        else None
    )

    required_return_pct: float | None = None
    required_return_pct_for_optimizer = _grc._NON_BINDING_RETURN_FLOOR
    if has_asset_goal:
        required_return_pct, early_result = _resolve_asset_goal_return_pct(
            settings_row, pv, required_dividend_yield_pct
        )
        if early_result is not None:
            return early_result
        assert required_return_pct is not None  # nosec B101 - early_result is None이면 항상 값이 있음
        required_return_pct_for_optimizer = required_return_pct

    candidate_dicts = await _get_or_seed_candidates(db, settings_row, existing_items)

    if not candidate_dicts:
        return _grc._no_recommendation(
            "등록된 후보 종목이 없습니다 — 후보 ETF를 추가해주세요",
            required_return_pct,
            required_dividend_yield_pct,
        )

    user_id = getattr(settings_row, "user_id", None)
    computed_candidates, preference_fallback_note, single_tax_type = await _apply_tax_type_preference_for_overall(
        db, candidate_dicts, user_id
    )
    duplicate_index_note = detect_duplicate_tracking_index_note(computed_candidates, existing_items)
    preference_fallback_note = (
        f"{preference_fallback_note} {duplicate_index_note}"
        if preference_fallback_note and duplicate_index_note
        else preference_fallback_note or duplicate_index_note
    )

    def _combine_note(msg: str | None) -> str | None:
        if preference_fallback_note and msg:
            return f"{preference_fallback_note} {msg}"
        return preference_fallback_note or msg

    risk_tolerance = getattr(settings_row, "goal_risk_tolerance", None) or "CONSERVATIVE"
    max_weight_pct_raw = getattr(settings_row, "goal_max_weight_pct", None)
    max_weight = float(max_weight_pct_raw) / 100 if max_weight_pct_raw else _MAX_WEIGHT
    cagr_lookback_years = int(
        getattr(settings_row, "goal_cagr_lookback_years", None) or _grc._DEFAULT_CAGR_LOOKBACK_YEARS
    )

    overall_market_filter = (
        (lambda c, tax_type_value=single_tax_type: _matches_index_region_preference(c, tax_type_value))
        if single_tax_type is not None
        else None
    )
    dividend_capacity_remaining = MAX_GOAL_CANDIDATE_TICKERS - len(candidate_dicts)

    async def _suggest_dividend_candidates(
        expected_dividend_yield_pct: float | None,
    ) -> tuple[list[dict[str, object]], str | None, str | None]:
        if user_id is None:
            return [], None, None
        return await _grc._suggest_for_dividend_goal(
            cache,
            computed_candidates,
            required_dividend_yield_pct,
            expected_dividend_yield_pct,
            max_weight,
            capacity_remaining=dividend_capacity_remaining,
            market_filter=overall_market_filter,
        )

    candidates = [(c["ticker"], c["name"], c["market"], c.get("asset_class", "EQUITY")) for c in computed_candidates]
    tickers_only = [(t, m) for t, _, m, _ in candidates]

    cagr_map, dividend_map, market_signal_level = await _fetch_overall_candidate_data(
        cache, tickers_only, cagr_lookback_years
    )
    filtered = _filter_candidates_with_cagr(candidates, cagr_map, dividend_map)
    if len(filtered) < _MIN_CANDIDATES:
        suggested_candidates, dividend_note, dividend_goal_status = await _suggest_dividend_candidates(None)
        result = _grc._no_recommendation(
            "추천에 필요한 수익률 데이터를 가져오지 못했습니다",
            required_return_pct,
            required_dividend_yield_pct,
        )
        result.note = _combine_note(result.note)
        if dividend_note:
            result.note = f"{result.note} {dividend_note}" if result.note else dividend_note
        result.suggested_candidates = [SuggestedGoalCandidate(**s) for s in suggested_candidates]
        result.dividend_goal_status = dividend_goal_status
        return result

    f_symbols = [f[0] for f in filtered]
    f_tickers = [f[1] for f in filtered]
    f_cagrs = [f[2] for f in filtered]
    f_dividends = [f[3] for f in filtered]
    f_asset_classes = [f[4] for f in filtered]

    loop = asyncio.get_running_loop()
    async with _yfinance_sem:
        returns_map = await loop.run_in_executor(None, fetch_yf_daily_returns, f_symbols)
    items, expected_return_pct, expected_volatility_pct, opt_note = await loop.run_in_executor(
        None,
        functools.partial(
            _optimize_goal_portfolio,
            f_symbols,
            f_tickers,
            f_cagrs,
            returns_map,
            required_return_pct_for_optimizer,
            max_weight=max_weight,
            risk_tolerance=risk_tolerance,
            asset_classes=f_asset_classes,
            class_bounds=_compute_overall_class_bounds(settings_row),
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

    suggested_candidates, dividend_note, dividend_goal_status = await _suggest_dividend_candidates(
        expected_dividend_yield_pct
    )
    note = _combine_note(opt_note)
    if dividend_note:
        note = f"{note} {dividend_note}" if note else dividend_note

    return GoalRecommendation(
        generated_at=datetime.now(UTC).isoformat(),
        is_configured=True,
        required_return_pct=required_return_pct,
        required_dividend_yield_pct=required_dividend_yield_pct,
        recommended_items=_grc._attach_dividend_yield(items, dividend_map),
        expected_return_pct=expected_return_pct,
        expected_dividend_yield_pct=expected_dividend_yield_pct,
        expected_volatility_pct=expected_volatility_pct,
        note=note,
        cagr_lookback_years=cagr_lookback_years,
        risk_tolerance=risk_tolerance,
        max_weight_pct=round(max_weight * 100, 2),
        market_signal_level=market_signal_level,
        suggested_candidates=[SuggestedGoalCandidate(**s) for s in suggested_candidates],
        dividend_goal_status=dividend_goal_status,
    )


async def compute_portfolio_expected_metrics(
    cache: CacheStoreType,
    items: list[tuple[str, str, str, float]],  # (ticker, market, name, weight 0~100)
    cagr_lookback_years: int = _grc._DEFAULT_CAGR_LOOKBACK_YEARS,
) -> PortfolioExpectedMetrics:
    """포트폴리오의 현재 목표 비중(`Portfolio.items`, CASH/부동산 등 시세 없는 항목은 호출측이 미리
    제외)에 대해 추천 비중과 동일한 지표(기대수익률/배당수익률/변동성)를 계산한다 — "적용 전 비교
    미리보기"에서 추천 비중의 같은 지표와 나란히 보여주기 위함. 최적화(SLSQP)하지 않고 주어진
    비중 그대로 가중평균/공분산만 계산한다(`goal_portfolio_optimizer.compute_weighted_expected_metrics`).
    """
    if not items:
        return PortfolioExpectedMetrics()

    tickers_only = [(ticker, market) for ticker, market, _name, _w in items]
    cagr_map, dividend_map = await asyncio.gather(
        get_historical_returns(tickers_only, cache=cache, years=cagr_lookback_years),
        _grc._fetch_dividend_yields(cache, tickers_only),
    )

    symbols = [to_yf_symbol(ticker, market) for ticker, market, _name, _w in items]
    weights_pct = [w for *_, w in items]
    cagr_by_symbol = {
        to_yf_symbol(t, m): cagr_map[(t, m)]["cagr_pct"]
        for t, m in tickers_only
        if (t, m) in cagr_map and cagr_map[(t, m)].get("cagr_pct") is not None
    }
    dividend_by_symbol = {to_yf_symbol(t, m): dividend_map.get((t, m), 0.0) for t, m in tickers_only}

    loop = asyncio.get_running_loop()
    async with _yfinance_sem:
        returns_map = await loop.run_in_executor(None, fetch_yf_daily_returns, symbols)

    expected_return_pct, expected_dividend_yield_pct, expected_volatility_pct = compute_weighted_expected_metrics(
        symbols, weights_pct, cagr_by_symbol, dividend_by_symbol, returns_map
    )
    return PortfolioExpectedMetrics(
        expected_return_pct=expected_return_pct,
        expected_dividend_yield_pct=expected_dividend_yield_pct or None,
        expected_volatility_pct=expected_volatility_pct,
    )
