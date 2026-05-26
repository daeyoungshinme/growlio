"""외부 소스(Yahoo Finance, Naver, pykrx, FinanceDataReader)에서 배당 정보를 수집하는 동기 함수들.

모든 함수는 동기(sync)이며 asyncio run_in_executor로 호출한다.
"""

from __future__ import annotations

from datetime import date

import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = structlog.get_logger()

_NAVER_RETRY = dict(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)


def sync_yahoo_dividend_info(yahoo_symbol: str) -> dict:
    """trailingAnnualDividendRate(TTM 주당 배당금)를 DPS로 사용.
    yield는 trailingAnnualDividendYield 우선, forward dividendYield 폴백.
    """
    import yfinance as yf
    try:
        ticker = yf.Ticker(yahoo_symbol)
        info = ticker.info
        trailing_yld = float(info.get("trailingAnnualDividendYield") or 0)
        forward_yld = float(info.get("dividendYield") or 0)
        yld = trailing_yld if trailing_yld > 0 else forward_yld

        # yfinance가 한국 종목에서 decimal(0.027) 대신 percentage(2.7)로 반환하는 사례 보정
        # 현실적인 배당수익률 상한을 30%로 설정 (0.3 초과 = 단위 오류로 판단)
        if yld > 0.3:
            logger.warning("yahoo_yield_percentage_corrected", symbol=yahoo_symbol, raw_yld=yld)
            yld = yld / 100

        trailing_dps = float(info.get("trailingAnnualDividendRate") or 0)
        last_price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)

        # DPS가 주가 대비 50% 초과이면 단위 오류로 판단
        if trailing_dps > 0 and last_price > 0 and trailing_dps / last_price > 0.5:
            logger.warning(
                "yahoo_dps_unit_corrected",
                symbol=yahoo_symbol, raw_dps=trailing_dps, price=last_price,
            )
            trailing_dps = trailing_dps / 100

        dps = round(trailing_dps, 2) if trailing_dps > 0 else round(last_price * yld, 2)
        return {"dividend_yield": yld, "dps": dps, "ex_dividend_date": None}
    except Exception as e:
        logger.warning("yahoo_dividend_info_failed", symbol=yahoo_symbol, error=str(e))
        return {"dividend_yield": 0.0, "dps": 0.0, "ex_dividend_date": None}


def sync_pykrx_etf_dividend_info(ticker: str) -> dict:
    """pykrx로 ETF 분배수익률 조회.

    KRX 로그인 불필요 — pykrx가 KRX_ID/KRX_PW 미설정 시 익명 폴백.
    ETF가 아니거나 데이터 없으면 {"dps": 0.0, "dividend_yield": 0.0} 반환.
    """
    import contextlib
    import io
    from datetime import timedelta

    # pykrx import 시 "KRX 로그인 실패" 메시지 억제 (기능 정상)
    with contextlib.redirect_stdout(io.StringIO()):
        from pykrx import stock

    try:
        today = date.today()
        end = today.strftime("%Y%m%d")
        start = (today - timedelta(days=365)).strftime("%Y%m%d")

        div_df = stock.get_market_dividend_by_date(start, end, ticker)
        if div_df is None or div_df.empty:
            return {"dps": 0.0, "dividend_yield": 0.0}

        dps_col = next((c for c in ["주당배당금", "DPS"] if c in div_df.columns), None)
        if dps_col is None:
            return {"dps": 0.0, "dividend_yield": 0.0}

        annual_dps = float(div_df[dps_col][div_df[dps_col] > 0].sum())
        if annual_dps <= 0:
            return {"dps": 0.0, "dividend_yield": 0.0}

        price_df = stock.get_etf_ohlcv_by_date(end, end, ticker)
        current_price = float(price_df["종가"].iloc[-1]) if not price_df.empty else 0.0
        yield_decimal = round(annual_dps / current_price, 6) if current_price > 0 else 0.0

        logger.info(
            "pykrx_etf_dividend_fetched",
            ticker=ticker, annual_dps=annual_dps, yield_decimal=yield_decimal,
        )
        return {"dps": annual_dps, "dividend_yield": yield_decimal}
    except Exception as e:
        logger.warning("pykrx_etf_dividend_failed", ticker=ticker, error=str(e))
        return {"dps": 0.0, "dividend_yield": 0.0}


def sync_fdr_etf_dividend_info(ticker: str) -> dict:
    """fdr.StockListing('ETF/KR')으로 현재가 조회 + pykrx fundamental로 DIV/DPS 조회."""
    import contextlib
    import io

    try:
        import FinanceDataReader as fdr

        etf_list = fdr.StockListing("ETF/KR")
        row = etf_list[etf_list["Symbol"] == ticker]
        if row.empty:
            return {"dps": 0.0, "dividend_yield": 0.0}

        current_price = float(row["Price"].iloc[0]) if "Price" in row.columns else 0.0
        if current_price == 0.0:
            return {"dps": 0.0, "dividend_yield": 0.0}

        with contextlib.redirect_stdout(io.StringIO()):
            from pykrx import stock

        today_str = date.today().strftime("%Y%m%d")
        fund_df = stock.get_market_fundamental_by_ticker(today_str, market="ALL")

        if fund_df is None or fund_df.empty or ticker not in fund_df.index:
            return {"dps": 0.0, "dividend_yield": 0.0}

        row_f = fund_df.loc[ticker]
        dps = float(row_f.get("DPS", 0) or 0)
        div_pct = float(row_f.get("DIV", 0) or 0)

        yield_decimal = round(div_pct / 100, 6) if div_pct > 0 else (
            round(dps / current_price, 6) if (dps > 0 and current_price > 0) else 0.0
        )

        logger.info("fdr_etf_dividend_fetched", ticker=ticker, dps=dps, yield_decimal=yield_decimal)
        return {"dps": dps, "dividend_yield": yield_decimal}
    except Exception as exc:
        logger.warning("fdr_etf_dividend_failed", ticker=ticker, error=str(exc))
        return {"dps": 0.0, "dividend_yield": 0.0}


def sync_naver_etf_dividend_info(ticker: str) -> dict:
    """Naver Finance 모바일 API(etfAnalysis)로 국내 ETF TTM 분배율·DPS·배당월 조회."""
    import requests as _req
    import requests.exceptions as _req_exc

    _MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    )

    @retry(**_NAVER_RETRY)
    def _fetch() -> _req.Response:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/etfAnalysis"
        r = _req.get(url, headers={"User-Agent": _MOBILE_UA}, timeout=10)
        r.raise_for_status()
        return r

    try:
        resp = _fetch()
        div = resp.json().get("dividend") or {}
        if not div:
            return {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}

        yield_pct = float(div.get("dividendYieldTtm") or 0)
        dps = float(div.get("dividendPerShareTtm") or 0)

        months_raw = div.get("dividendMonthThisYear") or ""
        months: list[int] = []
        if months_raw:
            for part in str(months_raw).split(","):
                part = part.strip()
                if part.isdigit():
                    months.append(int(part))

        logger.info("naver_etf_dividend_fetched", ticker=ticker, dps=dps, yield_pct=yield_pct)
        return {
            "dps": dps,
            "dividend_yield": yield_pct / 100.0,
            "dividend_months": months,
        }
    except _req_exc.HTTPError as exc:
        logger.warning("naver_etf_dividend_http_error", ticker=ticker, status=exc.response.status_code if exc.response else None)
        return {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}
    except _req_exc.RequestException as exc:
        logger.warning("naver_etf_dividend_network_error", ticker=ticker, error=str(exc))
        return {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("naver_etf_dividend_parse_error", ticker=ticker, error=str(exc))
        return {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}


def sync_naver_stock_dividend_info(ticker: str) -> dict:
    """Naver Finance 모바일 API(summary)로 국내 일반주식 배당수익률 조회. DPS는 미제공."""
    import requests as _req
    import requests.exceptions as _req_exc

    _MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    )

    @retry(**_NAVER_RETRY)
    def _fetch() -> _req.Response:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/summary"
        r = _req.get(url, headers={"User-Agent": _MOBILE_UA}, timeout=10)
        r.raise_for_status()
        return r

    try:
        resp = _fetch()
        detail = resp.json().get("stockItemDetail") or {}
        yield_pct = float(detail.get("dividendYield") or 0)
        if yield_pct <= 0:
            return {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}
        logger.info("naver_stock_dividend_fetched", ticker=ticker, yield_pct=yield_pct)
        return {"dps": 0.0, "dividend_yield": yield_pct / 100.0, "dividend_months": []}
    except _req_exc.HTTPError as exc:
        logger.warning("naver_stock_dividend_http_error", ticker=ticker, status=exc.response.status_code if exc.response else None)
        return {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}
    except _req_exc.RequestException as exc:
        logger.warning("naver_stock_dividend_network_error", ticker=ticker, error=str(exc))
        return {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("naver_stock_dividend_parse_error", ticker=ticker, error=str(exc))
        return {"dps": 0.0, "dividend_yield": 0.0, "dividend_months": []}


def sync_fetch_dividend_months(yahoo_symbol: str) -> list[int]:
    """과거 2년 배당락일에서 지급월 추출. calendar로 ex-date/payment-date 오프셋 보정."""
    import yfinance as yf
    try:
        t = yf.Ticker(yahoo_symbol)

        offset_months = 1  # 기본: 배당락일 + 1개월 ≈ 지급일
        try:
            cal = t.calendar or {}
            ex_date = cal.get("Ex-Dividend Date")
            pay_date = cal.get("Dividend Date")
            if ex_date and pay_date:
                ex_m = ex_date.month if hasattr(ex_date, "month") else int(str(ex_date)[5:7])
                pay_m = pay_date.month if hasattr(pay_date, "month") else int(str(pay_date)[5:7])
                offset_months = (pay_m - ex_m) % 12
        except Exception:
            pass

        divs = t.dividends
        if divs is None or len(divs) == 0:
            return []
        cutoff_year = date.today().year - 2
        months: set[int] = set()
        for ts in divs.index:
            if hasattr(ts, "year") and ts.year >= cutoff_year:
                payment_month = ((int(ts.month) - 1 + offset_months) % 12) + 1
                months.add(payment_month)
        return sorted(months)
    except Exception:
        return []
