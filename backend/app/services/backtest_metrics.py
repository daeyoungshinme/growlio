"""백테스팅 순수 계산 함수.

I/O 없는 수학 로직만 포함 — 테스트 시 외부 의존성 불필요.
"""
from __future__ import annotations

import math

from app.schemas.backtest import PortfolioMetrics, SeriesData
from app.services.yahoo_price import to_yf_symbol as _to_yf_symbol

_TRADING_DAYS_PER_YEAR = 252


def compute_metrics(name: str, values: list[float]) -> PortfolioMetrics:
    """수익률 시리즈로 주요 지표(CAGR, MDD, Sharpe, Sortino) 계산."""
    if len(values) < 2:
        return PortfolioMetrics(
            name=name, total_return_pct=0, cagr_pct=0, mdd_pct=0,
            sharpe_ratio=0, volatility_pct=0, sortino_ratio=0,
        )

    total_return = (values[-1] / 100.0 - 1) * 100
    years = len(values) / _TRADING_DAYS_PER_YEAR
    cagr = ((values[-1] / 100.0) ** (1 / years) - 1) * 100 if years > 0 else 0

    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

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

    sharpe = (mean_r / std_r * math.sqrt(_TRADING_DAYS_PER_YEAR)) if std_r > 0 else 0
    volatility_pct = std_r * math.sqrt(_TRADING_DAYS_PER_YEAR) * 100

    downside_rets = [r for r in daily_rets if r < 0]
    if len(downside_rets) >= 2:
        ds_mean = sum(downside_rets) / len(downside_rets)
        ds_var = sum((r - ds_mean) ** 2 for r in downside_rets) / (len(downside_rets) - 1)
        ds_std = math.sqrt(ds_var) if ds_var > 0 else 0
        sortino = (mean_r / ds_std * math.sqrt(_TRADING_DAYS_PER_YEAR)) if ds_std > 0 else 0
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


def compute_portfolio_series(
    name: str,
    holdings: list[dict],
    price_data: dict[str, list[tuple[str, float]]],
    dates: list[str],
) -> tuple[SeriesData, PortfolioMetrics]:
    """holdings의 Buy & Hold 수익률 시리즈 계산."""
    sym_map: dict[str, str] = {}
    weight_map: dict[str, float] = {}
    for h in holdings:
        sym = _to_yf_symbol(h["ticker"], h["market"])
        sym_map[h["ticker"]] = sym
        weight_map[sym] = h["weight"] / 100.0

    price_by_sym: dict[str, dict[str, float]] = {}
    for sym in sym_map.values():
        if sym in price_data:
            price_by_sym[sym] = dict(price_data[sym])

    init_prices: dict[str, float] = {}
    for sym in sym_map.values():
        p = price_by_sym.get(sym, {})
        for d in dates:
            if d in p and p[d] > 0:
                init_prices[sym] = p[d]
                break

    if not init_prices:
        empty_vals: list[float] = [100.0] * len(dates)
        metrics = compute_metrics(name, empty_vals)
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
        if total_weight > 0:
            portfolio_val = (portfolio_val / total_weight) * 100
        else:
            portfolio_val = values[-1] if values else 100.0
        values.append(round(portfolio_val, 4))

    metrics = compute_metrics(name, values)
    return SeriesData(name=name, values=values), metrics
