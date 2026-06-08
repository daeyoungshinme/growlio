"""실시간 가격 발행 Job.

30초 간격으로 WebSocket 구독 종목의 현재가를 Yahoo Finance로 조회해 broadcast한다.
구독자가 없으면 조회를 건너뛴다.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial

import structlog

from app.services.yahoo_price import _sync_yahoo_batch, _yfinance_sem
from app.utils.circuit_breaker import yahoo_circuit
from app.ws.connection_manager import manager

logger = structlog.get_logger()


async def run_price_broadcast() -> None:
    """구독 중인 종목의 현재가를 Yahoo Finance로 일괄 조회해 WebSocket 클라이언트에 전송."""
    if manager.connection_count == 0:
        return

    tickers = manager.get_all_subscribed_tickers()
    if not tickers:
        return

    logger.debug(
        "price_broadcast_start",
        ticker_count=len(tickers),
        connections=manager.connection_count,
    )

    if not yahoo_circuit.is_available():
        logger.debug("price_broadcast_skipped_circuit_open")
        return

    loop = asyncio.get_running_loop()
    try:
        async with _yfinance_sem:
            price_map: dict[str, float] = await loop.run_in_executor(
                None, partial(_sync_yahoo_batch, tickers)
            )
        if price_map:
            yahoo_circuit.record_success()
        else:
            yahoo_circuit.record_failure()
            return
    except Exception as e:
        logger.warning("price_broadcast_fetch_failed", error=str(e))
        yahoo_circuit.record_failure()
        return

    ticker_to_market = {t: m for t, m in tickers}
    updated_at = datetime.now(UTC).isoformat()

    prices = {
        ticker: {
            "price": price,
            "market": ticker_to_market.get(ticker, ""),
            "updated_at": updated_at,
        }
        for ticker, price in price_map.items()
        if price > 0
    }

    if prices:
        await manager.broadcast_prices(prices)
        logger.debug("price_broadcast_done", sent=len(prices))
