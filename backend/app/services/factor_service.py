"""팩터 분석 서비스 — Fama-French 3팩터 기반 Value/Size/Momentum/Growth 노출도 계산.

yfinance .info에서 P/E, P/B, 시가총액을 가져와 종목별·포트폴리오 가중 팩터 점수를 반환한다.
1시간 캐시를 사용한다.
"""

from __future__ import annotations

import asyncio
import math
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.schemas.service_dtypes import FactorData
from app.services.market_data_fetcher import fetch_yf_close_series, fetch_yf_info
from app.services.position_aggregator import query_latest_position_map
from app.services.yahoo_price import to_yf_symbol as _to_yf_symbol
from app.utils.cache_keys import (
    TTL_FACTOR_ANALYSIS,
    CacheStoreType,
    factor_analysis_key,
    factor_analysis_portfolio_key,
    get_cached_json,
    set_cached_json,
)

logger = structlog.get_logger()


def _safe_float(v: object) -> float | None:
    try:
        f = float(v)  # type: ignore[arg-type]
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _sync_fetch_factor_data(symbols: list[str]) -> dict[str, FactorData]:
    """yfinance .info에서 P/E, P/B, 시가총액, 12-1M 모멘텀 수집."""
    from datetime import date, timedelta

    # Step 1: 역사 데이터 일괄 다운로드 (모멘텀 계산용, 12-1M = 최근 21일 제외 335일)
    end_date = date.today() - timedelta(days=21)
    start_date = end_date - timedelta(days=335)
    close_series = fetch_yf_close_series(symbols, start_date, end_date)

    momentum_map: dict[str, float | None] = {sym: None for sym in symbols}
    for sym, series in close_series.items():
        if len(series) >= 2:
            raw_mom = float(series.iloc[-1] / series.iloc[0] - 1) * 100
            momentum_map[sym] = round(raw_mom, 2) if math.isfinite(raw_mom) else None

    # Step 2: .info 병렬 조회 (P/E, P/B, 시가총액)
    info_map = fetch_yf_info(symbols)

    # Step 3: 결과 조합
    result: dict[str, FactorData] = {}
    for sym in symbols:
        info = info_map.get(sym, {})
        result[sym] = {
            "pe_ratio": _safe_float(info.get("trailingPE") or info.get("forwardPE")),
            "pb_ratio": _safe_float(info.get("priceToBook")),
            "market_cap": _safe_float(info.get("marketCap")),
            "momentum_pct": momentum_map.get(sym),
        }
    return result


# ---------------------------------------------------------------------------
# 팩터 점수 계산 (0-100)
# ---------------------------------------------------------------------------


def _score_value(pb: float | None, pe: float | None) -> float:
    """Value 점수. 낮은 P/B·P/E = 가치주 = 높은 점수."""
    scores: list[float] = []
    if pb is not None and pb > 0:
        # P/B 0.5 이하 → 100점, 5.0 이상 → 0점
        scores.append(max(0.0, min(100.0, (5.0 - pb) / 4.5 * 100)))
    if pe is not None and 0 < pe < 200:
        # P/E 5 이하 → 100점, 50 이상 → 0점
        scores.append(max(0.0, min(100.0, (50.0 - pe) / 45.0 * 100)))
    return round(sum(scores) / len(scores), 1) if scores else 50.0


def _score_growth(pb: float | None, pe: float | None) -> float:
    """Growth 점수. 높은 P/B·P/E = 성장주 = 높은 점수."""
    scores: list[float] = []
    if pb is not None and pb > 0:
        scores.append(max(0.0, min(100.0, (pb - 0.5) / 4.5 * 100)))
    if pe is not None and 0 < pe < 200:
        scores.append(max(0.0, min(100.0, (pe - 5.0) / 45.0 * 100)))
    return round(sum(scores) / len(scores), 1) if scores else 50.0


def _score_size(market_cap: float | None) -> float:
    """Size 점수 (Small-Cap 지향). 작은 시총 = 높은 점수 (Fama-French SMB 개념)."""
    if market_cap is None or market_cap <= 0:
        return 50.0
    cap_b = market_cap / 1e9  # USD 기준 십억 달러
    # 1B 이하 → 100점, 500B 이상 → 0점
    return round(max(0.0, min(100.0, (500.0 - cap_b) / 499.0 * 100)), 1)


def _score_momentum(momentum_pct: float | None) -> float:
    """Momentum 점수. 높은 12-1M 수익률 = 높은 점수."""
    if momentum_pct is None:
        return 50.0
    # -50% → 0점, +50% → 100점
    return round(max(0.0, min(100.0, (momentum_pct + 50.0) / 100.0 * 100)), 1)


def _build_holdings(
    positions: list[dict],
    yf_symbols: list[str],
    weights: list[float],
    factor_data: dict[str, FactorData],
) -> list[dict]:
    """종목별 팩터 점수를 계산해 holdings 목록을 반환한다."""
    holdings = []
    for pos, sym, w in zip(positions, yf_symbols, weights, strict=False):
        fd = factor_data.get(sym, {})
        pe = fd.get("pe_ratio")
        pb = fd.get("pb_ratio")
        market_cap = fd.get("market_cap")
        momentum = fd.get("momentum_pct")
        holdings.append(
            {
                "ticker": pos["ticker"],
                "name": pos["name"],
                "weight_pct": round(w * 100, 2),
                "pe_ratio": pe,
                "pb_ratio": pb,
                "market_cap": market_cap,
                "momentum_pct": momentum,
                "value_score": _score_value(pb, pe),
                "growth_score": _score_growth(pb, pe),
                "size_score": _score_size(market_cap),
                "momentum_score": _score_momentum(momentum),
            }
        )
    return holdings


def _portfolio_factors(holdings: list[dict]) -> dict:
    """holdings에서 가중 평균 팩터 점수를 계산한다."""

    def _weighted(key: str) -> float:
        return round(sum(h[key] * (h["weight_pct"] / 100) for h in holdings), 1)

    return {
        "value": _weighted("value_score"),
        "growth": _weighted("growth_score"),
        "size": _weighted("size_score"),
        "momentum": _weighted("momentum_score"),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_factor_analysis_for_portfolio(
    portfolio_id: str,
    db: AsyncSession,
    cache: CacheStoreType = None,
) -> dict:
    """저장된 포트폴리오(Portfolio.items)의 팩터 노출도 분석 반환."""
    from app.models.portfolio import Portfolio

    cache_key = factor_analysis_portfolio_key(portfolio_id)

    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return cached

    portfolio = await db.scalar(
        select(Portfolio).options(selectinload(Portfolio.items)).where(Portfolio.id == portfolio_id)
    )
    if not portfolio or not portfolio.items:
        return _empty_factor_result()

    positions = [{"ticker": item.ticker, "market": item.market, "name": item.name} for item in portfolio.items]
    weights = [float(item.weight) / 100.0 for item in portfolio.items]

    total_weight = sum(weights)
    if total_weight <= 0:
        return _empty_factor_result()
    weights = [w / total_weight for w in weights]

    yf_symbols = [_to_yf_symbol(p["ticker"], p["market"]) for p in positions]

    loop = asyncio.get_running_loop()
    factor_data = await loop.run_in_executor(None, _sync_fetch_factor_data, yf_symbols)

    holdings = _build_holdings(positions, yf_symbols, weights, factor_data)
    result_data: dict = {
        "holdings": holdings,
        "portfolio_factors": _portfolio_factors(holdings),
        "position_count": len(positions),
        "portfolio_name": portfolio.name,
        "note": "yfinance 기반 팩터 점수 (0-100, 높을수록 해당 팩터 노출도 높음)",
    }

    await set_cached_json(cache, cache_key, result_data, TTL_FACTOR_ANALYSIS)
    return result_data


async def get_factor_analysis(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStoreType = None,
    account_ids: list[uuid.UUID] | None = None,
) -> dict:
    """포트폴리오 팩터 노출도 분석 반환."""
    acct_suffix = "_".join(sorted(str(a) for a in account_ids)) if account_ids else "all"
    cache_key = factor_analysis_key(user_id, acct_suffix)

    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return cached

    pos_map = await query_latest_position_map(user_id, db, include_name=True, account_ids=account_ids)

    if not pos_map:
        return _empty_factor_result()

    total_value = sum(p["value_krw"] for p in pos_map.values())
    if total_value <= 0:
        return _empty_factor_result()

    positions = list(pos_map.values())
    yf_symbols = [_to_yf_symbol(p["ticker"], p["market"]) for p in positions]
    weights = [p["value_krw"] / total_value for p in positions]

    loop = asyncio.get_running_loop()
    factor_data = await loop.run_in_executor(None, _sync_fetch_factor_data, yf_symbols)

    holdings = _build_holdings(positions, yf_symbols, weights, factor_data)
    result_data: dict = {
        "holdings": holdings,
        "portfolio_factors": _portfolio_factors(holdings),
        "position_count": len(positions),
        "note": "yfinance 기반 팩터 점수 (0-100, 높을수록 해당 팩터 노출도 높음)",
    }

    await set_cached_json(cache, cache_key, result_data, TTL_FACTOR_ANALYSIS)
    return result_data


def _empty_factor_result() -> dict:
    return {
        "holdings": [],
        "portfolio_factors": {"value": 0.0, "growth": 0.0, "size": 0.0, "momentum": 0.0},
        "position_count": 0,
        "note": "포지션 데이터 없음",
    }
