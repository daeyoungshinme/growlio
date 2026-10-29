"""QQQ/SPY/DIA 차트 신호 조회 — 일봉 종가로 기술적 지표 스냅샷을 만들어 캐시한다.

일봉 기준이라 장중 변화가 없으므로 6시간 캐시. Yahoo 실패 시 해당 종목은 trend="UNKNOWN"으로 반환되고
(tactical_allocation_service가 판정 불가로 처리), 실패 결과는 짧게만 캐시한다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import structlog

from app.services.market_data_fetcher import fetch_yf_close_series
from app.services.market_signal.technical_indicators import TechnicalSnapshot, compute_snapshot
from app.services.yahoo_price import run_yf_bounded
from app.utils.cache_keys import (
    TTL_TECHNICAL_SIGNAL,
    TTL_TECHNICAL_SIGNAL_DEGRADED,
    get_cached_json,
    set_cached_json,
    technical_signal_key,
)
from app.utils.kst import today_kst

if TYPE_CHECKING:
    import pandas as pd

    from app.core.cache_store import CacheStore

logger = structlog.get_logger()

TACTICAL_TICKERS: tuple[str, ...] = ("QQQ", "SPY", "DIA")
# 국면 판정에 쓰는 종목 — 이 종목이 실패했을 때만 짧게 캐시한다(DIA는 표시 전용이라 실패해도 정상 TTL)
_REGIME_TICKERS = frozenset({"QQQ", "SPY"})
_HISTORY_DAYS = 420  # 200일선 + 52주 고점 계산에 필요한 거래일(≈252)을 넉넉히 덮는 달력일


def _empty_snapshot() -> TechnicalSnapshot:
    return TechnicalSnapshot(
        close=None,
        sma20=None,
        sma60=None,
        sma120=None,
        sma50=None,
        sma200=None,
        rsi14=None,
        macd_hist=None,
        drawdown_pct=None,
        trend="UNKNOWN",
        pullback_stage="UNKNOWN",
    )


async def fetch_close_history(tickers: list[str], days: int) -> dict[str, pd.Series]:
    end = today_kst() + timedelta(days=1)  # yfinance end는 배타적
    start = end - timedelta(days=days)
    return await run_yf_bounded(fetch_yf_close_series, tickers, start, end)


async def get_technical_signals(
    cache: CacheStore | None, tickers: tuple[str, ...] = TACTICAL_TICKERS
) -> dict[str, TechnicalSnapshot]:
    key = technical_signal_key(tickers)
    cached = await get_cached_json(cache, key)
    if cached:
        return cached

    try:
        closes = await fetch_close_history(list(tickers), _HISTORY_DAYS)
    except Exception as exc:
        logger.warning("technical_signal_fetch_failed", tickers=tickers, error=str(exc))
        closes = {}

    result: dict[str, TechnicalSnapshot] = {
        t: compute_snapshot(closes[t]) if t in closes else _empty_snapshot() for t in tickers
    }
    degraded = any(s["trend"] == "UNKNOWN" for t, s in result.items() if t in _REGIME_TICKERS)
    await set_cached_json(cache, key, result, TTL_TECHNICAL_SIGNAL_DEGRADED if degraded else TTL_TECHNICAL_SIGNAL)
    return result
