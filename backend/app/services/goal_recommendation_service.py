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
막지 않음). `get_horizon_recommendations`(투자기간별)은 목표금액 역산을 하지 않는 별도 경로지만,
배당 목표는 전체 자산 기준과 동일한 필요배당수익률(%)을 모든 (기간,세제유형) 조합에 동일 적용해
함께 반영한다(`_compute_horizon_recommendations` 참고).

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

MVO 최적화 엔진은 `goal_portfolio_optimizer.py`, 후보 종목 관리/영속화는 `goal_candidate_service.py`
로 분리되어 있다 — 이 파일에는 API 진입점(전체 자산 기준 `get_goal_recommendation`, 투자기간별
`get_horizon_recommendations`, 연령대별 `get_age_based_recommendation`)과 그 사이에서 공유되는
소규모 헬퍼만 남아 있다.

`get_age_based_recommendation`(연령대별)은 `UserSettings.age_group`(사용자가 직접 선택한
20대/30대/40대/50대/60대 이상 연령대)에 따라, 목표금액 역산 없이 연령대에 맞는 리스크 성향 +
주식비중 상/하한만으로 추천 비중을 계산한다 — 목표 역산을 하지 않는다는 점에서
`get_horizon_recommendations`와 성격이 같다(`_NON_BINDING_RETURN_FLOOR`로 required_return_pct
제약을 사실상 무효화).
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

from app.constants import (
    CASH_EQUIVALENT_MARKET,
    CASH_EQUIVALENT_NAME,
    CASH_EQUIVALENT_TICKER,
    DOMESTIC_MARKETS,
)
from app.enums import AccountTaxType, AgeGroup, InvestmentHorizon
from app.models.asset import AssetAccount
from app.models.user import UserSettings
from app.schemas.rebalancing import (
    GoalRecommendation,
    GoalRecommendationItem,
    HorizonGoalRecommendation,
    HorizonRecommendationResponse,
    PortfolioExpectedMetrics,
    SuggestedGoalCandidate,
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
    _matches_index_region_preference,
    _persist_added_candidates,
    detect_duplicate_tracking_index_note,
    existing_items_from_positions,
)
from app.services.goal_portfolio_optimizer import (
    _MAX_WEIGHT,
    _MIN_CANDIDATES,
    _dividend_floor_constraint,
    _optimize_goal_portfolio,
    compute_weighted_expected_metrics,
)
from app.services.goal_return_solver import months_until_year_end, solve_required_annual_return_pct
from app.services.market_data_fetcher import fetch_yf_daily_returns
from app.services.market_signal_service import get_market_signal
from app.services.portfolio_service import (
    build_portfolio_overview,
    compute_total_assets_krw,
    prefetch_accounts_snapshot_positions,
)
from app.services.position_aggregator import query_latest_position_map
from app.services.price_service import get_historical_returns
from app.services.recommendation_universe import MAX_GOAL_CANDIDATE_TICKERS, RECOMMENDATION_UNIVERSE
from app.services.yahoo_price import _yfinance_sem, to_yf_symbol
from app.utils.cache_keys import (
    TTL_GOAL_RECOMMENDATION,
    CacheStoreType,
    get_cached_json,
    goal_recommendation_age_key,
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


_RECOMMENDATION_DRIFT_THRESHOLD_PCT = 3.0
"""`frontend/src/utils/recommendationDrift.ts`의 RECOMMENDATION_DRIFT_THRESHOLD_PCT와 동일하게
유지 — 프론트(화면을 열었을 때 배지)와 백엔드(주간 알림 job)가 같은 기준으로 "유의미한 변화"를
판단하게 하기 위함. 한쪽만 바꾸면 배지와 알림의 민감도가 어긋나므로 항상 함께 바꿀 것."""

_DIVIDEND_IMPROVEMENT_THRESHOLD_PCT = 0.5
"""이미 배당 목표를 달성했어도, 미등록 후보를 추가했을 때 그리디 최대 달성 가능 배당수익률이
이 값(%p) 이상 개선되면 `_suggest_for_dividend_goal()`이 "더 나은 옵션이 있습니다"로 제안한다.
노이즈성 제안(0.1%p 차이로 계속 새 종목을 권유)을 막기 위한 최소 유의미 기준 —
`_RECOMMENDATION_DRIFT_THRESHOLD_PCT`(3.0%p, 비중 변화 감지용)와는 판단 축이 달라 값도 다르게 잡는다."""


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
    dividend_map = await _fetch_dividend_yields(tickers_only)
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

    pool_dividend_map = await _fetch_dividend_yields([(c["ticker"], c["market"]) for c in pool])
    pool_sorted = sorted(pool, key=lambda c: pool_dividend_map.get((c["ticker"], c["market"]), 0.0), reverse=True)
    combined_dividend_map = {**dividend_map, **pool_dividend_map}

    trial = list(candidate_dicts)
    suggested: list[dict[str, object]] = []
    for c in pool_sorted:
        if len(suggested) >= capacity_remaining:
            break
        yield_pct = pool_dividend_map.get((c["ticker"], c["market"]), 0.0)
        if yield_pct <= 0:
            break  # 남은 후보는 배당수익률 데이터가 없거나 0 — 더 제안해도 목표 달성에 도움 안 됨
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


async def get_goal_recommendation(
    cache: CacheStoreType,
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
        cached = await get_cached_json(cache, goal_recommendation_key(user_id))
        if cached is not None:
            return GoalRecommendation(**cached)

    result = await _compute_goal_recommendation(cache, base_krw, existing_items, settings_row, db)

    if user_id is not None and result.recommended_items:
        await set_cached_json(
            cache, goal_recommendation_key(user_id), result.model_dump(mode="json"), TTL_GOAL_RECOMMENDATION
        )
    return result


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
    assert settings_row.goal_amount is not None
    assert settings_row.retirement_target_year is not None
    pmt = float(settings_row.monthly_deposit_amount or 0)
    if not pmt and settings_row.annual_deposit_goal:
        pmt = float(settings_row.annual_deposit_goal) / 12
    goal_amount = float(settings_row.goal_amount)
    target_year = int(settings_row.retirement_target_year)
    n_months = months_until_year_end(target_year)

    if n_months <= 0:
        return None, _no_recommendation("목표 연도가 이미 지났습니다 — 목표연도를 다시 설정해주세요")
    if pv >= goal_amount:
        return None, _no_recommendation(
            "이미 목표 금액을 달성했습니다", required_dividend_yield_pct=required_dividend_yield_pct
        )

    required_return_pct = solve_required_annual_return_pct(pv, pmt, n_months, goal_amount)
    if required_return_pct is None:
        return None, _no_recommendation(
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
        return _not_configured("목표금액·목표연도 또는 배당목표를 설정하면 추천을 받을 수 있습니다")

    pv = base_krw
    required_dividend_yield_pct = (
        round(float(settings_row.annual_dividend_goal) / pv * 100, 2)
        if settings_row.annual_dividend_goal and pv > 0
        else None
    )

    required_return_pct: float | None = None
    required_return_pct_for_optimizer = _NON_BINDING_RETURN_FLOOR
    if has_asset_goal:
        required_return_pct, early_result = _resolve_asset_goal_return_pct(
            settings_row, pv, required_dividend_yield_pct
        )
        if early_result is not None:
            return early_result
        assert required_return_pct is not None
        required_return_pct_for_optimizer = required_return_pct

    candidate_dicts = await _get_or_seed_candidates(db, settings_row, existing_items)

    if not candidate_dicts:
        return _no_recommendation(
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
    cagr_lookback_years = int(getattr(settings_row, "goal_cagr_lookback_years", None) or _DEFAULT_CAGR_LOOKBACK_YEARS)

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
        return await _suggest_for_dividend_goal(
            computed_candidates,
            required_dividend_yield_pct,
            expected_dividend_yield_pct,
            max_weight,
            capacity_remaining=dividend_capacity_remaining,
            market_filter=overall_market_filter,
        )

    candidates = [(c["ticker"], c["name"], c["market"]) for c in computed_candidates]
    tickers_only = [(t, m) for t, _, m in candidates]

    cagr_map, dividend_map, market_signal_level = await asyncio.gather(
        get_historical_returns(tickers_only, cache=cache, years=cagr_lookback_years),
        _fetch_dividend_yields(tickers_only),
        _fetch_market_signal_level(cache),
    )

    filtered = [
        (to_yf_symbol(t, m), (t, name, m), cagr_map[(t, m)]["cagr_pct"], dividend_map.get((t, m), 0.0))
        for t, name, m in candidates
        if (t, m) in cagr_map and cagr_map[(t, m)].get("cagr_pct") is not None
    ]
    if len(filtered) < _MIN_CANDIDATES:
        suggested_candidates, dividend_note, dividend_goal_status = await _suggest_dividend_candidates(None)
        result = _no_recommendation(
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
        recommended_items=_attach_dividend_yield(items, dividend_map),
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
            risk_tolerance=risk_tolerance,
            max_weight_pct=round(max_weight * 100, 2),
            market_signal_level=market_signal_level,
            note=_combine_note(note),
        )

    candidates = [(c["ticker"], c["name"], c["market"], c.get("asset_class", "EQUITY")) for c in eligible_candidates]
    tickers_only = [(t, m) for t, _, m, _ in candidates]

    cagr_map, dividend_map = (
        await asyncio.gather(
            get_historical_returns(tickers_only, cache=cache, years=cagr_lookback_years),
            _fetch_dividend_yields(tickers_only),
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
                _CASH_EQUIVALENT_TICKER,
                (_CASH_EQUIVALENT_TICKER, _CASH_EQUIVALENT_NAME, _CASH_EQUIVALENT_MARKET),
                _CASH_EQUIVALENT_CAGR_PCT,
                False,
                0.0,
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
        _, (tk, name, mk), cagr, _, dividend = filtered[0]
        is_synthetic = tk == _CASH_EQUIVALENT_TICKER
        return HorizonGoalRecommendation(
            investment_horizon=horizon,
            tax_type=tax_type,
            base_krw=base_krw,
            account_count=len(account_ids),
            recommended_items=[
                GoalRecommendationItem(
                    ticker=tk, name=name, market=mk, weight=100.0, dividend_yield_pct=dividend if dividend > 0 else None
                )
            ],
            expected_return_pct=cagr,
            expected_dividend_yield_pct=dividend if dividend > 0 else None,
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

    equity_floor: float | None = None
    equity_ceiling: float | None = None
    if is_irp:
        equity_ceiling = 1.0 - _DEFAULT_IRP_SAFE_ASSET_FLOOR_PCT / 100
    elif include_cash_equivalent and any(f_is_equity):
        equity_floor = short_term_equity_floor

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
            is_equity=f_is_equity,
            equity_floor=equity_floor,
            equity_ceiling=equity_ceiling,
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
        recommended_items=_attach_dividend_yield(items, dividend_map),
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
    """`_compute_horizon_recommendations()` 결과를 유저당 TTL_GOAL_RECOMMENDATION(10분) 캐싱한다.

    최대 15개(투자기간×세제유형) 조합에 대해 후보 필터링(순차, 조합 간 상태 의존) 후 조합별
    SLSQP 최적화를 수행하는 무거운 계산이라 캐싱 효과가 크다. 계좌/스냅샷/포지션 DB 조회는
    조합마다 반복하지 않고 루프 진입 전 한 번만 수행한다(`prefetch_accounts_snapshot_positions`).
    무효화 조건은 `get_goal_recommendation`과 동일.

    조합 중 하나라도 `recommended_items`가 비어 있으면(예: 해외전용 조합만 Yahoo 서킷브레이커에
    걸려 시세 데이터를 못 가져온 경우) 응답 전체를 캐싱하지 않는다 — 15개 조합이 하나의 캐시
    키로 묶여 있어, 그대로 캐싱하면 일시적으로 실패한 조합 하나 때문에 나머지 정상 조합까지
    TTL 동안 통째로 그 실패 상태를 계속 반환하게 된다.
    """
    cached = await get_cached_json(cache, goal_recommendation_horizon_key(user_id))
    if cached is not None:
        return HorizonRecommendationResponse(**cached)

    result = await _compute_horizon_recommendations(cache, db, user_id, settings_row)

    if all(rec.recommended_items for rec in result.recommendations):
        await set_cached_json(
            cache, goal_recommendation_horizon_key(user_id), result.model_dump(mode="json"), TTL_GOAL_RECOMMENDATION
        )
    return result


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
    cagr_lookback_years = int(getattr(settings_row, "goal_cagr_lookback_years", None) or _DEFAULT_CAGR_LOOKBACK_YEARS)
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
                AssetAccount.is_active == True,  # noqa: E712
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
    market_signal_level = await _fetch_market_signal_level(cache)

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
        suggested, dividend_note, dividend_goal_status = await _suggest_for_dividend_goal(
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


async def get_age_based_recommendation(
    cache: CacheStoreType,
    db: AsyncSession,
    user_id: uuid.UUID,
    settings_row: UserSettings,
) -> GoalRecommendation:
    """`_compute_age_based_recommendation()` 결과를 유저당 TTL_GOAL_RECOMMENDATION(10분) 캐싱한다.

    무효화 조건은 `get_goal_recommendation`/`get_horizon_recommendations`와 동일 —
    `invalidate_goal_recommendation_caches()`가 `age_group` 변경(설정 저장) 시에도 함께 호출된다.
    """
    cached = await get_cached_json(cache, goal_recommendation_age_key(user_id))
    if cached is not None:
        return GoalRecommendation(**cached)

    result = await _compute_age_based_recommendation(cache, db, user_id, settings_row)

    if result.recommended_items:
        await set_cached_json(
            cache, goal_recommendation_age_key(user_id), result.model_dump(mode="json"), TTL_GOAL_RECOMMENDATION
        )
    return result


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
        _fetch_dividend_yields(tickers_only),
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
            is_equity=f_is_equity,
            equity_floor=equity_floor,
            equity_ceiling=equity_ceiling,
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


async def compute_portfolio_expected_metrics(
    cache: CacheStoreType,
    items: list[tuple[str, str, str, float]],  # (ticker, market, name, weight 0~100)
    cagr_lookback_years: int = _DEFAULT_CAGR_LOOKBACK_YEARS,
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
        _fetch_dividend_yields(tickers_only),
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
