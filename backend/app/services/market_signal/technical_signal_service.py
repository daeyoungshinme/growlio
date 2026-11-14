"""QQQ/SPY/DIA 차트 신호 조회 — 일봉 종가로 기술적 지표 스냅샷을 만들어 캐시한다.

정규장이 끝난 거래일의 종가만 쓴다(장중 일봉은 현재가라 버린다) — 캐시는 6시간, 키에 마지막으로 끝난 거래일이
들어 있어 장 마감 뒤에는 새로 계산한다. Yahoo 실패 시 해당 종목은 trend="UNKNOWN"으로 반환되고
(tactical_allocation_service가 판정 불가로 처리), 실패 결과는 짧게만 캐시한다.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import structlog

from app.services.market_data.market_data_fetcher import fetch_yf_close_series
from app.services.market_data.yahoo_price import run_yf_bounded
from app.services.market_signal.technical_indicators import TechnicalSnapshot, compute_snapshot
from app.utils.cache_keys import (
    TTL_TECHNICAL_SIGNAL,
    TTL_TECHNICAL_SIGNAL_DEGRADED,
    get_cached_json,
    set_cached_json,
    technical_signal_key,
)
from app.utils.kst import today_kst
from app.utils.market_hours import last_completed_us_session

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


def drop_unfinished_bars(closes: dict[str, pd.Series], session: date) -> dict[str, pd.Series]:
    """`session`(마지막으로 끝난 미국 거래일) 뒤의 행을 버린다 — 미국 장중에 받은 당일 일봉은 종가가 아니다.

    그 값으로 추세를 판정하면 07:40 국면 확정이 장중 가격에 기대고 백테스트(확정 종가)와 어긋난다(plans/128 C1).
    """
    out: dict[str, pd.Series] = {}
    for ticker, series in closes.items():
        kept = series[[ts.date() <= session for ts in series.index]]
        if not kept.empty:
            out[ticker] = kept
    return out


async def fetch_close_history(tickers: list[str], days: int) -> dict[str, pd.Series]:
    """확정된 일봉 종가 — 전술 국면·틸트·백테스트가 함께 쓴다."""
    end = today_kst() + timedelta(days=1)  # yfinance end는 배타적
    start = end - timedelta(days=days)
    closes = await run_yf_bounded(fetch_yf_close_series, tickers, start, end)
    return drop_unfinished_bars(closes, last_completed_us_session())


async def get_technical_signals(
    cache: CacheStore | None, tickers: tuple[str, ...] = TACTICAL_TICKERS
) -> dict[str, TechnicalSnapshot]:
    key = technical_signal_key(tickers, last_completed_us_session())
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
