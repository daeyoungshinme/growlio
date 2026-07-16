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

자동 반영되지 않음 — 프론트엔드에서 사용자가 확인 후 수동으로 포트폴리오 편집기에 적용한다.
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
from app.services.goal_return_solver import solve_required_annual_return_pct
from app.services.market_data_fetcher import fetch_yf_daily_returns
from app.services.portfolio_service import build_portfolio_overview
from app.services.position_aggregator import query_latest_position_map
from app.services.price_service import get_historical_returns
from app.services.recommendation_universe import (
    MAX_GOAL_CANDIDATE_TICKERS,
    RECOMMENDATION_UNIVERSE,
    resolve_index_region,
)
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

_MAX_WEIGHT = 0.4  # 종목당 최대 비중 상한 (과도한 집중 방지) — 기본값, UserSettings.goal_max_weight_pct로 조정 가능
_MIN_RETURN_DAYS = 30
_MIN_CANDIDATES = 2
_DIVIDEND_FETCH_CONCURRENCY = 8
_DEFAULT_CAGR_LOOKBACK_YEARS = 10
_RISK_TOLERANCE_FRONTIER_FRACTION = {"CONSERVATIVE": 0.0, "BALANCED": 0.4, "AGGRESSIVE": 0.8}

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
_TAX_TYPE_MARKET_GROUP: dict[str, str] = {
    "GENERAL": "DOMESTIC",
    "ISA": "DOMESTIC",
    "PENSION_SAVINGS": "DOMESTIC",
    "IRP": "DOMESTIC",
    "OVERSEAS_DEDICATED": "OVERSEAS",
}
"""세제유형별 투자 가능 시장 — ISA/연금저축/IRP/일반 계좌는 국내(국내주식+국내ETF)만,
해외전용 계좌는 해외(해외주식+해외ETF)만 추천 후보로 허용한다."""
_TAX_TYPE_INDEX_REGION_PREFERENCE: dict[str, str] = {
    "GENERAL": "DOMESTIC",
    "ISA": "OVERSEAS",
    "PENSION_SAVINGS": "OVERSEAS",
    "IRP": "OVERSEAS",
    "OVERSEAS_DEDICATED": "OVERSEAS",
}
"""세제유형별 선호 추종지수 지역(EQUITY 후보 한정) — ISA/연금저축/IRP는 국내상장이지만 해외지수를
추종하는 ETF(나스닥100 등)를, 일반 계좌는 국내지수를 추종하는 종목/ETF를 우선 추천한다.
`_TAX_TYPE_MARKET_GROUP`(상장거래소 기준)과 달리 이건 추종지수 기준이라 별개 축이다.
OVERSEAS_DEDICATED도 이 맵에 포함하는 이유는 선호 지역 좁히기가 아니라 `_apply_index_region_preference`의
큐레이션 보강(등록 후보 부족 시 `RECOMMENDATION_UNIVERSE`에서 자동 추가) 경로를 태우기 위함이다 —
`preferred_equity` 계산에서 OVERSEAS_DEDICATED는 항상 상장거래소가 해외인 후보만 통과하도록 별도
조건을 추가로 강제하므로(아래 `_apply_index_region_preference` 참고), KRX 상장·해외지수 추종 ETF가
이 세제유형 후보로 섞여 들어가지는 않는다."""
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


def _apply_index_region_preference(
    candidates: list[dict[str, str]], tax_type_value: str, capacity_remaining: int
) -> tuple[list[dict[str, str]], str | None, list[dict[str, str]]]:
    """EQUITY 후보를 세제유형별 선호 추종지수 지역으로 좁힌다. BOND/CASH는 영향받지 않는다.

    선호 지역에 맞는 EQUITY 후보가 사용자 등록 목록에 하나도 없으면(예: ISA인데 해외지수 추종
    ETF 미등록), 큐레이션 유니버스(`RECOMMENDATION_UNIVERSE`)에서 선호 지역·해당 세제유형이
    투자 가능한 시장에 맞는 ETF를 찾아 자동 보강한다 — 사용자가 직접 등록하지 않아도 항상
    선호 지역 위주로 추천되도록 하기 위함. 보강된 후보는 세 번째 반환값(`added`)으로 함께
    돌려주며, 호출측이 이를 `UserSettings.goal_candidate_tickers`에도 실제로 등록해 "후보 ETF
    관리" 화면에 반영해야 한다 — 계산에만 쓰이고 등록 목록엔 안 보이면 사용자가 당황하기 때문.

    `capacity_remaining`(등록 가능 잔여 슬롯, `MAX_GOAL_CANDIDATE_TICKERS - 전체 등록 후보 수`)보다
    보강 후보가 많아 전부 등록할 수 없으면(등록 한도 초과) 보강 자체를 포기한다 — 계산에 쓰인
    후보와 실제 등록되는 후보가 항상 일치하도록 하기 위한 전부 아니면 전무 규칙. 큐레이션 보강도
    실패하거나 포기되면(안전장치) 원본 후보 목록을 그대로 반환하고 `added=[]`.
    """
    preferred_region = _TAX_TYPE_INDEX_REGION_PREFERENCE.get(tax_type_value)
    if not preferred_region:
        return candidates, None, []

    non_equity = [c for c in candidates if c.get("asset_class", "EQUITY") != "EQUITY"]
    equity_candidates = [c for c in candidates if c.get("asset_class", "EQUITY") == "EQUITY"]
    preferred_equity = [
        c
        for c in equity_candidates
        if resolve_index_region(c["ticker"], c["market"], c.get("index_region")) == preferred_region
        # OVERSEAS_DEDICATED는 추종지수가 아니라 상장거래소가 실제 매수 가능 여부를 결정한다 — KRX
        # 상장·해외지수 추종 ETF(예: TIGER 미국나스닥100)가 index_region=OVERSEAS로 태그돼 있어도
        # 이 세제유형 계좌에서는 매수할 수 없으므로 항상 제외한다. get_horizon_recommendations는
        # 호출 전에 이미 시장으로 후보를 걸러주지만, get_goal_recommendation(전체 탭)은 그런 사전
        # 필터링이 없어 이 함수 자체가 강제하지 않으면 새어 들어갈 수 있다.
        and (tax_type_value != "OVERSEAS_DEDICATED" or c["market"].upper() not in DOMESTIC_MARKETS)
    ]

    if preferred_equity:
        return preferred_equity + non_equity, None, []
    if not equity_candidates:
        # 애초에 EQUITY 후보가 하나도 없던 경우(예: 시장그룹 필터에서 전부 걸러짐) — 이 함수의
        # 관심사(등록은 했지만 지역이 안 맞음)가 아니므로 큐레이션 보강 없이 그대로 통과시킨다.
        return candidates, None, []

    region_label = "해외지수 추종 ETF" if preferred_region == "OVERSEAS" else "국내지수 추종 종목/ETF"
    market_group = _TAX_TYPE_MARKET_GROUP.get(tax_type_value, "DOMESTIC")
    seen = {(c["ticker"], c["market"]) for c in candidates}
    curated_fallback = [
        c
        for c in RECOMMENDATION_UNIVERSE
        if c.get("asset_class", "EQUITY") == "EQUITY"
        and resolve_index_region(c["ticker"], c["market"], c.get("index_region")) == preferred_region
        and (c["market"].upper() in DOMESTIC_MARKETS) == (market_group == "DOMESTIC")
        and (c["ticker"], c["market"]) not in seen
    ]
    if curated_fallback and len(curated_fallback) <= capacity_remaining:
        note = (
            f"등록된 후보 중 {region_label}가 없어 큐레이션 ETF를 후보 목록에 자동 등록했습니다 — "
            "후보 ETF 관리에서 확인·삭제할 수 있습니다"
        )
        return curated_fallback + non_equity, note, curated_fallback

    note = (
        f"등록된 후보 중 {region_label}가 없어 전체 후보로 대체 추천합니다 — 후보 ETF 관리에서 지역 태그를 확인해주세요"
    )
    return candidates, note, []


def _cash_equivalent_daily_returns() -> list[float]:
    """변동성 0으로 가정한 합성 일별수익률 시계열 — MVO 공분산 계산에 참여시키기 위함."""
    return [_CASH_EQUIVALENT_CAGR_PCT / 100 / _CASH_EQUIVALENT_RETURN_DAYS] * _CASH_EQUIVALENT_RETURN_DAYS


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


def _optimize_goal_portfolio(
    symbols: list[str],
    tickers: list[tuple[str, str, str]],  # (ticker, name, market)
    cagr_pct: list[float],
    returns_map: dict[str, list[float]],
    required_return_pct: float,
    max_weight: float = _MAX_WEIGHT,
    risk_tolerance: str = "CONSERVATIVE",
    is_equity: list[bool] | None = None,
    equity_floor: float | None = None,
    equity_ceiling: float | None = None,
) -> tuple[list[dict], float | None, str | None]:
    """분산 최소화 + 목표수익률 제약(SLSQP). (recommended_items, expected_return_pct, note) 반환. 동기 함수.

    `required_return_pct`는 실행가능성 하드체크(달성 불가 판정)에 쓰이는 필요수익률이다.

    CONSERVATIVE(기본값)는 오늘까지의 동작과 동일하게 "필요수익률 이상"이라는 부등식 제약만
    사용해 순수 최소분산 포트폴리오를 찾는다. BALANCED/AGGRESSIVE는 제약 없는 최소분산
    포트폴리오의 "자연 수익률"과 종목당 최대 비중 제약 하에서 달성 가능한 최대 가중평균
    CAGR 사이를 성향 비율(`_RISK_TOLERANCE_FRONTIER_FRACTION`)로 보간한 지점을 **등식 제약**으로
    고정한다 — 부등식과 달리 이미 자연 수익률이 목표를 넘는 경우에도 항상 실제로 비중이
    달라짐을 보장한다.

    `is_equity`+`equity_floor`가 함께 주어지면(단기 추천 전용) "주식 비중 합 ≥ equity_floor"
    부등식 제약을 추가한다 — 총합=1 제약과 결합되면 "안전자산 비중 ≤ 1-equity_floor"도 자동
    성립한다. 후보가 전부 주식이거나 전부 비주식이면(비교 대상이 없어 제약이 무의미) 무시한다.

    `is_equity`+`equity_ceiling`이 함께 주어지면(IRP 추천 전용) `equity_floor`와 대칭으로
    "주식 비중 합 ≤ equity_ceiling" 부등식 제약을 추가한다 — 총합=1 제약과 결합되면 "안전자산
    비중 ≥ 1-equity_ceiling"도 자동 성립한다. 호출측은 `equity_floor`와 `equity_ceiling`을
    동시에 넘기지 않는다(IRP는 단기 주식 하한 규칙보다 우선하므로 상호 배타적으로 세팅됨).
    """
    import numpy as np
    from scipy.optimize import minimize

    equity_flags_in = is_equity or [False] * len(symbols)
    valid = [
        (s, tk, c, eq)
        for s, tk, c, eq in zip(symbols, tickers, cagr_pct, equity_flags_in, strict=False)
        if s in returns_map and len(returns_map[s]) >= _MIN_RETURN_DAYS
    ]
    if len(valid) < _MIN_CANDIDATES:
        return [], None, f"추천에 충분한 시세 데이터가 있는 종목이 {_MIN_CANDIDATES}개 미만입니다"

    syms, tks, cagrs_list, equity_flags = zip(*valid, strict=False)
    cagrs = np.array(cagrs_list, dtype=float)
    n = len(syms)

    if float(cagrs.max()) < required_return_pct:
        return [], None, f"큐레이션 종목만으로는 목표 수익률(연 {required_return_pct:.1f}%)을 달성하기 어렵습니다"

    min_len = min(len(returns_map[s]) for s in syms)
    rets = np.array([returns_map[s][:min_len] for s in syms])
    cov_annual = np.cov(rets) * 252 if n > 1 else np.array([[float(np.var(rets[0])) * 252]])

    max_weight_used = max(max_weight, 1.0 / n)  # n이 작아 상한 합이 100%를 못 채우면 완화

    n_equity = sum(equity_flags)
    apply_equity_floor = equity_floor is not None and equity_floor > 0 and 0 < n_equity < n
    apply_equity_ceiling = equity_ceiling is not None and equity_ceiling < 1.0 and 0 < n_equity < n
    if apply_equity_floor:
        assert equity_floor is not None  # nosec B101 — apply_equity_floor 가드로 이미 None 아님 보장, mypy 타입 내로잉용
        # 주식 후보가 적어도(예: 1개) 하한을 채울 수 있도록 주식 종목당 상한을 별도로 완화
        equity_cap = max(max_weight_used, equity_floor / n_equity)
        bounds = [(0.0, equity_cap if eq else max_weight_used) for eq in equity_flags]
    elif apply_equity_ceiling:
        assert equity_ceiling is not None  # nosec B101 — apply_equity_ceiling 가드로 이미 None 아님 보장, mypy 타입 내로잉용
        # 비주식(안전자산) 후보가 적어도(예: 1개) 하한(1-equity_ceiling)을 채울 수 있도록 비주식
        # 종목당 상한을 별도로 완화 — apply_equity_floor의 equity_cap과 대칭.
        n_non_equity = n - n_equity
        non_equity_cap = max(max_weight_used, (1.0 - equity_ceiling) / n_non_equity)
        bounds = [(0.0, max_weight_used if eq else non_equity_cap) for eq in equity_flags]
    else:
        bounds = [(0.0, max_weight_used)] * n
    x0 = np.full(n, 1.0 / n)

    # 종목당 비중 상한(bounds) 하에서 달성 가능한 최대 가중평균 CAGR — equity_floor/equity_ceiling이
    # 걸려 있으면 해당 그룹(주식/비주식)의 합산 상한도 함께 지켜야 한다. 그렇지 않으면 BALANCED/
    # AGGRESSIVE 성향의 프론티어 목표(target)가 그 그룹 제약과 동시에 만족 불가능한 지점으로
    # 계산돼 옵티마이저가 실패할 수 있다(예: IRP 안전자산 30% 하한 + LONG_TERM AGGRESSIVE 조합).
    # 상한이 없다면 cagrs.max()겠지만, 캡이 있으면 고CAGR 종목에만 몰아줄 수 없으므로 그보다 낮을 수 있음.
    equity_budget: float = equity_ceiling if apply_equity_ceiling and equity_ceiling is not None else 1.0
    non_equity_budget: float = 1.0 - equity_floor if apply_equity_floor and equity_floor is not None else 1.0
    group_budget = {True: equity_budget, False: non_equity_budget}
    group_used = {True: 0.0, False: 0.0}
    max_achievable_return = 0.0
    remaining = 1.0
    for idx in np.argsort(-cagrs):
        is_eq = bool(equity_flags[idx])
        take = max(min(bounds[idx][1], remaining, group_budget[is_eq] - group_used[is_eq]), 0.0)
        max_achievable_return += take * float(cagrs[idx])
        remaining -= take
        group_used[is_eq] += take
        if remaining <= 1e-9:
            break

    note: str | None = None
    frontier_frac = _RISK_TOLERANCE_FRONTIER_FRACTION.get(risk_tolerance, 0.0)

    if frontier_frac <= 0.0:
        # CONSERVATIVE(또는 미인식 값) — 기존과 동일한 코드 경로, 순수 최소분산 + 부등식 제약
        constraints = [
            {"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0},
            {"type": "ineq", "fun": lambda w: float(w @ cagrs) - required_return_pct},
        ]
    else:
        baseline_res = minimize(
            lambda w: float(w @ cov_annual @ w),
            x0=x0,
            method="SLSQP",
            bounds=bounds,
            constraints=[{"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0}],
            options={"ftol": 1e-9, "maxiter": 500},
        )
        natural_return = float(baseline_res.x @ cagrs) if baseline_res.success else required_return_pct

        frontier_low = max(natural_return, required_return_pct)
        frontier_high = max_achievable_return
        target = frontier_low + frontier_frac * max(frontier_high - frontier_low, 0.0)
        target = min(max(target, required_return_pct), frontier_high)

        if frontier_high - frontier_low < 1e-6:
            note = "선택한 리스크 성향을 반영하기에는 후보 종목 간 기대수익률 차이가 크지 않습니다"

        constraints = [
            {"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0},
            {"type": "eq", "fun": lambda w: float(w @ cagrs) - target},
        ]
    if apply_equity_floor or apply_equity_ceiling:
        equity_mask = np.array(equity_flags, dtype=bool)
        if apply_equity_floor:
            assert equity_floor is not None  # nosec B101 — apply_equity_floor 가드로 이미 None 아님 보장, mypy 타입 내로잉용
            constraints = [
                *constraints,
                {"type": "ineq", "fun": lambda w: float(w[equity_mask].sum()) - equity_floor},
            ]
        if apply_equity_ceiling:
            assert equity_ceiling is not None  # nosec B101 — apply_equity_ceiling 가드로 이미 None 아님 보장, mypy 타입 내로잉용
            constraints = [
                *constraints,
                {"type": "ineq", "fun": lambda w: equity_ceiling - float(w[equity_mask].sum())},
            ]
    res = minimize(
        lambda w: float(w @ cov_annual @ w),
        x0=x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 500},
    )
    if not res.success:
        return [], None, "제약 조건을 만족하는 포트폴리오를 찾지 못했습니다"

    weights = res.x
    expected_return = round(float(weights @ cagrs), 2)

    items = [
        {"ticker": tk[0], "name": tk[1], "market": tk[2], "weight": round(float(w) * 100, 1)}
        for tk, w in zip(tks, weights, strict=False)
        if w >= 0.005
    ]
    total = sum(i["weight"] for i in items)
    if items and abs(total - 100) > 0.01:
        items[0]["weight"] = round(items[0]["weight"] + (100 - total), 1)

    return items, expected_return, note


def existing_items_from_positions(pos_map: dict[str, dict]) -> list[tuple[str, str, str]]:
    """전체 계좌 실제 보유 포지션(query_latest_position_map 결과)을 추천 후보 시드로 사용."""
    return [
        (p["ticker"], p.get("name") or p["ticker"], p["market"])
        for p in pos_map.values()
        if p["ticker"] != "CASH" and p["market"] != "KR_PROPERTY"
    ]


def _seed_candidate_tickers(existing_items: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    """후보를 한 번도 등록한 적 없을 때 초기 후보(보유종목 + 큐레이션 ETF)를 구성한다.

    보유 종목을 우선 채우고 남는 자리를 큐레이션 ETF로 채우되, `MAX_GOAL_CANDIDATE_TICKERS`를
    넘지 않는다 — 저장 시 `GoalCandidateTickersUpdate` 검증(최대 개수)을 통과해야 하기 때문.
    """
    seen: set[tuple[str, str]] = set()
    seed: list[dict[str, str]] = []
    for t, name, m in existing_items:
        if len(seed) >= MAX_GOAL_CANDIDATE_TICKERS:
            break
        if (t, m) in seen:
            continue
        seen.add((t, m))
        seed.append({"ticker": t, "name": name, "market": m})
    for c in RECOMMENDATION_UNIVERSE:
        if len(seed) >= MAX_GOAL_CANDIDATE_TICKERS:
            break
        if (c["ticker"], c["market"]) in seen:
            continue
        seen.add((c["ticker"], c["market"]))
        seed.append(c)
    return seed


async def _persist_added_candidates(
    db: AsyncSession, user_id: uuid.UUID, added: list[dict[str, str]]
) -> list[dict[str, str]]:
    """`added`를 잠금 후 재조회한 최신 `goal_candidate_tickers`에 병합해 커밋한다.

    `/goal-recommendation`과 `/goal-recommendation/by-horizon`은 완전히 독립된 요청·DB세션으로,
    둘 다 세제유형 선호 지수 지역에 맞는 큐레이션 ETF를 동시에 추가하려 할 수 있다. 각자 요청 시작
    시점에 읽은 스냅샷을 그대로 덮어쓰면 나중에 커밋하는 쪽이 먼저 커밋된 추가분을 지워버리는
    lost-update가 발생한다 — `with_for_update()`로 행을 잠그고 그 시점의 최신 값을 다시 읽어
    병합해야 두 요청의 추가분이 모두 살아남는다.

    `populate_existing=True`가 반드시 필요하다 — `settings_row`는 이 함수 호출 전에 이미 같은
    세션에서 한 번 로드돼 identity map에 올라가 있으므로, 이 옵션 없이 동일 PK를 다시 select하면
    SQLAlchemy는 DB에서 잠금만 걸 뿐 Python 객체 속성은 갱신하지 않고 기존(스테일한) 객체를
    그대로 반환한다 — 그러면 아래 `current`가 여전히 요청 시작 시점의 낡은 값이 되어 락을 걸어도
    lost-update가 재발한다.
    """
    locked_row = await db.scalar(
        select(UserSettings)
        .where(UserSettings.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_row is None:
        return added
    current = locked_row.goal_candidate_tickers or []
    seen = {(c["ticker"], c["market"]) for c in current}
    merged = current + [c for c in added if (c["ticker"], c["market"]) not in seen]
    if len(merged) > MAX_GOAL_CANDIDATE_TICKERS:
        merged = merged[:MAX_GOAL_CANDIDATE_TICKERS]
    locked_row.goal_candidate_tickers = merged
    await db.commit()
    return merged


async def _get_or_seed_candidates(
    db: AsyncSession,
    settings_row: UserSettings,
    existing_items: list[tuple[str, str, str]],
) -> list[dict[str, str]]:
    """등록된 후보 목록을 반환하거나, 한 번도 등록한 적 없으면 시딩 후 커밋한다.

    최초 시딩도 두 목표 역산 엔드포인트가 동시에 트리거할 수 있으므로 락을 걸고 재확인한다
    (`_persist_added_candidates`와 동일한 lost-update 방지 목적 — `populate_existing=True`가
    빠지면 이미 로드된 `settings_row`의 스테일한 속성이 그대로 반환되어 락이 무의미해진다).
    """
    candidate_dicts = getattr(settings_row, "goal_candidate_tickers", None)
    if candidate_dicts is None:
        user_id = getattr(settings_row, "user_id", None)
        locked_row = (
            await db.scalar(
                select(UserSettings)
                .where(UserSettings.user_id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if user_id is not None
            else None
        )
        candidate_dicts = locked_row.goal_candidate_tickers if locked_row is not None else None
        if candidate_dicts is None:
            candidate_dicts = _seed_candidate_tickers(existing_items)
            target_row = locked_row if locked_row is not None else settings_row
            target_row.goal_candidate_tickers = candidate_dicts
            await db.commit()
    return candidate_dicts


async def _active_account_tax_types(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """활성 계좌들의 tax_type 목록을 조회한다 (전체 탭의 단일세제유형 판별용)."""
    rows = (
        (
            await db.execute(
                select(AssetAccount.tax_type).where(
                    AssetAccount.user_id == user_id,
                    AssetAccount.is_active == True,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


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

    cagr_map, dividend_map = await asyncio.gather(
        get_historical_returns(tickers_only, redis=redis, years=cagr_lookback_years),
        _fetch_dividend_yields(tickers_only),
    )

    filtered = [
        (to_yf_symbol(t, m), (t, name, m), cagr_map[(t, m)]["cagr_pct"])
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
    preference_fallback_note: str | None = None,
) -> HorizonGoalRecommendation:
    """필터링된(자산군·시장 적합) 후보 목록으로 (기간, 세제유형) 조합 하나에 대한 추천을 계산한다.

    SHORT_TERM은 등록된 BOND/CASH 후보 개수와 무관하게 현금성 자산(CMA·파킹통장) 합성 후보를 항상
    함께 분석 대상에 포함시켜, 실제 등록 후보가 없으면 100% 현금성 자산으로, 있으면 그 후보들과
    나란히 MVO로 비중을 분배한다. 등록된 주식(EQUITY) 후보가 있으면 `short_term_equity_floor`
    비율 이상을 주식에 배분하도록 강제해 지나치게 안전자산 위주로 수렴하지 않게 한다.

    IRP(개인형퇴직연금)는 투자기간과 무관하게 이 현금성 자산 안전판을 항상 포함시키고, 대신
    `_DEFAULT_IRP_SAFE_ASSET_FLOOR_PCT`(안전자산 최소 30%) 제약을 적용한다 — 퇴직연금 규제(위험자산
    투자한도 70%)에 근거한 고정 규칙이라 SHORT_TERM의 주식 최소 80% 규칙보다 우선한다(동시에
    적용 시 상호 모순이라 IRP 조합에서는 단기 주식 하한 규칙 자체를 적용하지 않는다).

    `preference_fallback_note`는 세제유형별 추종지수 선호 필터(`get_horizon_recommendations`)가
    선호 지역 후보 부족으로 전체 후보로 되돌아갔을 때 그 사실을 안내하기 위해 전달된다 — 이후
    계산되는 다른 note와 함께(있으면 앞에 붙여) 표시된다.
    """
    is_irp = tax_type == AccountTaxType.IRP.value
    include_cash_equivalent = horizon == "SHORT_TERM" or is_irp

    def _combine_note(msg: str | None) -> str | None:
        if preference_fallback_note and msg:
            return f"{preference_fallback_note} {msg}"
        return preference_fallback_note or msg

    if not include_cash_equivalent and len(eligible_candidates) < _MIN_CANDIDATES:
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
            note=_combine_note("추천에 필요한 수익률 데이터를 가져오지 못했습니다"),
        )

    if len(filtered) == 1:
        # 등록된 실 후보가 하나도 유효하지 않아 현금성 자산 합성 후보만 남은 경우 — 옵티마이저 없이 전액 배분
        _, (tk, name, mk), cagr, _ = filtered[0]
        return HorizonGoalRecommendation(
            investment_horizon=horizon,
            tax_type=tax_type,
            base_krw=base_krw,
            account_count=len(account_ids),
            recommended_items=[GoalRecommendationItem(ticker=tk, name=name, market=mk, weight=100.0)],
            expected_return_pct=cagr,
            risk_tolerance=risk_tolerance,
            max_weight_pct=round(max_weight * 100, 2),
            includes_cash_equivalent=True,
            note=_combine_note(
                "채권/현금성 ETF 후보가 등록되어 있지 않아 현금성 자산(CMA·파킹통장 등)으로 전액 "
                "배분을 권장합니다. 후보 ETF 관리에서 채권/현금성 ETF를 등록하면 함께 분석해 비중을 조정합니다."
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
                preference_fallback_note,
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
