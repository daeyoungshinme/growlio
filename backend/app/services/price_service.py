"""현재가 조회 서비스.

우선순위:
  1. Yahoo Finance (API 키 불필요 — 국내·해외 모두 지원, ~15분 지연)
  2. KIS API (설정된 경우, 실시간)

Yahoo Finance 함수 → yahoo_price.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from functools import partial

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount
from app.services.credential_service import decrypt
from app.services.yahoo_price import (
    _sync_calc_return,
    _sync_yahoo_batch,
    _sync_yahoo_price,
    _yfinance_sem,
)
from app.utils.cache_keys import (
    TTL_PRICE_CURRENT,
    TTL_PRICE_RETURN,
    current_price_key,
    price_return_key,
)
from app.utils.circuit_breaker import yahoo_circuit

logger = structlog.get_logger()

DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ", "KRX"}


async def fetch_current_price(
    user_id: uuid.UUID,
    ticker: str,
    market: str,
    db: AsyncSession,
    redis=None,
) -> float | None:
    """단일 종목 현재가 조회.
    Redis 15분 캐시 → Yahoo Finance → KIS 순으로 시도한다.
    """
    cache_key = current_price_key(ticker, market)
    if redis:
        with contextlib.suppress(Exception):
            cached = await redis.get(cache_key)
            if cached:
                return float(cached)

    loop = asyncio.get_running_loop()

    if yahoo_circuit.is_available():
        async with _yfinance_sem:
            price = await loop.run_in_executor(None, partial(_sync_yahoo_price, ticker, market))
        if price:
            yahoo_circuit.record_success()
        else:
            yahoo_circuit.record_failure()

    if not price:
        account = await _get_any_kis_account(user_id, db)
        if account:
            try:
                price = await _price_via_kis(account, ticker, market, db, redis)
            except Exception as e:
                logger.warning("kis_price_failed", ticker=ticker, error=str(e), exc_type=type(e).__name__)

    if price and redis:
        with contextlib.suppress(Exception):
            await redis.set(cache_key, str(price), ex=TTL_PRICE_CURRENT)

    return price


async def fetch_prices_batch(
    user_id: uuid.UUID,
    tickers: list[tuple[str, str]],
    db: AsyncSession,
    redis=None,
) -> dict[str, float]:
    """여러 종목 현재가를 한 번에 조회. {ticker: price}

    Yahoo Finance 배치 조회 후, 실패한 종목만 KIS로 보완한다.
    """
    if not tickers:
        return {}

    loop = asyncio.get_running_loop()

    if yahoo_circuit.is_available():
        async with _yfinance_sem:
            price_map: dict[str, float] = await loop.run_in_executor(
                None, partial(_sync_yahoo_batch, tickers)
            )
        if price_map:
            yahoo_circuit.record_success()
        else:
            yahoo_circuit.record_failure()
    else:
        price_map = {}

    missing = [(t, m) for t, m in tickers if t not in price_map or price_map[t] == 0]
    if missing:
        account = await _get_any_kis_account(user_id, db)
        if account:
            fallback_tasks = [
                _fetch_fallback(account, ticker, market, db, redis)
                for ticker, market in missing
            ]
            results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            for (ticker, _), result in zip(missing, results):
                if isinstance(result, (int, float)) and result > 0:
                    price_map[ticker] = float(result)

    return price_map


async def get_historical_returns(
    tickers: list[tuple[str, str]],
    redis=None,
    years: int = 10,
) -> dict[tuple[str, str], dict]:
    """각 종목의 최근 N년 누적/연환산 수익률을 반환한다."""
    if not tickers:
        return {}

    loop = asyncio.get_running_loop()

    async def _get_one(ticker: str, market: str) -> dict | None:
        cache_key = price_return_key(years, ticker, market)
        if redis:
            with contextlib.suppress(Exception):
                cached = await redis.get(cache_key)
                if cached:
                    return json.loads(cached)

        if not yahoo_circuit.is_available():
            return None

        async with _yfinance_sem:
            result = await loop.run_in_executor(
                None, partial(_sync_calc_return, ticker, market, years)
            )
        if result:
            yahoo_circuit.record_success()

        if result and redis:
            with contextlib.suppress(Exception):
                await redis.setex(cache_key, TTL_PRICE_RETURN, json.dumps(result))

        return result

    tasks = [_get_one(ticker, market) for ticker, market in tickers]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    return_map: dict[tuple[str, str], dict] = {}
    for (ticker, market), res in zip(tickers, raw):
        if isinstance(res, dict):
            return_map[(ticker, market)] = res

    return return_map


async def _get_any_kis_account(user_id: uuid.UUID, db: AsyncSession) -> AssetAccount | None:
    """유저의 활성 KIS 계좌 중 자격증명이 있는 첫 번째 계좌를 반환."""
    return await db.scalar(
        select(AssetAccount).where(
            AssetAccount.user_id == user_id,
            AssetAccount.data_source == "KIS_API",
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.kis_app_key != None,  # noqa: E711
        )
    )


async def _fetch_fallback(account: AssetAccount, ticker: str, market: str, db, redis) -> float | None:
    try:
        price = await _price_via_kis(account, ticker, market, db, redis)
        if price:
            return price
    except Exception as e:
        logger.warning("kis_price_fallback_failed", ticker=ticker, error=str(e), exc_type=type(e).__name__)
    return None


async def _price_via_kis(account: AssetAccount, ticker: str, market: str, db, redis) -> float | None:
    from app.kis.auth import get_access_token

    app_key = decrypt(account.kis_app_key)
    app_secret = decrypt(account.kis_app_secret)
    is_mock = account.is_mock_mode
    token = await get_access_token(
        app_key, app_secret,
        is_mock=is_mock, redis=redis, db=db,
        user_id=str(account.user_id),
        account_id=str(account.id),
    )
    if market in DOMESTIC_MARKETS:
        from app.kis.domestic_quote import get_domestic_price
        return await get_domestic_price(app_key, app_secret, token, ticker, is_mock=is_mock)
    else:
        from app.kis.overseas_quote import get_overseas_price
        result = await get_overseas_price(app_key, app_secret, token, ticker, market, is_mock=is_mock)
        return float(result.get("price", 0)) or None
