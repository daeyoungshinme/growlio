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
from datetime import UTC, date, datetime

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DOMESTIC_MARKETS
from app.models.user import UserSettings
from app.schemas.rebalancing import GoalRecommendation, GoalRecommendationItem
from app.services.dividend_constants import is_korean_etf
from app.services.dividend_sync_sources import (
    sync_naver_etf_dividend_info,
    sync_naver_stock_dividend_info,
    sync_yahoo_dividend_info,
)
from app.services.goal_return_solver import solve_required_annual_return_pct
from app.services.market_data_fetcher import fetch_yf_daily_returns
from app.services.price_service import get_historical_returns
from app.services.recommendation_universe import MAX_GOAL_CANDIDATE_TICKERS, RECOMMENDATION_UNIVERSE
from app.services.yahoo_price import to_yf_symbol
from app.utils.cache_keys import RedisType

logger = structlog.get_logger()

_MAX_WEIGHT = 0.4  # 종목당 최대 비중 상한 (과도한 집중 방지) — 기본값, UserSettings.goal_max_weight_pct로 조정 가능
_MIN_RETURN_DAYS = 30
_MIN_CANDIDATES = 2
_DIVIDEND_FETCH_CONCURRENCY = 8
_DEFAULT_CAGR_LOOKBACK_YEARS = 10
_RISK_TOLERANCE_FRONTIER_FRACTION = {"CONSERVATIVE": 0.0, "BALANCED": 0.4, "AGGRESSIVE": 0.8}


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
) -> tuple[list[dict], float | None, str | None]:
    """분산 최소화 + 목표수익률 제약(SLSQP). (recommended_items, expected_return_pct, note) 반환. 동기 함수.

    `required_return_pct`는 실행가능성 하드체크(달성 불가 판정)에 쓰이는 필요수익률이다.

    CONSERVATIVE(기본값)는 오늘까지의 동작과 동일하게 "필요수익률 이상"이라는 부등식 제약만
    사용해 순수 최소분산 포트폴리오를 찾는다. BALANCED/AGGRESSIVE는 제약 없는 최소분산
    포트폴리오의 "자연 수익률"과 종목당 최대 비중 제약 하에서 달성 가능한 최대 가중평균
    CAGR 사이를 성향 비율(`_RISK_TOLERANCE_FRONTIER_FRACTION`)로 보간한 지점을 **등식 제약**으로
    고정한다 — 부등식과 달리 이미 자연 수익률이 목표를 넘는 경우에도 항상 실제로 비중이
    달라짐을 보장한다.
    """
    import numpy as np
    from scipy.optimize import minimize

    valid = [
        (s, tk, c)
        for s, tk, c in zip(symbols, tickers, cagr_pct, strict=False)
        if s in returns_map and len(returns_map[s]) >= _MIN_RETURN_DAYS
    ]
    if len(valid) < _MIN_CANDIDATES:
        return [], None, f"추천에 충분한 시세 데이터가 있는 종목이 {_MIN_CANDIDATES}개 미만입니다"

    syms, tks, cagrs_list = zip(*valid, strict=False)
    cagrs = np.array(cagrs_list, dtype=float)
    n = len(syms)

    if float(cagrs.max()) < required_return_pct:
        return [], None, f"큐레이션 종목만으로는 목표 수익률(연 {required_return_pct:.1f}%)을 달성하기 어렵습니다"

    min_len = min(len(returns_map[s]) for s in syms)
    rets = np.array([returns_map[s][:min_len] for s in syms])
    cov_annual = np.cov(rets) * 252 if n > 1 else np.array([[float(np.var(rets[0])) * 252]])

    max_weight_used = max(max_weight, 1.0 / n)  # n이 작아 상한 합이 100%를 못 채우면 완화
    bounds = [(0.0, max_weight_used)] * n
    x0 = np.full(n, 1.0 / n)

    # 종목당 비중 상한(max_weight_used) 하에서 달성 가능한 최대 가중평균 CAGR
    # (상한이 없다면 cagrs.max()겠지만, 캡이 있으면 고CAGR 종목에만 몰아줄 수 없으므로 그보다 낮을 수 있음)
    max_achievable_return = 0.0
    remaining = 1.0
    for idx in np.argsort(-cagrs):
        take = min(max_weight_used, remaining)
        max_achievable_return += take * float(cagrs[idx])
        remaining -= take
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


async def get_goal_recommendation(
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

    candidate_dicts = getattr(settings_row, "goal_candidate_tickers", None)
    if candidate_dicts is None:
        candidate_dicts = _seed_candidate_tickers(existing_items)
        settings_row.goal_candidate_tickers = candidate_dicts
        await db.commit()

    if not candidate_dicts:
        return _no_recommendation(
            "등록된 후보 종목이 없습니다 — 후보 ETF를 추가해주세요",
            required_return_pct,
            required_dividend_yield_pct,
        )

    risk_tolerance = getattr(settings_row, "goal_risk_tolerance", None) or "CONSERVATIVE"
    max_weight_pct_raw = getattr(settings_row, "goal_max_weight_pct", None)
    max_weight = float(max_weight_pct_raw) / 100 if max_weight_pct_raw else _MAX_WEIGHT
    cagr_lookback_years = int(getattr(settings_row, "goal_cagr_lookback_years", None) or _DEFAULT_CAGR_LOOKBACK_YEARS)

    candidates = [(c["ticker"], c["name"], c["market"]) for c in candidate_dicts]
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
        return _no_recommendation(
            "추천에 필요한 수익률 데이터를 가져오지 못했습니다",
            required_return_pct,
            required_dividend_yield_pct,
        )

    f_symbols = [f[0] for f in filtered]
    f_tickers = [f[1] for f in filtered]
    f_cagrs = [f[2] for f in filtered]

    loop = asyncio.get_running_loop()
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
        note=opt_note,
        cagr_lookback_years=cagr_lookback_years,
        risk_tolerance=risk_tolerance,
        max_weight_pct=round(max_weight * 100, 2),
    )
