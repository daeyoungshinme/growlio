"""백테스팅 서비스.

Buy & Hold 전략으로 가상 포트폴리오의 과거 수익률을 시뮬레이션한다.
- yfinance 히스토리컬 가격 사용
- 벤치마크: S&P500 (SPY)
- 실제 포트폴리오: 최신 AssetSnapshot positions 비중 기반 yfinance 백테스팅 (성장형과 동일 방식)

순수 계산 함수는 backtest_metrics.py 참고.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from functools import partial

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.models.portfolio import Portfolio
from app.schemas.backtest import (
    BacktestResult,
    BacktestRunRequest,
    CorrelationRequest,
    CorrelationResult,
    PortfolioMetrics,
    SeriesData,
)
from app.services.backtest_metrics import compute_metrics, compute_portfolio_series
from app.services.yahoo_price import to_yf_symbol as _to_yf_symbol

logger = structlog.get_logger()

DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ", "KRX"}

_BACKTEST_SKIP_TICKERS = {"CASH", "REAL_ESTATE"}
_BACKTEST_SKIP_MARKETS = {"KR_PROPERTY"}

# 테스트 backward-compatibility 별칭
_compute_metrics = compute_metrics
_compute_portfolio_series = compute_portfolio_series


# ── yfinance 히스토리컬 다운로드 (동기) ──────────────────────

def _sync_download_history(
    symbols: list[str],
    start: date,
    end: date,
    reinvest_dividends: bool = True,
) -> dict[str, list[tuple[str, float]]]:
    """symbol → [(date_str, price), ...] 반환. 동기 함수."""
    import pandas as pd
    import yfinance as yf

    if not symbols:
        return {}

    try:
        raw = yf.download(
            symbols,
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=reinvest_dividends,
            progress=False,
            threads=False,
        )
    except Exception as e:
        logger.warning("yfinance_download_failed", symbols=symbols, error=str(e))
        return {}

    close = raw.get("Close") if isinstance(raw.columns, pd.MultiIndex) else raw
    if close is None or close.empty:
        return {}

    if not isinstance(close, pd.DataFrame):
        close = close.to_frame(name=symbols[0])

    result: dict[str, list[tuple[str, float]]] = {}
    for sym in symbols:
        if sym not in close.columns:
            continue
        series = close[sym].dropna()
        if series.empty:
            continue
        result[sym] = [(idx.strftime("%Y-%m-%d"), float(val)) for idx, val in series.items() if val > 0]

    return result


# ── 실제 보유 포트폴리오 holdings 조회 ──────────────────────────

async def _get_real_portfolio_holdings(
    user_id: uuid.UUID,
    db: AsyncSession,
    asset_types: list[str] | None = None,
) -> list[dict] | None:
    """최신 AssetSnapshot의 positions로부터 실제 보유 종목 비중을 계산.

    반환: [{ticker, market, weight}, ...] — compute_portfolio_series에 바로 전달 가능.
    스냅샷이 없거나 포지션이 비어 있으면 None 반환.
    """
    latest_sub = (
        select(
            AssetSnapshot.account_id,
            func.max(AssetSnapshot.snapshot_date).label("max_date"),
        )
        .join(AssetAccount, AssetSnapshot.account_id == AssetAccount.id)
        .where(
            AssetSnapshot.user_id == user_id,
            AssetAccount.is_active == True,  # noqa: E712
            *([AssetAccount.asset_type.in_(asset_types)] if asset_types else []),
        )
        .group_by(AssetSnapshot.account_id)
        .subquery()
    )

    snap_rows = await db.execute(
        select(AssetSnapshot.id)
        .join(
            latest_sub,
            (AssetSnapshot.account_id == latest_sub.c.account_id)
            & (AssetSnapshot.snapshot_date == latest_sub.c.max_date),
        )
    )
    snap_ids = [row[0] for row in snap_rows.all()]

    if not snap_ids:
        return None

    pos_rows = await db.execute(
        select(Position).where(Position.snapshot_id.in_(snap_ids))
    )
    all_positions = pos_rows.scalars().all()

    if not all_positions:
        return None

    ticker_map: dict[tuple[str, str], float] = {}
    for p in all_positions:
        ticker = p.ticker
        market = p.market
        if not ticker or not market:
            continue
        if ticker in _BACKTEST_SKIP_TICKERS or market in _BACKTEST_SKIP_MARKETS:
            continue
        value_krw = float(p.value_krw or 0) or (float(p.current_price or 0) * float(p.qty or 0))
        if value_krw and value_krw > 0:
            key = (ticker, market)
            ticker_map[key] = ticker_map.get(key, 0.0) + value_krw

    if not ticker_map:
        return None

    total_krw = sum(ticker_map.values())
    if total_krw <= 0:
        return None

    return [
        {"ticker": ticker, "market": market, "weight": round(value / total_krw * 100, 4)}
        for (ticker, market), value in ticker_map.items()
    ]


# ── 메인 백테스팅 실행 ─────────────────────────────────────

async def _download_price_data(
    portfolios: list[Portfolio],
    req: BacktestRunRequest,
    real_holdings: list[dict] | None,
) -> dict[str, list[tuple[str, float]]]:
    """모든 포트폴리오 심볼과 실제 보유 종목의 가격 데이터를 yfinance로 다운로드한다."""
    all_symbols: list[str] = []
    for p in portfolios:
        for h in p.items:
            if h.ticker in _BACKTEST_SKIP_TICKERS or h.market in _BACKTEST_SKIP_MARKETS:
                continue
            sym = _to_yf_symbol(h.ticker, h.market)
            if sym not in all_symbols:
                all_symbols.append(sym)
    if req.include_spy and "SPY" not in all_symbols:
        all_symbols.append("SPY")

    if real_holdings:
        for rh in real_holdings:
            sym = _to_yf_symbol(rh["ticker"], rh["market"])
            if sym not in all_symbols:
                all_symbols.append(sym)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(_sync_download_history, all_symbols, req.start_date, req.end_date, req.reinvest_dividends),
    )


def _build_date_axis(
    price_data: dict[str, list[tuple[str, float]]],
    all_symbols: list[str],
    req: BacktestRunRequest,
) -> list[str]:
    """공통 날짜 축을 구성한다. SPY 또는 첫 번째 심볼의 거래일 기준."""
    ref_sym = "SPY" if "SPY" in price_data else (all_symbols[0] if all_symbols else None)
    if ref_sym and ref_sym in price_data:
        return [d for d, _ in price_data[ref_sym]]

    from datetime import timedelta
    cur = req.start_date
    dates: list[str] = []
    while cur <= req.end_date:
        if cur.weekday() < 5:
            dates.append(cur.isoformat())
        cur += timedelta(days=1)
    return dates


def _compute_performance_metrics(
    portfolios: list[Portfolio],
    price_data: dict[str, list[tuple[str, float]]],
    dates: list[str],
    req: BacktestRunRequest,
    real_holdings: list[dict] | None,
) -> tuple[list[SeriesData], list[PortfolioMetrics]]:
    """포트폴리오별 시리즈·메트릭, SPY 벤치마크, 실제 포트폴리오 시리즈를 계산한다."""
    all_series: list[SeriesData] = []
    all_metrics: list[PortfolioMetrics] = []

    # 각 포트폴리오 시리즈
    for p in portfolios:
        investable = [
            {"ticker": h.ticker, "market": h.market, "weight": float(h.weight), "name": h.name}
            for h in p.items
            if h.ticker not in _BACKTEST_SKIP_TICKERS
            and h.market not in _BACKTEST_SKIP_MARKETS
        ]
        s, m = compute_portfolio_series(p.name, investable, price_data, dates)
        all_series.append(s)
        all_metrics.append(m)

    # S&P500 시리즈
    if req.include_spy and "SPY" in price_data:
        spy_prices = dict(price_data["SPY"])
        spy_vals: list[float] = []
        base_price: float | None = None
        for d in dates:
            spy_p = spy_prices.get(d)
            if spy_p and base_price is None:
                base_price = spy_p
            if base_price and base_price > 0:
                spy_vals.append(round((spy_prices.get(d, base_price) / base_price) * 100, 4))
            else:
                spy_vals.append(100.0)
        spy_series = SeriesData(name="S&P 500", values=spy_vals)
        all_series.append(spy_series)
        all_metrics.append(compute_metrics("S&P 500", spy_vals))

    # 실제 포트폴리오 시리즈 — 최신 스냅샷 positions 비중 기반 yfinance 백테스팅
    if req.include_real_portfolio and real_holdings:
        s, m = compute_portfolio_series("실제 포트폴리오", real_holdings, price_data, dates)
        all_series.append(s)
        all_metrics.append(m)

    return all_series, all_metrics


async def run_backtest(
    user_id: uuid.UUID,
    req: BacktestRunRequest,
    db: AsyncSession,
) -> BacktestResult:
    # 1. 포트폴리오 설정 로드
    port_rows = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.items))
        .where(
            Portfolio.user_id == user_id,
            Portfolio.id.in_(req.portfolio_ids),
        )
    )
    portfolios: list[Portfolio] = list(port_rows.scalars().all())

    # 2. 실제 포트폴리오 보유 종목 조회
    real_asset_types: list[str] | None = None
    if portfolios and all(p.base_type == "STOCK_ONLY" for p in portfolios):
        real_asset_types = ["STOCK_KIS", "STOCK_OTHER", "STOCK_KIWOOM"]

    real_holdings: list[dict] | None = None
    if req.include_real_portfolio:
        real_holdings = await _get_real_portfolio_holdings(user_id, db, asset_types=real_asset_types)

    # 3. yfinance 히스토리컬 일괄 다운로드
    price_data = await _download_price_data(portfolios, req, real_holdings)

    # 4. 공통 날짜 축 구성
    all_symbols = list(price_data.keys())
    dates = _build_date_axis(price_data, all_symbols, req)

    if not dates:
        return BacktestResult(dates=[], series=[], metrics=[])

    # 5–7. 시리즈 및 성능 메트릭 계산
    all_series, all_metrics = _compute_performance_metrics(
        portfolios, price_data, dates, req, real_holdings
    )

    return BacktestResult(dates=dates, series=all_series, metrics=all_metrics)


# ── 상관관계 분석 ───────────────────────────────────────────────

def _sync_compute_correlation(
    symbols: list[str],
    labels: list[str],
    start: date,
    end: date,
) -> tuple[list[str], list[list[float | None]]]:
    """월별 수익률 기반 상관계수 행렬 계산 (동기). (filtered_labels, matrix) 반환."""
    import math as _math

    import pandas as pd
    import yfinance as yf

    if not symbols:
        return [], []

    try:
        raw = yf.download(
            symbols,
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as e:
        logger.warning("correlation_download_failed", error=str(e))
        return [], []

    if raw is None or (hasattr(raw, "empty") and raw.empty):
        return [], []

    close = raw.get("Close") if isinstance(raw.columns, pd.MultiIndex) else raw
    if close is None or (hasattr(close, "empty") and close.empty):
        return [], []

    if not isinstance(close, pd.DataFrame):
        close = close.to_frame(name=symbols[0])

    monthly = close.resample("ME").last()
    returns = monthly.pct_change().dropna(how="all")

    valid_cols = [col for col in returns.columns if returns[col].count() >= 6]
    if not valid_cols:
        return [], []

    returns = returns[valid_cols]
    corr = returns.corr()

    sym_to_label = dict(zip(symbols, labels, strict=False))
    filtered_labels = [sym_to_label.get(str(col), str(col)) for col in valid_cols]

    matrix: list[list[float | None]] = []
    for col in valid_cols:
        row: list[float | None] = []
        for col2 in valid_cols:
            val = corr.loc[col, col2]
            row.append(round(float(val), 3) if not _math.isnan(float(val)) else None)
        matrix.append(row)

    return filtered_labels, matrix


async def compute_correlation(
    user_id: uuid.UUID,
    req: CorrelationRequest,
    db: AsyncSession,
) -> CorrelationResult:
    """포트폴리오 내 종목 간 월별 수익률 상관관계 분석."""
    result = await db.execute(
        select(Portfolio)
        .options(selectinload(Portfolio.items))
        .where(
            Portfolio.user_id == user_id,
            Portfolio.id.in_(req.portfolio_ids),
        )
    )
    portfolios = list(result.scalars().all())

    seen: set[str] = set()
    symbols: list[str] = []
    labels: list[str] = []

    for port in portfolios:
        for item in (port.items or []):
            if not item.ticker or not item.market:
                continue
            if item.ticker in _BACKTEST_SKIP_TICKERS or item.market in _BACKTEST_SKIP_MARKETS:
                continue
            sym = _to_yf_symbol(item.ticker, item.market)
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)
                labels.append(item.name or item.ticker)

    if not symbols:
        return CorrelationResult(labels=[], matrix=[])

    loop = asyncio.get_running_loop()
    filtered_labels, matrix = await loop.run_in_executor(
        None,
        partial(_sync_compute_correlation, symbols, labels, req.start_date, req.end_date),
    )

    return CorrelationResult(labels=filtered_labels, matrix=matrix)
