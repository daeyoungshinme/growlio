"""국내 종목 현재가 조회 — Naver Finance / pykrx 소스.

Yahoo Finance가 클라우드 호스팅(Render 등) IP를 차단해 401을 반환하는 경우를 대비한
국내 종목(KOSPI/KOSDAQ) 전용 폴백 소스. 해외 종목은 Naver 모바일 API가 지원하지 않아
대상에서 제외한다 (`m.stock.naver.com/api/stock/{symbol}/basic`은 국내 종목만 응답).

모든 함수는 동기(sync)이며 asyncio run_in_executor로 호출한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.utils.kst import today_kst
from app.utils.naver_retry import NAVER_FAILURES, log_naver_failure, naver_get_json
from app.utils.pykrx_util import quiet_pykrx

if TYPE_CHECKING:
    from datetime import date

    import pandas as pd

logger = structlog.get_logger()


def yf_symbol_to_krx_ticker(symbol: str) -> str | None:
    """`005930.KS`/`035720.KQ` 형태의 yfinance 심볼을 KRX 6자리 티커로 변환.

    국내 심볼이 아니면(해외 종목·지수 등) None을 반환한다.
    """
    if symbol.endswith((".KS", ".KQ")):
        return symbol.split(".")[0]
    return None


def sync_fdr_kosdaq_tickers() -> frozenset[str] | None:
    """FinanceDataReader로 KOSDAQ 상장 종목 6자리 코드 집합 조회. 실패·빈 결과면 None.

    pykrx `get_market_ticker_list`는 KRX 로그인 요구 이후 빈 결과로 깨져 쓰지 않는다.
    """
    try:
        import FinanceDataReader as fdr

        df = fdr.StockListing("KOSDAQ")
        if df is None or df.empty or "Code" not in df.columns:
            return None
        codes = frozenset(str(c).zfill(6) for c in df["Code"] if c)
        return codes or None
    except Exception as e:
        logger.warning("fdr_kosdaq_listing_failed", error=str(e))
        return None


def sync_naver_price(ticker: str) -> float | None:
    """Naver Finance 모바일 API(basic)로 국내 종목 현재가(종가) 조회. 국내 종목 전용."""
    try:
        raw_price = naver_get_json(ticker, "basic").get("closePrice")
        if not raw_price:
            return None
        price = float(str(raw_price).replace(",", ""))
        return price if price > 0 else None
    except NAVER_FAILURES as exc:
        log_naver_failure("naver_price", ticker, exc)
        return None


def sync_pykrx_price(ticker: str) -> float | None:
    """pykrx로 국내 종목 최근 종가 조회. KRX 로그인 불필요."""
    from datetime import timedelta

    try:
        with quiet_pykrx() as stock:
            today = today_kst()
            end = today.strftime("%Y%m%d")
            start = (today - timedelta(days=10)).strftime("%Y%m%d")
            df = stock.get_market_ohlcv_by_date(start, end, ticker)
        if df is None or df.empty:
            return None

        close_col = next((c for c in ["종가", "Close"] if c in df.columns), None)
        if close_col is None:
            return None

        price = float(df[close_col].iloc[-1])
        return price if price > 0 else None
    except Exception as e:
        logger.warning("pykrx_price_failed", ticker=ticker, error=str(e))
        return None


def sync_pykrx_close_series(ticker: str, start: date, end: date) -> pd.Series | None:
    """pykrx로 국내 종목의 기간별 종가 Series 조회 (백테스트/팩터/리스크 폴백용)."""
    try:
        with quiet_pykrx() as stock:
            df = stock.get_market_ohlcv_by_date(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker)
        if df is None or df.empty:
            return None

        close_col = next((c for c in ["종가", "Close"] if c in df.columns), None)
        if close_col is None:
            return None

        series = df[close_col].astype(float)
        series = series[series > 0]
        return series if not series.empty else None
    except Exception as e:
        logger.warning("pykrx_close_series_failed", ticker=ticker, error=str(e))
        return None
