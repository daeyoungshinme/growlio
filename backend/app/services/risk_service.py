"""포트폴리오 위험 분석 서비스.

VaR, 베타, 연율화 변동성, 분산도 점수를 계산한다.
yfinance 1년 일별 수익률 데이터를 기반으로 하며 Redis 1시간 캐시를 사용한다.
"""

from __future__ import annotations

import asyncio
import math
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.services._snapshot_queries import latest_snapshot_subquery
from app.services.market_data_fetcher import fetch_yf_daily_returns
from app.services.position_aggregator import query_latest_position_map
from app.services.yahoo_price import to_yf_symbol as _to_yf_symbol
from app.utils.cache_keys import TTL_RISK_ANALYSIS, RedisType, get_cached_json, set_cached_json

logger = structlog.get_logger()
_SP500_SYMBOL = "^GSPC"
DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ", "KRX"}
_MIN_RETURN_POINTS_FOR_CORRELATION = 20  # 상관계수 계산에 필요한 최소 수익률 데이터 포인트


def _sync_fetch_risk_data(
    symbols: list[str],
    extra_symbols: list[str],
) -> dict[str, list[float]]:
    """1년치 일별 수익률(소수, e.g. 0.01=1%) 반환. 동기 함수."""
    return fetch_yf_daily_returns(symbols, extra_symbols=extra_symbols)


def _calc_var(returns: list[float], confidence: float) -> float:
    """Historical VaR (%)."""
    if not returns:
        return 0.0
    sorted_r = sorted(returns)
    idx = max(0, int((1 - confidence) * len(sorted_r)) - 1)
    return abs(sorted_r[idx]) * 100


def _calc_beta(portfolio_rets: list[float], bench_rets: list[float]) -> float:
    n = min(len(portfolio_rets), len(bench_rets))
    if n < 10:
        return 1.0
    p = portfolio_rets[:n]
    b = bench_rets[:n]
    mean_p = sum(p) / n
    mean_b = sum(b) / n
    cov = sum((p[i] - mean_p) * (b[i] - mean_b) for i in range(n)) / (n - 1)
    var_b = sum((b[i] - mean_b) ** 2 for i in range(n)) / (n - 1)
    return cov / var_b if var_b > 0 else 1.0


def _calc_diversification_score(
    symbols: list[str],
    weights: list[float],
    returns_map: dict[str, list[float]],
) -> int:
    """0-100 분산도 점수 (낮은 상관계수 = 높은 점수)."""
    if len(symbols) < 2:
        return 20  # 단일 종목 = 낮은 분산

    # 가중 평균 쌍별 상관계수 계산
    n = len(symbols)
    total_weight = sum(weights)
    if total_weight <= 0:
        return 50

    corr_sum = 0.0
    pair_count = 0
    for i in range(n):
        for j in range(i + 1, n):
            s1, s2 = symbols[i], symbols[j]
            r1 = returns_map.get(s1, [])
            r2 = returns_map.get(s2, [])
            k = min(len(r1), len(r2))
            if k < _MIN_RETURN_POINTS_FOR_CORRELATION:
                continue
            r1 = r1[:k]
            r2 = r2[:k]
            mean1 = sum(r1) / k
            mean2 = sum(r2) / k
            cov = sum((r1[i2] - mean1) * (r2[i2] - mean2) for i2 in range(k)) / (k - 1)
            std1 = math.sqrt(sum((r - mean1) ** 2 for r in r1) / (k - 1)) if k > 1 else 0
            std2 = math.sqrt(sum((r - mean2) ** 2 for r in r2) / (k - 1)) if k > 1 else 0
            if std1 > 0 and std2 > 0:
                corr = cov / (std1 * std2)
                w = (weights[i] + weights[j]) / (2 * total_weight)
                corr_sum += corr * w
                pair_count += 1

    if pair_count == 0:
        return 50

    avg_corr = corr_sum / pair_count  # -1 ~ 1
    # corr -1 → 100점, corr +1 → 0점
    score = int((1 - avg_corr) / 2 * 100)
    return max(0, min(100, score))


async def get_portfolio_risk_metrics(
    user_id: uuid.UUID,
    db: AsyncSession,
    redis: RedisType = None,
    portfolio_id: str | None = None,
) -> dict:
    cache_key = f"risk:{user_id}:{portfolio_id or 'all'}"

    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    # 최신 스냅샷 포지션 조회
    pos_map = await query_latest_position_map(user_id, db)

    if not pos_map:
        return _empty_risk_result()

    total_value = sum(p["value_krw"] for p in pos_map.values())
    if total_value <= 0:
        return _empty_risk_result()

    # 비중 계산 + yfinance 심볼 변환
    positions = list(pos_map.values())
    yf_symbols = [_to_yf_symbol(p["ticker"], p["market"]) for p in positions]
    weights = [p["value_krw"] / total_value for p in positions]

    loop = asyncio.get_running_loop()
    returns_map = await loop.run_in_executor(None, _sync_fetch_risk_data, yf_symbols, [_SP500_SYMBOL])

    # 포트폴리오 가중 수익률 시계열 구성
    min_len = min(
        (len(returns_map[s]) for s in yf_symbols if s in returns_map),
        default=0,
    )
    portfolio_rets: list[float] = []
    if min_len >= 10:
        for i in range(min_len):
            r = 0.0
            for sym, w in zip(yf_symbols, weights, strict=False):
                if sym in returns_map and i < len(returns_map[sym]):
                    r += returns_map[sym][i] * w
            portfolio_rets.append(r)

    # 지표 계산
    var_95 = _calc_var(portfolio_rets, 0.95) if portfolio_rets else 0.0
    var_99 = _calc_var(portfolio_rets, 0.99) if portfolio_rets else 0.0

    n = len(portfolio_rets)
    if n >= 2:
        mean = sum(portfolio_rets) / n
        std = math.sqrt(sum((r - mean) ** 2 for r in portfolio_rets) / (n - 1))
        volatility_pct = std * math.sqrt(252) * 100
    else:
        volatility_pct = 0.0

    beta_sp500 = _calc_beta(portfolio_rets, returns_map.get(_SP500_SYMBOL, []))

    diversification_score = _calc_diversification_score(
        [s for s in yf_symbols if s in returns_map],
        [w for s, w in zip(yf_symbols, weights, strict=False) if s in returns_map],
        returns_map,
    )

    # 집중도 계산 (top 1 비중)
    top_weight_pct = max(weights) * 100 if weights else 0.0

    result_data = {
        "var_95_pct": round(var_95, 2),
        "var_99_pct": round(var_99, 2),
        "annualized_volatility_pct": round(volatility_pct, 2),
        "beta_sp500": round(beta_sp500, 3),
        "diversification_score": diversification_score,
        "top_holding_weight_pct": round(top_weight_pct, 2),
        "position_count": len(positions),
        "data_available": len(portfolio_rets) >= 10,
        "note": "1년 일별 수익률 기반 추정값 (yfinance)" if len(portfolio_rets) >= 10 else "데이터 불충분",
    }

    await set_cached_json(redis, cache_key, result_data, TTL_RISK_ANALYSIS)
    return result_data


def _empty_risk_result() -> dict:
    return {
        "var_95_pct": 0.0,
        "var_99_pct": 0.0,
        "annualized_volatility_pct": 0.0,
        "beta_sp500": 1.0,
        "diversification_score": 0,
        "top_holding_weight_pct": 0.0,
        "position_count": 0,
        "data_available": False,
        "note": "포지션 데이터 없음",
    }


async def get_currency_exposure(
    user_id: uuid.UUID,
    db: AsyncSession,
    redis: RedisType = None,
) -> dict:
    """국내/해외/통화 비중 분석."""
    cache_key = f"currency_exposure:{user_id}"

    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    subq = latest_snapshot_subquery(user_id=user_id)
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .join(subq, (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(AssetAccount.is_active == True)  # noqa: E712
    )
    rows = result.all()

    krw_total = 0.0
    usd_total = 0.0
    other_total = 0.0

    # 배치 조회로 N+1 방지
    snap_ids = [snap.id for snap, _ in rows]
    if snap_ids:
        all_pos_result = await db.execute(select(Position).where(Position.snapshot_id.in_(snap_ids)))
        for pos in all_pos_result.scalars().all():
            val = float(pos.value_krw or 0)
            currency = (pos.currency or "KRW").upper()
            if currency == "KRW":
                krw_total += val
            elif currency == "USD":
                usd_total += val
            else:
                other_total += val

    grand_total = krw_total + usd_total + other_total
    if grand_total <= 0:
        return {"krw_pct": 0, "usd_pct": 0, "other_pct": 0, "krw_value": 0, "usd_value": 0, "other_value": 0}

    data = {
        "krw_value": round(krw_total, 0),
        "usd_value": round(usd_total, 0),
        "other_value": round(other_total, 0),
        "krw_pct": round(krw_total / grand_total * 100, 2),
        "usd_pct": round(usd_total / grand_total * 100, 2),
        "other_pct": round(other_total / grand_total * 100, 2),
    }

    await set_cached_json(redis, cache_key, data, TTL_RISK_ANALYSIS)
    return data
