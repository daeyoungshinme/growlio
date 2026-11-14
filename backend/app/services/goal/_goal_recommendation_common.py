"""목표 역산 추천 3개 진입점이 공유하는 헬퍼 — 상수 + 순수 함수 + 배당/시장신호 조회.

`goal_recommendation_service.py`(전체 자산 기준)·`goal_age_recommendation_service.py`(연령대별)·
`goal_horizon_recommendation_service.py`(투자기간별)가 전부 이 모듈을 import해
`import _goal_recommendation_common as _grc; _grc.fn()` 형태의 **모듈 참조**로 호출한다 —
이름으로 import해 로컬 바인딩하면 테스트 `patch("...goal_recommendation_service._fetch_dividend_yields")`
류가 각 소비 모듈 경로마다 따로 필요해져(과거 autouse fixture가 3경로 patch), 유지보수가
어려웠다. 이 모듈이 유일한 소유자이므로 patch 경로도 `_goal_recommendation_common.*` 하나로 통일된다.

역방향 의존 없음 — 이 모듈은 goal_recommendation_service/age/horizon 어느 것도 import하지 않는다.

세 진입점의 공통 계산 골격(설정 파싱 → CAGR 확보 후보 필터링 → 일별수익률 조회 → MVO)도
여기 있다(`_GoalCandidate`/`_candidates_with_cagr`/`_fetch_candidate_returns`/`_run_goal_optimizer` 등).
배당 목표 처리(`_suggest_for_dividend_goal`·`_apply_dividend_suggestions` 등)는 `_goal_dividend_suggestions.py`.
단, `get_historical_returns`·`fetch_yf_daily_returns`·`build_portfolio_overview` 같은 외부 조회는 각 진입점
모듈에서 호출한다 — 테스트가 그 이름을 진입점 모듈 경로로 patch하기 때문이다
(`_fetch_candidate_returns`가 조회 함수를 인자로 받는 이유).
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import NamedTuple

import structlog
from pydantic import BaseModel

from app.constants import (
    CASH_EQUIVALENT_MARKET,
    CASH_EQUIVALENT_NAME,
    CASH_EQUIVALENT_TICKER,
    DEFAULT_GOAL_CAGR_LOOKBACK_YEARS,
    DOMESTIC_MARKETS,
)
from app.schemas.rebalancing import (
    GoalRecommendation,
)
from app.services.dividend.constants import is_korean_etf
from app.services.dividend.sync_sources import (
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.goal.goal_portfolio_optimizer import (
    _MAX_WEIGHT,
    _MIN_RETURN_DAYS,
    _optimize_goal_portfolio,
)
from app.services.market_data.yahoo_price import run_yf_bounded, to_yf_symbol
from app.services.market_signal.market_signal_service import get_market_signal
from app.utils.cache_keys import (
    TTL_DAILY_RETURNS,
    TTL_GOAL_CANDIDATE_DIVIDEND_YIELD,
    TTL_GOAL_RECOMMENDATION,
    TTL_GOAL_RECOMMENDATION_INCOMPLETE,
    TTL_GOAL_RECOMMENDATION_STALE,
    CacheStoreType,
    daily_returns_key,
    get_cached_json,
    goal_candidate_dividend_yield_key,
    set_cached_json,
)
from app.utils.inproc_lock import single_flight_fetch

logger = structlog.get_logger()

_DIVIDEND_FETCH_CONCURRENCY = 8
_dividend_fetch_sem = asyncio.Semaphore(_DIVIDEND_FETCH_CONCURRENCY)
"""프로세스 공용 — 호출마다 만들면 horizon 15개 조합이 동시에 돌 때 8×15건이 된다."""
_DEFAULT_CAGR_LOOKBACK_YEARS = DEFAULT_GOAL_CAGR_LOOKBACK_YEARS

_NON_BINDING_RETURN_FLOOR = -50.0
"""기간별/연령대별 추천은 목표 역산이 아니므로 required_return_pct 하한 제약을 사실상 무효화한다
(전체 자산 기준 경로도 배당목표만 있고 자산목표가 없으면 이 값을 사용). 투자기간별 상수·로직은
`goal_horizon_recommendation_service.py`로 분리됨."""

_CASH_EQUIVALENT_TICKER = CASH_EQUIVALENT_TICKER
"""실제 시세 없는 합성 후보 식별자 — app.constants의 공유 정의 재노출(하위 호환 별칭)."""
_CASH_EQUIVALENT_NAME = CASH_EQUIVALENT_NAME
_CASH_EQUIVALENT_MARKET = CASH_EQUIVALENT_MARKET
_CASH_EQUIVALENT_CAGR_PCT = 3.0
"""CMA/파킹통장 평균 금리 가정치(%) — 실제 상품별로 상이하고 시세 데이터가 없어 고정값을 사용한다.
CONSERVATIVE 리스크 성향은 required_return_pct 부등식 제약이 비구속적(_NON_BINDING_RETURN_FLOOR)이므로
이 값은 비중 계산에 거의 영향을 주지 않고 주로 expected_return_pct 표시용으로 쓰인다."""
_CASH_EQUIVALENT_RETURN_DAYS = 252


def _cash_equivalent_daily_returns() -> list[float]:
    """변동성 0으로 가정한 합성 일별수익률 시계열 — MVO 공분산 계산에 참여시키기 위함."""
    return [_CASH_EQUIVALENT_CAGR_PCT / 100 / _CASH_EQUIVALENT_RETURN_DAYS] * _CASH_EQUIVALENT_RETURN_DAYS


async def _fetch_market_signal_level(cache: CacheStoreType) -> str | None:
    """추천 비중 계산에 반영할 시장 위험 신호 등급을 안전하게 조회한다.

    조회 실패 또는 `data_freshness="STALE"`(신뢰 불가)이면 감쇠 없이(None) 기존 동작을 유지한다
    — 참고용 제안이라 fail-open이 적절하며, AUTO 실행 게이트(`is_market_signal_blocking_auto_mode`)와
    달리 실패 시 보수적으로 차단할 필요가 없다.
    """
    try:
        signal = await get_market_signal(cache)
    except Exception as e:
        logger.warning("goal_recommendation_market_signal_failed", error=str(e))
        return None
    if signal.get("data_freshness") == "STALE":
        return None
    return signal.get("composite_level")


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


async def _fetch_dividend_yields(
    cache: CacheStoreType, candidates: list[tuple[str, str]]
) -> dict[tuple[str, str], float]:
    """후보 종목의 배당수익률(%)을 조회한다.

    `api/v1/rebalancing.py`의 `_collect_dividend_map`과 동일한 소스(Naver/Yahoo)를 쓰되,
    임의의 후보 티커 목록(포트폴리오 미보유 큐레이션 ETF 포함)을 대상으로 한다는 점이 다르다.

    ticker+market 단위로 `TTL_GOAL_CANDIDATE_DIVIDEND_YIELD`(1일) 전역 캐시를 공유한다 —
    유저별 요청마다 반복 조회할 필요가 없어, 첫 콜드 계산 이후에는 모든 유저·추천 경로
    (전체/기간별/연령대별)가 캐시를 재사용해 Naver/Yahoo 실시간 스크래핑 호출을 건너뛴다.
    배당수익률이 0인 종목도 그대로 캐싱한다 — 재조회 자체를 막는 게 목적이라, 매 콜드미스마다
    무배당 종목을 다시 스크래핑하는 낭비를 없앤다(원본 필터링 동작은 `result` 포함 여부로 유지).
    """
    loop = asyncio.get_running_loop()
    result: dict[tuple[str, str], float] = {}

    async def _fetch_one(ticker: str, market: str) -> None:
        cache_key = goal_candidate_dividend_yield_key(ticker, market)
        cached = await get_cached_json(cache, cache_key)
        if cached is not None:
            if cached.get("yield_pct", 0.0) > 0:
                result[(ticker, market)] = cached["yield_pct"]
            return
        try:
            async with _dividend_fetch_sem:
                if market.upper() in DOMESTIC_MARKETS:
                    fn = (
                        sync_naver_etf_dividend_info
                        if is_korean_etf(ticker, market)
                        else sync_naver_stock_dividend_info
                    )
                    info = await loop.run_in_executor(None, fn, ticker)
                else:
                    info = await run_yf_bounded(sync_yahoo_dividend_info, to_yf_symbol(ticker, market))
            if info.get("fetch_failed"):
                # 조회 실패를 "배당 0%"로 전역 캐시하면 복구 뒤에도 하루 동안 모든 유저의 배당 목표가 틀어진다
                return
            yield_pct = info["dividend_yield"] * 100
            await set_cached_json(cache, cache_key, {"yield_pct": yield_pct}, TTL_GOAL_CANDIDATE_DIVIDEND_YIELD)
            if yield_pct > 0:
                result[(ticker, market)] = yield_pct
        except Exception as e:
            logger.warning("goal_recommendation_dividend_fetch_failed", ticker=ticker, market=market, error=str(e))

    await asyncio.gather(*[_fetch_one(t, m) for t, m in candidates])
    return result


def _equity_class_bounds(
    equity_floor: float | None, equity_ceiling: float | None
) -> dict[str, tuple[float, float]] | None:
    """단기/IRP/연령대별 추천의 EQUITY vs OTHER 이분법 하한·상한을 `class_bounds`로 변환한다 —
    호출측은 항상 둘 중 하나만 넘긴다(`_AGE_GROUP_PROFILE` 독스트링 참고)."""
    if equity_floor is not None:
        return {"EQUITY": (equity_floor, 1.0)}
    if equity_ceiling is not None:
        return {"EQUITY": (0.0, equity_ceiling)}
    return None


# ── 세 진입점 공통 계산 골격 ───────────────────────────────────────────────────


class _GoalCandidate(NamedTuple):
    """CAGR이 확보된 옵티마이저 입력 후보 1개."""

    symbol: str  # yfinance 심볼(합성 현금성 자산은 `_CASH_EQUIVALENT_TICKER`)
    ticker: tuple[str, str, str]  # (ticker, name, market)
    cagr_pct: float
    asset_class: str  # `_optimize_goal_portfolio`의 `class_bounds` 키
    dividend_yield_pct: float


def _join_notes(*notes: str | None) -> str | None:
    """비어 있지 않은 안내 문구를 순서대로 공백으로 잇는다(전부 비면 None)."""
    return " ".join(n for n in notes if n) or None


def _max_weight_from_settings(settings_row: object) -> float:
    """`goal_max_weight_pct`(%) → 종목당 최대 비중(0~1). 미설정이면 `_MAX_WEIGHT`."""
    max_weight_pct_raw = getattr(settings_row, "goal_max_weight_pct", None)
    return float(max_weight_pct_raw) / 100 if max_weight_pct_raw else _MAX_WEIGHT


def cagr_lookback_years_from_settings(settings_row: object) -> int:
    return int(getattr(settings_row, "goal_cagr_lookback_years", None) or _DEFAULT_CAGR_LOOKBACK_YEARS)


async def read_cached_model[M: BaseModel](cache: CacheStoreType, key: str, model: type[M]) -> M | None:
    """캐시 JSON을 `model`로 복원한다(없으면 None)."""
    cached = await get_cached_json(cache, key)
    return model(**cached) if cached is not None else None


async def cached_recommendation[M: BaseModel](
    cache: CacheStoreType,
    cache_key: str,
    stale_key: str,
    model: type[M],
    compute: Callable[[], Awaitable[M]],
    cacheable: Callable[[M], bool],
    incomplete: Callable[[M], bool] | None = None,
) -> M:
    """추천 3종(전체·기간별·나이별) 공용 캐시 골격: 1시간 키 히트면 반환, 아니면 single-flight로 1건만 계산.

    `cacheable(result)`가 참일 때만 1시간 키와 stale(1일) 키에 저장한다 — 빈 추천(일시적 외부 API 장애 등)을
    캐싱하면 복구 뒤에도 TTL 동안 같은 실패를 돌려준다. cache가 None이면 매번 계산한다.
    `incomplete(result)`가 참이면(일부 후보의 시세를 못 가져옴) 짧게만 저장하고 stale 키에는 넣지 않는다 — 장애 중
    결과가 하루 동안 남지 않게. 아예 안 저장하면 시세가 계속 없는 후보(상장 직후 ETF)를 가진 유저가 매번 전부 계산한다.
    """

    async def _read_cache() -> M | None:
        return await read_cached_model(cache, cache_key, model)

    cached = await _read_cache()
    if cache is not None and cached is not None:
        return cached

    async def _fetch_and_cache() -> M:
        result = await compute()
        if cacheable(result):
            payload = result.model_dump(mode="json")
            if incomplete is not None and incomplete(result):
                await set_cached_json(cache, cache_key, payload, TTL_GOAL_RECOMMENDATION_INCOMPLETE)
                return result
            await set_cached_json(cache, cache_key, payload, TTL_GOAL_RECOMMENDATION)
            await set_cached_json(cache, stale_key, payload, TTL_GOAL_RECOMMENDATION_STALE)
        return result

    if cache is None:
        return await _fetch_and_cache()

    return await single_flight_fetch(cache, cache_key, _read_cache, _fetch_and_cache)


def investable_assets_krw(overview: dict) -> float:
    """overview 총자산에서 부동산을 뺀 값 — 필요 수익률·필요 배당수익률 역산의 기준 자산.

    부동산은 MVO 후보에 포함되지 않으므로(성장 미모델링) 기준에 넣으면 부동산 추가만으로 필요 수익률이
    부당하게 낮아지거나 "이미 달성"으로 잘못 판정된다. 전체·기간별·나이별 경로가 모두 이 값을 쓴다.
    """
    real_estate_krw = next(
        (item["amount_krw"] for item in overview.get("asset_type_allocation", []) if item.get("type") == "REAL_ESTATE"),
        0.0,
    )
    return float(overview.get("total_assets_krw", 0)) - real_estate_krw


def _required_dividend_yield_pct(annual_dividend_goal: float | None, total_assets_krw: float) -> float | None:
    """연 배당목표(원) ÷ 기준 자산총액 → 필요 배당수익률(%). 목표가 없거나 자산이 0 이하면 None."""
    if not annual_dividend_goal or total_assets_krw <= 0:
        return None
    return round(float(annual_dividend_goal) / total_assets_krw * 100, 2)


def _candidates_with_cagr(
    candidate_dicts: list[dict[str, str]],
    cagr_map: dict[tuple[str, str], dict],
    dividend_map: dict[tuple[str, str], float],
    *,
    equity_vs_other: bool,
) -> list[_GoalCandidate]:
    """CAGR 데이터가 확보된 후보만 남겨 옵티마이저 입력으로 묶는다.

    `equity_vs_other=True`(연령대별·투자기간별)면 자산군을 EQUITY vs OTHER 이분법으로, False(전체 자산
    기준)면 등록된 자산군(EQUITY/BOND/CASH) 그대로 둔다 — 전자는 주식비중 하한·상한만, 후자는 채권·현금성
    상한을 자산군별로 걸기 때문이다.
    """
    result: list[_GoalCandidate] = []
    for c in candidate_dicts:
        t, m = c["ticker"], c["market"]
        cagr = (cagr_map.get((t, m)) or {}).get("cagr_pct")
        if cagr is None:
            continue
        asset_class = c.get("asset_class", "EQUITY")
        if equity_vs_other:
            asset_class = "EQUITY" if asset_class == "EQUITY" else "OTHER"
        result.append(
            _GoalCandidate(to_yf_symbol(t, m), (t, c["name"], m), cagr, asset_class, dividend_map.get((t, m), 0.0))
        )
    return result


def _has_real_safe_asset(candidates: list[_GoalCandidate]) -> bool:
    return any(c.asset_class != "EQUITY" for c in candidates)


def _has_usable_safe_asset(candidates: list[_GoalCandidate], returns_map: dict[str, list[float]]) -> bool:
    """옵티마이저까지 살아남는 실제 안전자산 후보가 있는지 — CAGR이 있어도 일별수익률이 모자라면 옵티마이저가 뺀다."""
    return any(
        c.asset_class != "EQUITY" and len(returns_map.get(c.symbol) or []) >= _MIN_RETURN_DAYS for c in candidates
    )


def _ensure_safe_asset(candidates: list[_GoalCandidate], returns_map: dict[str, list[float]]) -> bool:
    """안전자산 제약이 걸린 추천에서 쓸 수 있는 안전자산이 없으면 합성 현금성 후보를 넣는다. 넣었으면 True."""
    if _has_usable_safe_asset(candidates, returns_map):
        return False
    if not any(c.symbol == _CASH_EQUIVALENT_TICKER for c in candidates):
        candidates.append(_cash_equivalent_candidate())
    returns_map[_CASH_EQUIVALENT_TICKER] = _cash_equivalent_daily_returns()
    return True


def _missing_candidate_count(
    eligible_count: int, candidates: list[_GoalCandidate], returns_map: dict[str, list[float]]
) -> int:
    """등록 후보 중 시세·수익률 데이터가 없어 계산에서 빠진 수(합성 현금성 후보는 세지 않는다)."""
    usable = sum(
        1
        for c in candidates
        if c.symbol != _CASH_EQUIVALENT_TICKER and len(returns_map.get(c.symbol) or []) >= _MIN_RETURN_DAYS
    )
    return max(0, eligible_count - usable)


def _missing_candidates_note(missing: int) -> str | None:
    if missing <= 0:
        return None
    return f"시세를 가져오지 못한 후보 {missing}개를 빼고 계산했어요 — 잠시 후 다시 확인해 주세요"


def _cash_equivalent_candidate() -> _GoalCandidate:
    """시세 없는 합성 현금성 자산(CMA·파킹통장) 후보 — `_cash_equivalent_daily_returns()`와 짝."""
    return _GoalCandidate(
        _CASH_EQUIVALENT_TICKER,
        (_CASH_EQUIVALENT_TICKER, _CASH_EQUIVALENT_NAME, _CASH_EQUIVALENT_MARKET),
        _CASH_EQUIVALENT_CAGR_PCT,
        "OTHER",
        0.0,
    )


async def _fetch_candidate_returns(
    fetch_daily_returns: Callable[[list[str]], dict[str, list[float]]],
    candidates: list[_GoalCandidate],
    include_cash_equivalent: bool,
    cache: CacheStoreType = None,
) -> dict[str, list[float]]:
    """후보의 일별수익률을 조회하고, 합성 현금성 자산이 포함되면 그 합성 시계열을 더한다.

    `fetch_daily_returns`는 호출 모듈의 `fetch_yf_daily_returns`를 넘긴다(모듈 docstring 참고).
    심볼별 결과는 `TTL_DAILY_RETURNS`(1일) 전역 캐시를 공유한다 — 순차 `yf.download`(threads=False)가
    추천 콜드 계산의 가장 느린 구간이었고, 기간별 추천은 조합마다 같은 심볼을 반복 조회했다.
    조회에 실패해 결과에 없는 심볼은 캐싱하지 않는다(다음 요청에서 재시도).
    """
    real_symbols = [c.symbol for c in candidates if c.symbol != _CASH_EQUIVALENT_TICKER]
    returns_map: dict[str, list[float]] = {}
    if real_symbols:
        cached = await asyncio.gather(*(get_cached_json(cache, daily_returns_key(s)) for s in real_symbols))
        returns_map = {s: v for s, v in zip(real_symbols, cached, strict=True) if isinstance(v, list)}
        missing = [s for s in real_symbols if s not in returns_map]
        logger.info("goal_daily_returns_cache", hit=len(returns_map), miss=len(missing))
        if missing:
            fetched = await run_yf_bounded(fetch_daily_returns, missing)
            returns_map.update(fetched)
            for sym in missing:
                if sym in fetched:
                    await _cache_daily_returns(cache, sym, fetched[sym])
    if include_cash_equivalent:
        returns_map[_CASH_EQUIVALENT_TICKER] = _cash_equivalent_daily_returns()
    return returns_map


async def _cache_daily_returns(cache: CacheStoreType, symbol: str, returns: list[float]) -> None:
    try:
        await set_cached_json(cache, daily_returns_key(symbol), returns, TTL_DAILY_RETURNS)
    except ValueError:  # NaN/Infinity 포함 — 캐싱만 건너뛰고 계산은 그대로
        logger.warning("goal_daily_returns_cache_skipped", symbol=symbol)


async def _run_goal_optimizer(
    candidates: list[_GoalCandidate],
    returns_map: dict[str, list[float]],
    required_return_pct: float,
    *,
    max_weight: float,
    risk_tolerance: str,
    class_bounds: dict[str, tuple[float, float]] | None,
    market_signal_level: str | None,
    required_dividend_yield_pct: float | None,
) -> tuple[list[dict], float | None, float | None, str | None]:
    """`_optimize_goal_portfolio`(동기 SLSQP)를 executor에서 실행한다."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(
            _optimize_goal_portfolio,
            [c.symbol for c in candidates],
            [c.ticker for c in candidates],
            [c.cagr_pct for c in candidates],
            returns_map,
            required_return_pct,
            max_weight=max_weight,
            risk_tolerance=risk_tolerance,
            asset_classes=[c.asset_class for c in candidates],
            class_bounds=class_bounds,
            market_signal_level=market_signal_level,
            dividend_yields=[c.dividend_yield_pct for c in candidates],
            required_dividend_yield_pct=required_dividend_yield_pct,
        ),
    )


def _includes_cash_equivalent(items: list[dict]) -> bool:
    return any(i["ticker"] == _CASH_EQUIVALENT_TICKER for i in items)
