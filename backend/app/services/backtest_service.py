"""백테스팅 서비스.

Buy & Hold 전략으로 가상 포트폴리오의 과거 수익률을 시뮬레이션한다.
- yfinance 히스토리컬 가격 사용
- 벤치마크: S&P500 (SPY)
- 실제 포트폴리오: 최신 AssetSnapshot positions 비중 기반 yfinance 백테스팅 (성장형과 동일 방식)
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
from app.services.yahoo_price import to_yf_symbol as _to_yf_symbol

logger = structlog.get_logger()

DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ", "KRX"}

# 백테스팅에서 제외되는 특수 항목 (가격 데이터 없음)
_BACKTEST_SKIP_TICKERS = {"CASH", "REAL_ESTATE"}
_BACKTEST_SKIP_MARKETS = {"KR_PROPERTY"}


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
        return PortfolioMetrics(
            name=name, total_return_pct=0, cagr_pct=0, mdd_pct=0,
            sharpe_ratio=0, volatility_pct=0, sortino_ratio=0,
        )

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

    # 일별 수익률
    daily_rets = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
    n = len(daily_rets)
    if n < 2:
        return PortfolioMetrics(
            name=name,
            total_return_pct=round(total_return, 2),
            cagr_pct=round(cagr, 2),
            mdd_pct=round(max_dd, 2),
            sharpe_ratio=0, volatility_pct=0, sortino_ratio=0,
        )

    mean_r = sum(daily_rets) / n
    variance = sum((r - mean_r) ** 2 for r in daily_rets) / (n - 1)
    std_r = math.sqrt(variance) if variance > 0 else 0

    # Sharpe (무위험이율 = 0 가정, 연율화)
    sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0

    # Volatility (연율화 표준편차, %)
    volatility_pct = std_r * math.sqrt(252) * 100

    # Sortino (하방 편차 기준)
    downside_rets = [r for r in daily_rets if r < 0]
    if len(downside_rets) >= 2:
        ds_mean = sum(downside_rets) / len(downside_rets)
        ds_var = sum((r - ds_mean) ** 2 for r in downside_rets) / (len(downside_rets) - 1)
        ds_std = math.sqrt(ds_var) if ds_var > 0 else 0
        sortino = (mean_r / ds_std * math.sqrt(252)) if ds_std > 0 else 0
    else:
        sortino = 0.0

    return PortfolioMetrics(
        name=name,
        total_return_pct=round(total_return, 2),
        cagr_pct=round(cagr, 2),
        mdd_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 3),
        volatility_pct=round(volatility_pct, 2),
        sortino_ratio=round(sortino, 3),
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
        empty_vals: list[float] = [100.0] * len(dates)
        metrics = _compute_metrics(name, empty_vals)
        return SeriesData(name=name, values=empty_vals), metrics

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


# ── 실제 보유 포트폴리오 holdings 조회 ──────────────────────────

async def _get_real_portfolio_holdings(
    user_id: uuid.UUID,
    db: AsyncSession,
    asset_types: list[str] | None = None,
) -> list[dict] | None:
    """최신 AssetSnapshot의 positions로부터 실제 보유 종목 비중을 계산.

    반환: [{ticker, market, weight}, ...] — _compute_portfolio_series에 바로 전달 가능.
    스냅샷이 없거나 포지션이 비어 있으면 None 반환.
    """
    # 계좌별 최신 snapshot_date 서브쿼리
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

    # 최신 스냅샷 ID 목록 조회
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

    # positions 테이블에서 해당 스냅샷 포지션 조회
    pos_rows = await db.execute(
        select(Position).where(Position.snapshot_id.in_(snap_ids))
    )
    all_positions = pos_rows.scalars().all()

    if not all_positions:
        return None

    # ticker+market 기준으로 value_krw 합산
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

    # 2. 모든 티커 수집 (CASH·REAL_ESTATE 제외 — yfinance 조회 불가)
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

    # 실제 포트폴리오 holdings 사전 조회 — 보유 종목도 yfinance 다운로드에 포함
    real_asset_types: list[str] | None = None
    if portfolios and all(p.base_type == "STOCK_ONLY" for p in portfolios):
        real_asset_types = ["STOCK_KIS", "STOCK_OTHER", "STOCK_KIWOOM"]

    real_holdings: list[dict] | None = None
    if req.include_real_portfolio:
        real_holdings = await _get_real_portfolio_holdings(user_id, db, asset_types=real_asset_types)
        if real_holdings:
            for rh in real_holdings:
                sym = _to_yf_symbol(rh["ticker"], rh["market"])
                if sym not in all_symbols:
                    all_symbols.append(sym)

    # 3. yfinance 히스토리컬 일괄 다운로드
    loop = asyncio.get_running_loop()
    price_data: dict[str, list[tuple[str, float]]] = await loop.run_in_executor(
        None,
        partial(_sync_download_history, all_symbols, req.start_date, req.end_date, req.reinvest_dividends),
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
        # PortfolioItem 모델 → dict 변환 (backtest 내부 함수 호환)
        investable = [
            {"ticker": h.ticker, "market": h.market, "weight": float(h.weight), "name": h.name}
            for h in p.items
            if h.ticker not in _BACKTEST_SKIP_TICKERS
            and h.market not in _BACKTEST_SKIP_MARKETS
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
            spy_p = spy_prices.get(d)
            if spy_p and base_price is None:
                base_price = spy_p
            if base_price and base_price > 0:
                spy_vals.append(round((spy_prices.get(d, base_price) / base_price) * 100, 4))
            else:
                spy_vals.append(100.0)
        spy_series = SeriesData(name="S&P 500", values=spy_vals)
        all_series.append(spy_series)
        all_metrics.append(_compute_metrics("S&P 500", spy_vals))

    # 7. 실제 포트폴리오 시리즈 — 최신 스냅샷 positions 비중 기반 yfinance 백테스팅
    if req.include_real_portfolio and real_holdings:
        s, m = _compute_portfolio_series("실제 포트폴리오", real_holdings, price_data, dates)
        all_series.append(s)
        all_metrics.append(m)

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

    # 월 말 기준으로 리샘플
    monthly = close.resample("ME").last()

    # 월별 수익률 계산
    returns = monthly.pct_change().dropna(how="all")

    # 충분한 데이터가 있는 심볼만 유지 (6개월 이상)
    valid_cols = [col for col in returns.columns if returns[col].count() >= 6]
    if not valid_cols:
        return [], []

    returns = returns[valid_cols]

    # 상관계수 행렬
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
