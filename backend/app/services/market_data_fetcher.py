"""yfinance 데이터 조회 공통 유틸.

factor_service, portfolio_optimizer, risk_service 세 곳에서 동일하게 사용되는
yfinance batch download + MultiIndex 파싱 + NaN 필터링 패턴을 한 곳에서 관리한다.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import pandas as pd

logger = structlog.get_logger()


def fetch_yf_daily_returns(
    symbols: list[str],
    period_days: int = 365,
    extra_symbols: list[str] | None = None,
) -> dict[str, list[float]]:
    """1년치 일별 수익률(소수, e.g. 0.01=1%)을 반환한다.

    portfolio_optimizer, risk_service에서 공통으로 사용.
    extra_symbols(예: ^GSPC)를 포함해 다운로드하되 결과에는 symbols + extra_symbols 모두 포함.
    """
    import pandas as pd
    import yfinance as yf

    all_syms = list(set(symbols + (extra_symbols or [])))
    if not all_syms:
        return {}

    end = date.today()
    start = end - timedelta(days=period_days)
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
        return {}

    close: pd.DataFrame | None = raw.get("Close") if isinstance(raw.columns, pd.MultiIndex) else raw
    if close is None or close.empty:
        return {}
    if not isinstance(close, pd.DataFrame):
        close = close.to_frame(name=all_syms[0])

    result: dict[str, list[float]] = {}
    for sym in all_syms:
        if sym not in close.columns:
            continue
        series = close[sym].dropna()
        if len(series) < 2:
            continue
        returns = series.pct_change().dropna().tolist()
        result[sym] = [float(r) for r in returns if math.isfinite(r)]
    return result


def fetch_yf_close_series(
    symbols: list[str],
    start: date,
    end: date,
) -> dict[str, "pd.Series"]:
    """지정 기간의 종목별 종가 Series를 반환한다.

    factor_service 모멘텀 계산(12-1M)에서 사용.
    """
    import pandas as pd
    import yfinance as yf

    if not symbols:
        return {}

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
        return {}

    if raw is None or raw.empty:
        return {}

    close: pd.DataFrame
    if isinstance(raw.columns, pd.MultiIndex):
        close_raw = raw.get("Close")
        if close_raw is None:
            return {}
        close = close_raw
    else:
        close = raw if isinstance(raw, pd.DataFrame) else raw.to_frame(name=symbols[0])

    result: dict[str, pd.Series] = {}
    for sym in symbols:
        if sym in close.columns:
            series = close[sym].dropna()
            if not series.empty:
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
    return info_map
