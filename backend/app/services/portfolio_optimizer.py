"""포트폴리오 최적화 서비스 — Mean-Variance Optimization으로 효율적 프론티어 계산.

scipy.optimize.minimize(SLSQP)를 사용하며, 1년 일별 수익률 데이터를 기반으로 한다.
Redis 1시간 캐시를 사용한다.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import math
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.services._snapshot_queries import latest_snapshot_subquery
from app.services.yahoo_price import to_yf_symbol as _to_yf_symbol
from app.utils.cache_keys import RedisType

logger = structlog.get_logger()

_OPTIMIZER_CACHE_TTL = 3600  # 1시간
_MIN_POSITIONS = 2           # 최적화에 필요한 최소 종목 수
_FRONTIER_POINTS = 20        # 효율적 프론티어 산점도 포인트 수
_MIN_RETURN_DAYS = 30        # 최적화에 필요한 최소 수익률 데이터 일수


def _sync_fetch_returns(symbols: list[str]) -> dict[str, list[float]]:
    """1년치 일별 수익률 수집. risk_service._sync_fetch_risk_data와 동일 패턴."""
    from datetime import date, timedelta

    import yfinance as yf

    end = date.today()
    start = end - timedelta(days=365)
    try:
        raw = yf.download(
            symbols,
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as e:
        logger.warning("optimizer_yf_download_failed", error=str(e))
        return {}

    import pandas as pd

    close = raw.get("Close") if isinstance(raw.columns, pd.MultiIndex) else raw
    if close is None or close.empty:
        return {}
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame(name=symbols[0])

    result: dict[str, list[float]] = {}
    for sym in symbols:
        if sym not in close.columns:
            continue
        series = close[sym].dropna()
        if len(series) < 2:
            continue
        returns = series.pct_change().dropna().tolist()
        result[sym] = [float(r) for r in returns if math.isfinite(r)]
    return result


def _compute_frontier(
    symbols: list[str],
    weights: list[float],
    returns_map: dict[str, list[float]],
) -> dict:
    """scipy SLSQP로 효율적 프론티어 계산. 동기 함수."""
    import numpy as np

    try:
        from scipy.optimize import minimize
    except ImportError:
        logger.error("scipy_not_installed")
        return {"frontier": [], "current": None, "assets": [], "note": "scipy 미설치"}

    # 충분한 데이터가 있는 종목만 사용
    valid_pairs = [
        (s, w)
        for s, w in zip(symbols, weights, strict=False)
        if s in returns_map and len(returns_map[s]) >= _MIN_RETURN_DAYS
    ]
    if len(valid_pairs) < _MIN_POSITIONS:
        return {
            "frontier": [],
            "current": None,
            "assets": [],
            "note": (
                f"최적화에 충분한 데이터 없음 "
                f"({_MIN_POSITIONS}종목 이상, {_MIN_RETURN_DAYS}일+ 수익률 필요)"
            ),
        }

    valid_syms, valid_weights = zip(*valid_pairs, strict=False)
    w_arr = np.array(valid_weights, dtype=float)
    w_arr /= w_arr.sum()  # 비중 정규화

    # 공통 기간 수익률 행렬 구성
    min_len = min(len(returns_map[s]) for s in valid_syms)
    rets = np.array([returns_map[s][:min_len] for s in valid_syms])  # (n, T)

    # 연율화 기대수익률 및 공분산 행렬
    mean_annual = rets.mean(axis=1) * 252
    cov_annual = np.cov(rets) * 252

    n = len(valid_syms)
    bounds = [(0.0, 1.0)] * n
    base_constraints = [{"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0}]

    # 현재 포트폴리오 위치
    cur_ret = float(w_arr @ mean_annual) * 100
    cur_vol = float(np.sqrt(w_arr @ cov_annual @ w_arr)) * 100
    current = (
        {"risk": round(cur_vol, 2), "return": round(cur_ret, 2)}
        if math.isfinite(cur_vol) and math.isfinite(cur_ret)
        else None
    )

    # 효율적 프론티어: 목표 수익률 범위에서 최소 분산 포트폴리오 탐색
    ret_min = float(mean_annual.min())
    ret_max = float(mean_annual.max())
    frontier: list[dict] = []
    for target in np.linspace(ret_min, ret_max, _FRONTIER_POINTS):
        cons = base_constraints + [
            {"type": "eq", "fun": lambda w, t=target: float(w @ mean_annual) - float(t)}
        ]
        res = minimize(
            lambda w: float(w @ cov_annual @ w),
            x0=w_arr,
            method="SLSQP",
            bounds=bounds,
            constraints=cons,
            options={"ftol": 1e-9, "maxiter": 500},
        )
        if res.success:
            vol = float(np.sqrt(res.fun)) * 100
            ret = float(target) * 100
            if math.isfinite(vol) and math.isfinite(ret):
                frontier.append({"risk": round(vol, 2), "return": round(ret, 2)})

    # 개별 종목 리스크-수익률
    diag_vol = np.sqrt(np.diag(cov_annual))
    assets = [
        {
            "symbol": s,
            "expected_return_pct": round(float(r) * 100, 2),
            "volatility_pct": round(float(v) * 100, 2),
        }
        for s, r, v in zip(valid_syms, mean_annual, diag_vol, strict=False)
    ]

    return {
        "frontier": frontier,
        "current": current,
        "assets": assets,
        "note": f"1년 일별 수익률 기반 MVO ({min_len}일, {n}종목)",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _compute_portfolio_position(
    symbols: list[str],
    weights: list[float],
    returns_map: dict[str, list[float]],
) -> dict | None:
    """주어진 tickers·weights로 포트폴리오의 (risk, return) 위치를 계산한다."""
    import numpy as np

    valid_pairs = [
        (s, w)
        for s, w in zip(symbols, weights, strict=False)
        if s in returns_map and len(returns_map[s]) >= _MIN_RETURN_DAYS
    ]
    if not valid_pairs:
        return None

    valid_syms, valid_weights = zip(*valid_pairs, strict=False)
    w_arr = np.array(valid_weights, dtype=float)
    total = w_arr.sum()
    if total <= 0:
        return None
    w_arr /= total

    min_len = min(len(returns_map[s]) for s in valid_syms)
    rets = np.array([returns_map[s][:min_len] for s in valid_syms])
    mean_annual = rets.mean(axis=1) * 252
    if len(valid_syms) > 1:
        cov_annual = np.cov(rets) * 252
    else:
        cov_annual = np.array([[float(np.var(rets[0])) * 252]])

    cur_ret = float(w_arr @ mean_annual) * 100
    cur_vol = float(np.sqrt(w_arr @ cov_annual @ w_arr)) * 100
    if not (math.isfinite(cur_vol) and math.isfinite(cur_ret)):
        return None
    return {"risk": round(cur_vol, 2), "return": round(cur_ret, 2)}


async def get_efficient_frontier(  # noqa: C901
    user_id: uuid.UUID,
    db: AsyncSession,
    redis: RedisType = None,
    compare_portfolio_id: str | None = None,
) -> dict:
    """효율적 프론티어 데이터 반환. compare_portfolio_id 지정 시 목표 포트폴리오 위치도 포함."""
    cache_key = f"efficient_frontier:{user_id}:{compare_portfolio_id or ''}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # 최신 스냅샷 포지션 조회 (risk_service와 동일 패턴)
    subq = latest_snapshot_subquery(user_id=user_id)
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id)
            & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(AssetAccount.is_active == True)  # noqa: E712
    )
    rows = result.all()

    snap_ids = [snap.id for snap, _ in rows]
    pos_map: dict[str, dict] = {}
    if snap_ids:
        all_pos_result = await db.execute(
            select(Position).where(Position.snapshot_id.in_(snap_ids))
        )
        for pos in all_pos_result.scalars().all():
            key = f"{pos.ticker}-{pos.market}"
            if key not in pos_map:
                pos_map[key] = {"ticker": pos.ticker, "market": pos.market, "value_krw": 0.0}
            pos_map[key]["value_krw"] += float(pos.value_krw or 0)

    if len(pos_map) < _MIN_POSITIONS:
        return {
            "frontier": [],
            "current": None,
            "target": None,
            "assets": [],
            "note": f"효율적 프론티어는 {_MIN_POSITIONS}종목 이상 필요합니다",
        }

    total_value = sum(p["value_krw"] for p in pos_map.values())
    if total_value <= 0:
        return {
            "frontier": [], "current": None, "target": None,
            "assets": [], "note": "포지션 데이터 없음",
        }

    positions = list(pos_map.values())
    yf_symbols = [_to_yf_symbol(p["ticker"], p["market"]) for p in positions]
    weights = [p["value_krw"] / total_value for p in positions]

    # 비교 포트폴리오 종목 추가 (유니버스 확장)
    compare_symbols: list[str] = []
    compare_weights: list[float] = []
    if compare_portfolio_id:
        from app.models.portfolio import Portfolio
        portfolio = await db.get(
            Portfolio,
            compare_portfolio_id,
            options=[selectinload(Portfolio.items)],
        )
        if portfolio and portfolio.items:
            total_w = sum(float(item.weight) for item in portfolio.items)
            for item in portfolio.items:
                sym = _to_yf_symbol(item.ticker, item.market)
                compare_symbols.append(sym)
                compare_weights.append(float(item.weight) / total_w if total_w > 0 else 0.0)

    # returns 취득: 현재 + 비교 포트폴리오 합집합
    all_symbols = list(dict.fromkeys(yf_symbols + compare_symbols))  # 중복 제거, 순서 유지

    loop = asyncio.get_running_loop()
    returns_map = await loop.run_in_executor(None, _sync_fetch_returns, all_symbols)
    result_data = await loop.run_in_executor(
        None, _compute_frontier, yf_symbols, weights, returns_map
    )

    # 비교 포트폴리오 위치 계산
    target_pos = None
    if compare_symbols and compare_weights:
        target_pos = await loop.run_in_executor(
            None, _compute_portfolio_position, compare_symbols, compare_weights, returns_map
        )
    result_data["target"] = target_pos

    if redis:
        with contextlib.suppress(Exception):
            await redis.setex(cache_key, _OPTIMIZER_CACHE_TTL, json.dumps(result_data))

    return result_data
