"""거시 시장 지표 조회 유틸.

**이 모듈의 책임:** VIX·장단기 금리차·공포탐욕 지수 등 매크로 지표 및 팩터·리스크 분석용
배치 수익률 데이터 수집 (factor_service, portfolio_optimizer, risk_service 공용).
개별 종목 가격·수익률 조회는 yahoo_price.py가 담당한다.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import TYPE_CHECKING

import structlog

from app.services.price_sync_sources import sync_pykrx_close_series, yf_symbol_to_krx_ticker
from app.utils.circuit_breaker import yahoo_circuit

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()


def _returns_from_series(series: pd.Series) -> list[float] | None:
    if len(series) < 2:
        return None
    returns = series.pct_change().dropna().tolist()
    return [float(r) for r in returns if math.isfinite(r)]


def _pykrx_daily_returns_fallback(
    missing_syms: list[str], start: date, end: date
) -> dict[str, list[float]]:
    """국내(.KS/.KQ) 심볼만 pykrx로 보완한다. 해외 종목·지수는 대체 소스가 없어 제외."""
    result: dict[str, list[float]] = {}
    for sym in missing_syms:
        ticker = yf_symbol_to_krx_ticker(sym)
        if ticker is None:
            continue
        series = sync_pykrx_close_series(ticker, start, end)
        if series is None:
            continue
        returns = _returns_from_series(series)
        if returns is not None:
            result[sym] = returns
    return result


def fetch_yf_daily_returns(
    symbols: list[str],
    period_days: int = 365,
    extra_symbols: list[str] | None = None,
) -> dict[str, list[float]]:
    """1년치 일별 수익률(소수, e.g. 0.01=1%)을 반환한다.

    portfolio_optimizer, risk_service에서 공통으로 사용.
    extra_symbols(예: ^GSPC)를 포함해 다운로드하되 결과에는 symbols + extra_symbols 모두 포함.
    Yahoo가 실패/차단된 국내(.KS/.KQ) 심볼은 pykrx로 보완한다.
    """
    import pandas as pd

    all_syms = list(set(symbols + (extra_symbols or [])))
    if not all_syms:
        return {}

    end = date.today()
    start = end - timedelta(days=period_days)
    result: dict[str, list[float]] = {}

    if yahoo_circuit.is_available():
        import yfinance as yf

        try:
            raw = yf.download(
                all_syms,
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as e:
            logger.warning("yf_download_failed", symbols=all_syms[:5], error=str(e))
            yahoo_circuit.record_failure()
            raw = None

        close: pd.DataFrame | None = None
        if raw is not None:
            close = raw.get("Close") if isinstance(raw.columns, pd.MultiIndex) else raw
            if close is None or close.empty:
                yahoo_circuit.record_failure()
                close = None
            else:
                yahoo_circuit.record_success()
                if not isinstance(close, pd.DataFrame):
                    close = close.to_frame(name=all_syms[0])

        if close is not None:
            for sym in all_syms:
                if sym not in close.columns:
                    continue
                returns = _returns_from_series(close[sym].dropna())
                if returns is not None:
                    result[sym] = returns

    missing = [sym for sym in all_syms if sym not in result]
    if missing:
        result.update(_pykrx_daily_returns_fallback(missing, start, end))
    return result


def fetch_yf_close_series(
    symbols: list[str],
    start: date,
    end: date,
) -> dict[str, pd.Series]:
    """지정 기간의 종목별 종가 Series를 반환한다.

    factor_service 모멘텀 계산(12-1M)에서 사용.
    Yahoo가 실패/차단된 국내(.KS/.KQ) 심볼은 pykrx로 보완한다.
    """
    import pandas as pd

    if not symbols:
        return {}

    result: dict[str, pd.Series] = {}

    if yahoo_circuit.is_available():
        import yfinance as yf

        try:
            raw = yf.download(
                symbols,
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as e:
            logger.warning("yf_close_series_failed", symbols=symbols[:5], error=str(e))
            yahoo_circuit.record_failure()
            raw = None

        if raw is not None and not raw.empty:
            yahoo_circuit.record_success()
            close: pd.DataFrame | None
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw.get("Close")
            else:
                close = raw if isinstance(raw, pd.DataFrame) else raw.to_frame(name=symbols[0])

            if close is not None:
                for sym in symbols:
                    if sym in close.columns:
                        series = close[sym].dropna()
                        if not series.empty:
                            result[sym] = series
        elif raw is not None:
            yahoo_circuit.record_failure()

    missing = [sym for sym in symbols if sym not in result]
    for sym in missing:
        ticker = yf_symbol_to_krx_ticker(sym)
        if ticker is None:
            continue
        series = sync_pykrx_close_series(ticker, start, end)
        if series is not None:
            result[sym] = series
    return result


def fetch_yf_info(
    symbols: list[str],
    max_workers: int = 5,
) -> dict[str, dict]:
    """ThreadPoolExecutor로 yfinance .info를 병렬 조회한다.

    factor_service P/E·P/B·시가총액 수집에서 사용.
    """
    import yfinance as yf

    if not symbols or not yahoo_circuit.is_available():
        return {}

    def _fetch_one(sym: str) -> tuple[str, dict]:
        try:
            return sym, yf.Ticker(sym).info or {}
        except Exception:
            return sym, {}

    info_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, sym): sym for sym in symbols}
        for future in as_completed(futures):
            try:
                sym, info = future.result()
                info_map[sym] = info
            except Exception as e:
                logger.warning("yf_info_fetch_failed", error=str(e))

    if any(info_map.values()):
        yahoo_circuit.record_success()
    else:
        yahoo_circuit.record_failure()
    return info_map
