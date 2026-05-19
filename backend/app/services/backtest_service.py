"""백테스팅 서비스.

Buy & Hold 전략으로 가상 포트폴리오의 과거 수익률을 시뮬레이션한다.
- yfinance 히스토리컬 가격 사용
- 벤치마크: S&P500 (SPY)
- 실제 포트폴리오: AssetSnapshot 일별 합계 시리즈
"""
from __future__ import annotations

import asyncio
import math
import uuid
from datetime import date
from functools import partial

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetSnapshot
from app.models.portfolio import Portfolio
from app.schemas.backtest import (
    BacktestResult,
    BacktestRunRequest,
    PortfolioMetrics,
    SeriesData,
)

logger = structlog.get_logger()

DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ", "KRX"}

# 백테스팅에서 제외되는 특수 항목 (가격 데이터 없음)
_BACKTEST_SKIP_TICKERS = {"CASH", "REAL_ESTATE"}
_BACKTEST_SKIP_MARKETS = {"KR_PROPERTY"}


# ── Yahoo Finance 심볼 변환 (price_service와 동일 로직) ───────

def _to_yf_symbol(ticker: str, market: str) -> str:
    m = market.upper()
    if m in ("KOSPI", "KRX"):
        return f"{ticker.zfill(6)}.KS"
    if m == "KOSDAQ":
        return f"{ticker.zfill(6)}.KQ"
    return ticker


# ── yfinance 히스토리컬 다운로드 (동기) ──────────────────────

def _sync_download_history(symbols: list[str], start: date, end: date) -> dict[str, list[tuple[str, float]]]:
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
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as e:
        logger.warning("yfinance_download_failed", symbols=symbols, error=str(e))
        return {}

    close = raw.get("Close") if isinstance(raw.columns, pd.MultiIndex) else raw
    if close is None or close.empty:
        return {}

    # 단일 심볼이면 Series → DataFrame 통일
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


# ── 지표 계산 ─────────────────────────────────────────────

def _compute_metrics(name: str, values: list[float]) -> PortfolioMetrics:
    if len(values) < 2:
        return PortfolioMetrics(name=name, total_return_pct=0, cagr_pct=0, mdd_pct=0, sharpe_ratio=0)

    total_return = (values[-1] / 100.0 - 1) * 100
    years = len(values) / 252  # 거래일 기준
    cagr = ((values[-1] / 100.0) ** (1 / years) - 1) * 100 if years > 0 else 0

    # MDD
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Sharpe (일별 수익률 기준, 무위험이율 = 0 가정)
    daily_rets = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
    n = len(daily_rets)
    if n < 2:
        sharpe = 0.0
    else:
        mean_r = sum(daily_rets) / n
        variance = sum((r - mean_r) ** 2 for r in daily_rets) / (n - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0

    return PortfolioMetrics(
        name=name,
        total_return_pct=round(total_return, 2),
        cagr_pct=round(cagr, 2),
        mdd_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 3),
    )


# ── 포트폴리오 시리즈 계산 (Buy & Hold) ─────────────────────

def _compute_portfolio_series(
    name: str,
    holdings: list[dict],
    price_data: dict[str, list[tuple[str, float]]],
    dates: list[str],
) -> tuple[SeriesData, PortfolioMetrics]:
    """holdings의 Buy & Hold 수익률 시리즈 계산."""
    # 심볼 → yf symbol 매핑
    sym_map: dict[str, str] = {}
    weight_map: dict[str, float] = {}
    for h in holdings:
        sym = _to_yf_symbol(h["ticker"], h["market"])
        sym_map[h["ticker"]] = sym
        weight_map[sym] = h["weight"] / 100.0

    # 각 심볼의 가격 딕셔너리 구성
    price_by_sym: dict[str, dict[str, float]] = {}
    for sym in sym_map.values():
        if sym in price_data:
            price_by_sym[sym] = dict(price_data[sym])

    # 초기 가격 확정 (첫 거래일)
    init_prices: dict[str, float] = {}
    for sym in sym_map.values():
        p = price_by_sym.get(sym, {})
        for d in dates:
            if d in p and p[d] > 0:
                init_prices[sym] = p[d]
                break

    if not init_prices:
        values = [100.0] * len(dates)
        metrics = _compute_metrics(name, values)
        return SeriesData(name=name, values=values), metrics

    values: list[float] = []
    for d in dates:
        portfolio_val = 0.0
        total_weight = 0.0
        for sym, w in weight_map.items():
            p_now = price_by_sym.get(sym, {}).get(d)
            p_init = init_prices.get(sym)
            if p_now and p_init and p_init > 0:
                portfolio_val += w * (p_now / p_init)
                total_weight += w
        # 가격 없는 종목은 비중 재조정
        if total_weight > 0:
            portfolio_val = (portfolio_val / total_weight) * 100
        else:
            portfolio_val = values[-1] if values else 100.0
        values.append(round(portfolio_val, 4))

    metrics = _compute_metrics(name, values)
    return SeriesData(name=name, values=values), metrics


# ── 실제 보유 포트폴리오 시리즈 ───────────────────────────────

async def _get_real_portfolio_series(
    user_id: uuid.UUID,
    dates: list[str],
    db: AsyncSession,
) -> tuple[SeriesData, PortfolioMetrics] | None:
    """AssetSnapshot 일별 합계로 실제 포트폴리오 수익률 시리즈 계산."""
    start = date.fromisoformat(dates[0]) if dates else None
    end = date.fromisoformat(dates[-1]) if dates else None
    if not start or not end:
        return None

    rows = await db.execute(
        select(
            AssetSnapshot.snapshot_date.label("snap_date"),
            func.sum(AssetSnapshot.amount_krw).label("total"),
        )
        .where(
            AssetSnapshot.user_id == user_id,
            AssetSnapshot.snapshot_date >= start,
            AssetSnapshot.snapshot_date <= end,
        )
        .group_by(AssetSnapshot.snapshot_date)
        .order_by(AssetSnapshot.snapshot_date)
    )
    snap_rows = rows.all()
    if not snap_rows:
        return None

    snap_map: dict[str, float] = {row.snap_date.isoformat(): float(row.total) for row in snap_rows}

    # forward-fill
    values: list[float] = []
    last_val: float | None = None
    for d in dates:
        if d in snap_map:
            last_val = snap_map[d]
        if last_val is None:
            # 데이터 시작 전 — 초기값 탐색
            continue
        values.append(last_val)

    if not values:
        return None

    # 기준 100 정규화
    base = values[0]
    if base <= 0:
        return None
    normalized = [round(v / base * 100, 4) for v in values]

    # dates 길이 맞추기 (forward-fill 없는 앞부분 제거)
    aligned_dates = dates[len(dates) - len(normalized):]
    if len(aligned_dates) != len(normalized):
        normalized = normalized[-len(dates):]

    name = "실제 포트폴리오"
    metrics = _compute_metrics(name, normalized)
    return SeriesData(name=name, values=normalized), metrics


# ── 메인 백테스팅 실행 ─────────────────────────────────────

async def run_backtest(
    user_id: uuid.UUID,
    req: BacktestRunRequest,
    db: AsyncSession,
) -> BacktestResult:
    # 1. 포트폴리오 설정 로드
    port_rows = await db.execute(
        select(Portfolio).where(
            Portfolio.user_id == user_id,
            Portfolio.id.in_(req.portfolio_ids),
        )
    )
    portfolios: list[Portfolio] = list(port_rows.scalars().all())

    # 2. 모든 티커 수집 (CASH·REAL_ESTATE 제외 — yfinance 조회 불가)
    all_symbols: list[str] = []
    for p in portfolios:
        for h in p.items:
            if h["ticker"] in _BACKTEST_SKIP_TICKERS or h["market"] in _BACKTEST_SKIP_MARKETS:
                continue
            sym = _to_yf_symbol(h["ticker"], h["market"])
            if sym not in all_symbols:
                all_symbols.append(sym)
    if req.include_spy and "SPY" not in all_symbols:
        all_symbols.append("SPY")

    # 3. yfinance 히스토리컬 일괄 다운로드
    loop = asyncio.get_event_loop()
    price_data: dict[str, list[tuple[str, float]]] = await loop.run_in_executor(
        None,
        partial(_sync_download_history, all_symbols, req.start_date, req.end_date),
    )

    # 4. 공통 날짜 축 구성 (SPY 또는 첫 번째 심볼의 거래일 기준)
    ref_sym = "SPY" if "SPY" in price_data else (all_symbols[0] if all_symbols else None)
    if ref_sym and ref_sym in price_data:
        dates = [d for d, _ in price_data[ref_sym]]
    else:
        # fallback: 달력일 기준 (주말 제외 불가, 단순 처리)
        from datetime import timedelta
        cur = req.start_date
        dates = []
        while cur <= req.end_date:
            if cur.weekday() < 5:
                dates.append(cur.isoformat())
            cur += timedelta(days=1)

    if not dates:
        return BacktestResult(dates=[], series=[], metrics=[])

    # 5. 각 포트폴리오 시리즈 계산
    all_series: list[SeriesData] = []
    all_metrics: list[PortfolioMetrics] = []

    for p in portfolios:
        investable = [
            h for h in p.items
            if h["ticker"] not in _BACKTEST_SKIP_TICKERS
            and h["market"] not in _BACKTEST_SKIP_MARKETS
        ]
        s, m = _compute_portfolio_series(p.name, investable, price_data, dates)
        all_series.append(s)
        all_metrics.append(m)

    # 6. S&P500 시리즈
    if req.include_spy and "SPY" in price_data:
        spy_prices = dict(price_data["SPY"])
        spy_vals: list[float] = []
        base_price: float | None = None
        for d in dates:
            p = spy_prices.get(d)
            if p and base_price is None:
                base_price = p
            if base_price and base_price > 0:
                spy_vals.append(round((spy_prices.get(d, base_price) / base_price) * 100, 4))
            else:
                spy_vals.append(100.0)
        spy_series = SeriesData(name="S&P 500", values=spy_vals)
        all_series.append(spy_series)
        all_metrics.append(_compute_metrics("S&P 500", spy_vals))

    # 7. 실제 포트폴리오 시리즈
    if req.include_real_portfolio:
        real = await _get_real_portfolio_series(user_id, dates, db)
        if real:
            all_series.append(real[0])
            all_metrics.append(real[1])

    return BacktestResult(dates=dates, series=all_series, metrics=all_metrics)
