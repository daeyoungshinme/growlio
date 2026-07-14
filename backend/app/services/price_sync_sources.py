"""국내 종목 현재가 조회 — Naver Finance / pykrx 소스.

Yahoo Finance가 클라우드 호스팅(Render 등) IP를 차단해 401을 반환하는 경우를 대비한
국내 종목(KOSPI/KOSDAQ) 전용 폴백 소스. 해외 종목은 Naver 모바일 API가 지원하지 않아
대상에서 제외한다 (`m.stock.naver.com/api/stock/{symbol}/basic`은 국내 종목만 응답).

모든 함수는 동기(sync)이며 asyncio run_in_executor로 호출한다.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

if TYPE_CHECKING:
    from datetime import date

    import pandas as pd

logger = structlog.get_logger()

_pykrx_lock = threading.Lock()
"""pykrx는 동시(멀티스레드) 호출에 안전하지 않아 프로세스 크래시가 관측됐다 — 여러 조합/종목이
run_in_executor로 동시에 pykrx를 호출할 수 있는 모든 경로(목표 역산 기간별 추천 등)에서 이 락으로
호출을 완전히 직렬화한다. threading.Lock을 쓰는 이유: 이 함수들은 실행기 워커 스레드에서 도는
동기 함수이므로 asyncio.Lock/Semaphore가 아니라 스레드 락이 맞다."""


def yf_symbol_to_krx_ticker(symbol: str) -> str | None:
    """`005930.KS`/`035720.KQ` 형태의 yfinance 심볼을 KRX 6자리 티커로 변환.

    국내 심볼이 아니면(해외 종목·지수 등) None을 반환한다.
    """
    if symbol.endswith((".KS", ".KQ")):
        return symbol.split(".")[0]
    return None


_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

_NAVER_RETRY = dict(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)


def sync_naver_price(ticker: str) -> float | None:
    """Naver Finance 모바일 API(basic)로 국내 종목 현재가(종가) 조회. 국내 종목 전용."""
    import requests as _req
    import requests.exceptions as _req_exc

    @retry(**_NAVER_RETRY)  # type: ignore[call-overload]
    def _fetch() -> _req.Response:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/basic"
        r = _req.get(url, headers={"User-Agent": _MOBILE_UA}, timeout=10)
        r.raise_for_status()
        return r

    try:
        resp = _fetch()
        raw_price = resp.json().get("closePrice")
        if not raw_price:
            return None
        price = float(str(raw_price).replace(",", ""))
        return price if price > 0 else None
    except _req_exc.HTTPError as exc:
        logger.warning(
            "naver_price_http_error",
            ticker=ticker,
            status=exc.response.status_code if exc.response else None,
        )
        return None
    except _req_exc.RequestException as exc:
        logger.warning("naver_price_network_error", ticker=ticker, error=str(exc))
        return None
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("naver_price_parse_error", ticker=ticker, error=str(exc))
        return None


def sync_pykrx_price(ticker: str) -> float | None:
    """pykrx로 국내 종목 최근 종가 조회. KRX 로그인 불필요."""
    import contextlib
    import io
    from datetime import date, timedelta

    try:
        with _pykrx_lock:
            with contextlib.redirect_stdout(io.StringIO()):
                from pykrx import stock

            today = date.today()
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
    import contextlib
    import io

    try:
        with _pykrx_lock:
            with contextlib.redirect_stdout(io.StringIO()):
                from pykrx import stock

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
