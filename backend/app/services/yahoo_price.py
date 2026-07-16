"""Yahoo Finance 종목 가격 조회 유틸리티.

**이 모듈의 책임:** 개별 종목의 현재가·배치 가격·기간 수익률 조회 (종목 단위 I/O).
거시 지표(VIX, 금리차 등)는 market_data_fetcher.py가 담당한다.

티커 변환:
  KOSPI  005930  →  005930.KS
  KOSDAQ 035720  →  035720.KQ
  NYSE/NASDAQ AAPL → AAPL
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog

from app.constants import DOMESTIC_MARKETS
from app.core.config import settings
from app.services.price_sync_sources import sync_pykrx_close_series

if TYPE_CHECKING:
    from datetime import date

logger = structlog.get_logger()

_yfinance_sem = asyncio.Semaphore(settings.api_semaphore_limit)


def to_yf_symbol(ticker: str, market: str) -> str:
    """Yahoo Finance 심볼 변환 (KOSPI/KRX → .KS, KOSDAQ → .KQ, 해외 그대로)."""
    m = market.upper()
    if m in ("KOSPI", "KRX"):
        return f"{ticker.zfill(6)}.KS"
    if m == "KOSDAQ":
        return f"{ticker.zfill(6)}.KQ"
    return ticker


# 내부 별칭 (기존 코드 호환)
def _sync_usdkrw() -> float:
    """동기 함수 — run_in_executor로 호출. 실패 시 0.0 반환."""
    import yfinance as yf

    try:
        hist = yf.Ticker("USDKRW=X").history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            if rate > 0:
                return rate
    except Exception as e:
        logger.warning("usdkrw_fetch_failed", error=str(e))
    return 0.0


def _sync_yahoo_price(ticker: str, market: str) -> float | None:
    """동기 함수 — run_in_executor로 호출."""
    import yfinance as yf

    sym = to_yf_symbol(ticker, market)
    try:
        hist = yf.Ticker(sym).history(period="5d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            return price if price > 0 else None
    except Exception as e:
        logger.warning("yahoo_price_failed", ticker=ticker, symbol=sym, error=str(e))
    return None


def _sync_yahoo_batch(items: list[tuple[str, str]]) -> dict[str, float]:
    """여러 종목을 한 번의 download 호출로 조회. {ticker: price}"""
    import yfinance as yf

    if not items:
        return {}

    sym_map = {to_yf_symbol(t, m): t for t, m in items}
    symbols = list(sym_map.keys())

    for attempt in range(3):
        try:
            data = yf.download(
                symbols,
                period="5d",
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            close = data.get("Close")
            if close is None or (hasattr(close, "empty") and close.empty):
                if attempt < 2:
                    time.sleep(1)
                    continue
                return {}

            result: dict[str, float] = {}
            for sym, orig in sym_map.items():
                try:
                    col = close[sym].dropna()
                    if not col.empty:
                        val = float(col.iloc[-1])
                        if val > 0:
                            result[orig] = val
                except (KeyError, IndexError, ValueError) as e:
                    logger.debug("yahoo_price_parse_skip", sym=sym, error=str(e))
            return result
        except Exception as e:
            logger.warning("yahoo_batch_failed", attempt=attempt + 1, error=str(e))
            if attempt < 2:
                time.sleep(1)
    return {}


def _cagr_from_prices(start_price: float, end_price: float, start_date, end_date) -> dict | None:
    """시작/종료 시점 가격으로 누적수익률·CAGR을 계산한다. 공통 계산 로직(yfinance/pykrx 공용)."""
    if start_price <= 0:
        return None

    actual_years = (end_date - start_date).days / 365.25
    if actual_years < 0.1:
        return None

    cumulative = (end_price / start_price - 1) * 100
    cagr = ((end_price / start_price) ** (1 / actual_years) - 1) * 100
    return {
        "cumulative_return_pct": round(cumulative, 2),
        "cagr_pct": round(cagr, 2),
        "actual_years": round(actual_years, 1),
    }


def _pykrx_calc_return(ticker: str, market: str, start: date, end: date) -> dict | None:
    """국내(KOSPI/KOSDAQ) 종목 전용 pykrx CAGR 폴백 — Yahoo가 실패했거나(클라우드 IP 차단 등)
    회로가 열려 있을 때 사용. 해외 종목은 대체 소스가 없어 항상 None."""
    if market.upper() not in DOMESTIC_MARKETS:
        return None

    series = sync_pykrx_close_series(ticker.zfill(6), start, end)
    if series is None or len(series) < 2:
        return None

    return _cagr_from_prices(float(series.iloc[0]), float(series.iloc[-1]), series.index[0], series.index[-1])


def _sync_calc_returns_batch(items: list[tuple[str, str]], years: int = 10) -> dict[tuple[str, str], dict]:
    """여러 종목의 N년 수익률을 한 번의 yfinance batch download로 계산한다. {(ticker, market): {...}}

    `_sync_yahoo_batch`(현재가)와 동일한 패턴 — 종목별 개별 `yf.Ticker().history()` 호출 대신
    한 번의 `yf.download()`로 묶어 조회 속도를 높이고 Yahoo 요청 수를 줄인다.
    """
    from datetime import date

    import yfinance as yf

    if not items:
        return {}

    end = date.today()
    try:
        start = end.replace(year=end.year - years)
    except ValueError:
        start = end.replace(year=end.year - years, day=28)

    sym_map = {to_yf_symbol(t, m): (t, m) for t, m in items}
    symbols = list(sym_map.keys())

    result: dict[tuple[str, str], dict] = {}
    for attempt in range(3):
        try:
            data = yf.download(
                symbols,
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            close = data.get("Close")
            if close is None or (hasattr(close, "empty") and close.empty):
                if attempt < 2:
                    time.sleep(1)
                    continue
                return result

            for sym, key in sym_map.items():
                try:
                    col = close[sym].dropna()
                    if len(col) < 2:
                        continue
                    r = _cagr_from_prices(float(col.iloc[0]), float(col.iloc[-1]), col.index[0], col.index[-1])
                    if r:
                        result[key] = r
                except (KeyError, IndexError, ValueError) as e:
                    logger.debug("historical_return_batch_parse_skip", sym=sym, error=str(e))
            return result
        except Exception as e:
            logger.warning("historical_return_batch_failed", attempt=attempt + 1, error=str(e))
            if attempt < 2:
                time.sleep(1)
    return result


def _sync_pykrx_returns_batch(items: list[tuple[str, str]], years: int = 10) -> dict[tuple[str, str], dict]:
    """국내 종목 목록의 N년 수익률을 pykrx로 종목별 조회한다. {(ticker, market): {...}}

    pykrx는 진짜 배치 API가 없어 종목별 순차 호출이다 — `market_data_fetcher._pykrx_daily_returns_fallback`과
    동일한 전제. Yahoo가 실패했거나(circuit open 포함) 국내 종목만 대상으로 한다.
    """
    from datetime import date

    if not items:
        return {}

    end = date.today()
    try:
        start = end.replace(year=end.year - years)
    except ValueError:
        start = end.replace(year=end.year - years, day=28)

    result: dict[tuple[str, str], dict] = {}
    for ticker, market in items:
        r = _pykrx_calc_return(ticker, market, start, end)
        if r:
            result[(ticker, market)] = r
    return result
