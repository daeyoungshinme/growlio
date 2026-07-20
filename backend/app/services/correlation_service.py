"""포트폴리오 내 종목 간 월별 수익률 상관관계 분석 — backtest_service.py에서 분리.

run_backtest(백테스트 실행)와 별개 스키마(CorrelationRequest/Result)를 쓰는 독립 기능.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from functools import partial

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import CASH_EQUIVALENT_TICKER
from app.models.portfolio import Portfolio
from app.schemas.backtest import CorrelationRequest, CorrelationResult
from app.services.yahoo_price import to_yf_symbol as _to_yf_symbol
from app.utils.circuit_breaker import yahoo_circuit

logger = structlog.get_logger()

_BACKTEST_SKIP_TICKERS = {"CASH", "REAL_ESTATE", CASH_EQUIVALENT_TICKER}
_BACKTEST_SKIP_MARKETS = {"KR_PROPERTY"}


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

    if not yahoo_circuit.is_available():
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
        yahoo_circuit.record_failure()
        return [], []

    if raw is None or (hasattr(raw, "empty") and raw.empty):
        yahoo_circuit.record_failure()
        return [], []

    close = raw.get("Close") if isinstance(raw.columns, pd.MultiIndex) else raw
    if close is None or (hasattr(close, "empty") and close.empty):
        yahoo_circuit.record_failure()
        return [], []
    yahoo_circuit.record_success()

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
        for item in port.items or []:
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
