"""목표 역산 추천 3개 진입점이 공유하는 헬퍼 — 상수 + 순수 함수 + 배당/시장신호 조회.

`goal_recommendation_service.py`(전체 자산 기준)·`goal_age_recommendation_service.py`(연령대별)·
`goal_horizon_recommendation_service.py`(투자기간별)가 전부 이 모듈을 import해
`import _goal_recommendation_common as _grc; _grc.fn()` 형태의 **모듈 참조**로 호출한다 —
이름으로 import해 로컬 바인딩하면 테스트 `patch("...goal_recommendation_service._fetch_dividend_yields")`
류가 각 소비 모듈 경로마다 따로 필요해져(과거 autouse fixture가 3경로 patch), 유지보수가
어려웠다. 이 모듈이 유일한 소유자이므로 patch 경로도 `_goal_recommendation_common.*` 하나로 통일된다.

역방향 의존 없음 — 이 모듈은 goal_recommendation_service/age/horizon 어느 것도 import하지 않는다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import structlog

from app.constants import (
    CASH_EQUIVALENT_MARKET,
    CASH_EQUIVALENT_NAME,
    CASH_EQUIVALENT_TICKER,
    DOMESTIC_MARKETS,
)
from app.schemas.rebalancing import GoalRecommendation, GoalRecommendationItem
from app.services.dividend.constants import is_korean_etf
from app.services.dividend.sync_sources import (
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.goal_portfolio_optimizer import _dividend_floor_constraint
from app.services.market_signal_service import get_market_signal
from app.services.recommendation_universe import RECOMMENDATION_UNIVERSE
from app.services.yahoo_price import to_yf_symbol
from app.utils.cache_keys import (
    TTL_GOAL_CANDIDATE_DIVIDEND_YIELD,
    CacheStoreType,
    get_cached_json,
    goal_candidate_dividend_yield_key,
    set_cached_json,
)

logger = structlog.get_logger()

_DIVIDEND_FETCH_CONCURRENCY = 8
_DEFAULT_CAGR_LOOKBACK_YEARS = 10

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

_DIVIDEND_IMPROVEMENT_THRESHOLD_PCT = 0.5
"""이미 배당 목표를 달성했어도, 미등록 후보를 추가했을 때 그리디 최대 달성 가능 배당수익률이
이 값(%p) 이상 개선되면 `_suggest_for_dividend_goal()`이 "더 나은 옵션이 있습니다"로 제안한다.
노이즈성 제안(0.1%p 차이로 계속 새 종목을 권유)을 막기 위한 최소 유의미 기준 —
`_RECOMMENDATION_DRIFT_THRESHOLD_PCT`(3.0%p, 비중 변화 감지용, goal_recommendation_service.py)와는
판단 축이 달라 값도 다르게 잡는다."""

_MIN_SUGGESTABLE_DIVIDEND_YIELD_PCT = 2.5
"""`_suggest_for_dividend_goal()`이 "고배당 후보"로 제안할 수 있는 최소 배당수익률(%) 하한.
큐레이션 유니버스(`RECOMMENDATION_UNIVERSE`)에는 SPY/QQQ/KODEX200 같은 저배당 브로드마켓 ETF와
채권/현금성 ETF도 섞여 있는데, 하한 없이 "목표 달성에 필요한 만큼만" 그리디하게 채우다 보면
사용자가 이미 진짜 고배당 ETF(JEPI/JEPQ/SCHD 등)를 후보로 등록해둔 상태에서 남은 풀 중 "가장
나은" 선택지가 저배당 종목이 되어도 그대로 "고배당 후보"로 제안되는 문제가 있었다 — 이 하한
미만인 후보는 목표 달성에 부족하더라도(상태는 unreachable로 유지) 아예 제안하지 않는다.

3.0%로 처음 도입했다가 실측 데이터로 2.5%로 낮췄다 — 국내계좌(GENERAL/ISA/PENSION_SAVINGS/IRP)는
지역 선호 필터로 해외상장 고배당 ETF(JEPI/JEPQ/SCHD)가 애초에 제안 풀에서 제외되는데, 유일하게
남는 국내상장 배당형 ETF(458730/446720, Dow Jones US Dividend 100 추종)의 실제 수익률이 ~2.9%로
3.0%를 근소하게 밑돌아 이 계좌군에서 고배당 후보가 사실상 영구히 제안되지 않는 문제가 있었다."""


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

    ticker+market 단위로 `TTL_GOAL_CANDIDATE_DIVIDEND_YIELD`(1시간) 전역 캐시를 공유한다 —
    유저별 요청마다 반복 조회할 필요가 없어, 첫 콜드 계산 이후에는 모든 유저·추천 경로
    (전체/기간별/연령대별)가 캐시를 재사용해 Naver/Yahoo 실시간 스크래핑 호출을 건너뛴다.
    배당수익률이 0인 종목도 그대로 캐싱한다 — 재조회 자체를 막는 게 목적이라, 매 콜드미스마다
    무배당 종목을 다시 스크래핑하는 낭비를 없앤다(원본 필터링 동작은 `result` 포함 여부로 유지).
    """
    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(_DIVIDEND_FETCH_CONCURRENCY)
    result: dict[tuple[str, str], float] = {}

    async def _fetch_one(ticker: str, market: str) -> None:
        cache_key = goal_candidate_dividend_yield_key(ticker, market)
        cached = await get_cached_json(cache, cache_key)
        if cached is not None:
            if cached.get("yield_pct", 0.0) > 0:
                result[(ticker, market)] = cached["yield_pct"]
            return
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
            yield_pct = info["dividend_yield"] * 100
            await set_cached_json(cache, cache_key, {"yield_pct": yield_pct}, TTL_GOAL_CANDIDATE_DIVIDEND_YIELD)
            if yield_pct > 0:
                result[(ticker, market)] = yield_pct
        except Exception as e:
            logger.warning("goal_recommendation_dividend_fetch_failed", ticker=ticker, market=market, error=str(e))

    await asyncio.gather(*[_fetch_one(t, m) for t, m in candidates])
    return result


def _attach_dividend_yield(
    items: list[dict[str, object]], dividend_map: dict[tuple[str, str], float]
) -> list[GoalRecommendationItem]:
    """옵티마이저 결과(`items`)에 `_fetch_dividend_yields()`가 이미 조회해둔 종목별 배당수익률을
    붙인다 — 배당 목표 제약(`_optimize_goal_portfolio`)은 포트폴리오 전체 가중평균에만 걸리므로,
    저배당 종목(예: 성장형 지수 ETF)도 분산 목적으로 결과에 포함될 수 있다. 화면에서 이를 구분할
    수 있도록 종목별 수치를 노출한다(조회 실패/데이터 없음이면 None)."""
    return [
        GoalRecommendationItem(**i, dividend_yield_pct=dividend_map.get((str(i["ticker"]), str(i["market"]))))
        for i in items
    ]


async def _suggest_for_dividend_goal(
    cache: CacheStoreType,
    candidate_dicts: list[dict[str, str]],
    required_dividend_yield_pct: float | None,
    expected_dividend_yield_pct: float | None,
    max_weight: float,
    capacity_remaining: int,
    market_filter: Callable[[dict[str, str]], bool] | None = None,
) -> tuple[list[dict[str, object]], str | None, str | None]:
    """등록된 후보만으로 배당 목표(`required_dividend_yield_pct`) 달성이 어렵거나, 이미 달성했더라도
    등록후보 밖에 유의미하게 더 높은 배당수익률 후보가 있으면 큐레이션 유니버스(`RECOMMENDATION_UNIVERSE`)
    에서 필요한 만큼만 "제안"한다 — 등록 목록(`UserSettings.goal_candidate_tickers`)에는 반영하지
    않고, 반환된 제안 목록은 응답의 `suggested_candidates` 필드로만 노출된다. 사용자가 추천 카드의
    "후보에 추가" 버튼으로 승인해야만 `PUT /settings/goal-candidate-tickers`를 통해 실제로 저장되고,
    그래야 다음 추천 계산부터 비중 산출에 포함된다 — 사용자 동의 없이 후보 목록이 바뀌는 것을
    막기 위한 설계.

    `_get_or_seed_candidates`는 최초 1회만 시딩하고 이후에는 저장된 목록을 그대로 쓴다(자동
    병합 없음, "후보 ETF 관리"에서 사용자가 편집한 목록을 존중하기 위한 의도된 설계) — 그래서
    큐레이션 유니버스에 새 고배당 ETF를 추가해도 이미 후보를 등록한 기존 사용자에게는 영원히
    노출되지 않는다. 이 함수는 "배당 목표 달성/개선에 실제로 필요한 경우"에만 한정해 제안함으로써
    사용자가 등록하지 않은 임의 종목을 무분별하게 제안하지 않으면서 이 gap을 메운다.

    `expected_dividend_yield_pct`는 이번 계산에서 최적화 이후 실제로 산출된 가중평균 배당수익률이다
    (아직 최적화 전이거나 실패했으면 호출측이 None을 넘긴다 — 이 경우 무조건 미달성으로 취급한다).
    `expected_dividend_yield_pct < required_dividend_yield_pct`(미달성)면 목표치를 달성하는 후보를
    찾고, 이미 달성했으면(`expected >= required`) `expected + _DIVIDEND_IMPROVEMENT_THRESHOLD_PCT`를
    새 탐색 목표로 삼아 "더 나은 옵션"을 찾는다 — 둘 다 동일한 그리디 탐색 루프를 목표치만 바꿔 재사용한다.

    반환값 3번째 요소 `dividend_goal_status`: `"unreachable"`(등록 후보로 목표 달성 불가) /
    `"improvable"`(이미 달성했지만 더 나은 후보가 있음) / `"optimal"`(달성했고 더 나은 후보 없음) /
    `None`(배당 목표 자체가 없음).

    달성가능성 판정은 종목당 `max_weight` 상한만 고려하는 근사치(`_dividend_floor_constraint`를
    `equity_floor`/`equity_ceiling` 없이 호출)다 — 최종 게이트는 `_optimize_goal_portfolio`의
    그룹예산까지 반영한 정확한 검증이 담당하므로, 여기서는 "제안이 더 필요한가"를 판단하는
    트리거로만 쓰기에 충분하다(과소·과대 추정돼도 최종 결과의 정확성에는 영향 없음).

    `candidate_dicts`는 이번 계산(전체 등록 목록의 부분집합일 수 있음, 예: 기간별 추천의
    세제유형별 필터링 결과)에 쓰이는 후보 집합이고, `capacity_remaining`은 항상 호출측이
    **전체** 등록 목록 기준(`MAX_GOAL_CANDIDATE_TICKERS - 전체 등록 후보 수`)으로 계산해
    넘겨야 한다 — `_apply_index_region_preference`와 동일한 컨벤션.
    """
    if not required_dividend_yield_pct:
        return [], None, None

    if expected_dividend_yield_pct is None:
        unreachable = True
        search_target = required_dividend_yield_pct
    else:
        unreachable = expected_dividend_yield_pct < required_dividend_yield_pct
        search_target = (
            required_dividend_yield_pct
            if unreachable
            else expected_dividend_yield_pct + _DIVIDEND_IMPROVEMENT_THRESHOLD_PCT
        )
    status: str = "unreachable" if unreachable else "optimal"

    def _achievable(dicts: list[dict[str, str]], dividend_map: dict[tuple[str, str], float]) -> bool:
        if not dicts:
            return False
        divs = tuple(dividend_map.get((c["ticker"], c["market"]), 0.0) for c in dicts)
        bounds = [(0.0, max_weight)] * len(dicts)
        constraint, _ = _dividend_floor_constraint(bounds, divs, search_target)
        return constraint is not None

    tickers_only = [(c["ticker"], c["market"]) for c in candidate_dicts]
    dividend_map = await _fetch_dividend_yields(cache, tickers_only)
    if not unreachable and _achievable(candidate_dicts, dividend_map):
        # 이미 달성 + 등록 후보만으로 개선 목표(search_target)까지도 달성 가능 — 제안 불필요
        return [], None, status

    seen = {(c["ticker"], c["market"]) for c in candidate_dicts}
    pool = [
        c
        for c in RECOMMENDATION_UNIVERSE
        if (c["ticker"], c["market"]) not in seen and (market_filter is None or market_filter(c))
    ]
    if not pool or capacity_remaining <= 0:
        return [], None, status

    pool_dividend_map = await _fetch_dividend_yields(cache, [(c["ticker"], c["market"]) for c in pool])
    # 절대 수익률 하한 미만인 후보는 "고배당"이라 부를 수 없으므로 애초에 정렬 대상에서 제외한다
    # (`_MIN_SUGGESTABLE_DIVIDEND_YIELD_PCT` 참고) — 목표 달성에 부족해도 저배당 종목으로 채우지 않는다.
    pool_above_floor = [
        c for c in pool if pool_dividend_map.get((c["ticker"], c["market"]), 0.0) >= _MIN_SUGGESTABLE_DIVIDEND_YIELD_PCT
    ]
    pool_sorted = sorted(
        pool_above_floor, key=lambda c: pool_dividend_map.get((c["ticker"], c["market"]), 0.0), reverse=True
    )
    combined_dividend_map = {**dividend_map, **pool_dividend_map}

    trial = list(candidate_dicts)
    suggested: list[dict[str, object]] = []
    for c in pool_sorted:
        if len(suggested) >= capacity_remaining:
            break
        yield_pct = pool_dividend_map.get((c["ticker"], c["market"]), 0.0)
        trial.append(c)
        suggested.append({**c, "dividend_yield_pct": round(yield_pct, 2)})
        if _achievable(trial, combined_dividend_map):
            break

    if not suggested:
        return [], None, status

    status = "unreachable" if unreachable else "improvable"
    note = (
        f"등록된 후보로는 배당 목표(연 {required_dividend_yield_pct:.1f}%)를 달성하기 어렵습니다 — "
        "아래 고배당 후보를 추가하면 도움이 됩니다"
        if unreachable
        else "이미 배당 목표를 달성했지만, 아래 후보를 추가하면 배당수익률을 더 높일 수 있습니다"
    )
    return suggested, note, status


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
