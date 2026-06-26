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

import structlog

from app.config import settings

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


def _sync_calc_return(ticker: str, market: str, years: int = 10) -> dict | None:
    """동기 함수 — run_in_executor로 호출. yfinance로 N년 수익률 계산."""
    from datetime import date

    import yfinance as yf

    sym = to_yf_symbol(ticker, market)
    end = date.today()
    try:
        start = end.replace(year=end.year - years)
    except ValueError:
        start = end.replace(year=end.year - years, day=28)

    try:
        hist = yf.Ticker(sym).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
        if hist.empty:
            return None

        close = hist["Close"].dropna()
        if len(close) < 2:
            return None

        start_price = float(close.iloc[0])
        end_price = float(close.iloc[-1])
        if start_price <= 0:
            return None

        actual_years = (close.index[-1] - close.index[0]).days / 365.25
        if actual_years < 0.1:
            return None

        cumulative = (end_price / start_price - 1) * 100
        cagr = ((end_price / start_price) ** (1 / actual_years) - 1) * 100
        return {
            "cumulative_return_pct": round(cumulative, 2),
            "cagr_pct": round(cagr, 2),
            "actual_years": round(actual_years, 1),
        }
    except Exception as e:
        logger.warning("historical_return_failed", ticker=ticker, symbol=sym, error=str(e))
        return None
