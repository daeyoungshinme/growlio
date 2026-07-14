"""현재가 조회 서비스.

우선순위:
  1. 국내(KOSPI/KOSDAQ): Naver Finance → pykrx → Yahoo Finance → KIS API
  2. 해외: Yahoo Finance (API 키 불필요, ~15분 지연) → KIS API (설정된 경우, 실시간)

Yahoo Finance가 Render 등 클라우드 호스팅 IP를 차단해 401을 반환하는 경우를 대비해
국내 종목은 Naver/pykrx를 우선 시도한다 (yfinance 함수 → yahoo_price.py,
국내 폴백 함수 → price_sync_sources.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from functools import partial

import structlog
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DOMESTIC_MARKETS
from app.models.asset import AssetAccount
from app.services.credential_service import decrypt
from app.services.price_sync_sources import sync_naver_price, sync_pykrx_price
from app.services.yahoo_price import (
    _sync_calc_returns_batch,
    _sync_pykrx_returns_batch,
    _sync_yahoo_batch,
    _sync_yahoo_price,
    _yfinance_sem,
)
from app.utils.cache_keys import (
    TTL_PRICE_CURRENT,
    TTL_PRICE_RETURN,
    RedisType,
    current_price_key,
    price_return_key,
)
from app.utils.circuit_breaker import CircuitOpenError, naver_circuit, yahoo_circuit

logger = structlog.get_logger()


async def _domestic_price_fallback(ticker: str, loop: asyncio.AbstractEventLoop) -> float | None:
    """국내 종목 전용 폴백: Naver Finance → pykrx 순으로 시도."""
    try:
        price = await naver_circuit.call(loop.run_in_executor, None, partial(sync_naver_price, ticker))
    except CircuitOpenError:
        price = None
    except Exception as e:
        logger.warning("naver_price_failed", ticker=ticker, error=str(e))
        price = None
    if price:
        return price

    return await loop.run_in_executor(None, partial(sync_pykrx_price, ticker))


async def fetch_current_price(
    user_id: uuid.UUID,
    ticker: str,
    market: str,
    db: AsyncSession,
    redis: RedisType = None,
) -> float | None:
    """단일 종목 현재가 조회.
    Redis 15분 캐시 → (국내: Naver/pykrx →) Yahoo Finance → KIS 순으로 시도한다.
    """
    cache_key = current_price_key(ticker, market)
    if redis:
        with contextlib.suppress(RedisError):
            cached = await redis.get(cache_key)
            if cached:
                return float(cached)

    loop = asyncio.get_running_loop()

    price: float | None = None
    if market.upper() in DOMESTIC_MARKETS:
        price = await _domestic_price_fallback(ticker, loop)

    if not price and yahoo_circuit.is_available():
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
        with contextlib.suppress(RedisError):
            await redis.set(cache_key, str(price), ex=TTL_PRICE_CURRENT)

    return price


async def _read_cached_prices(redis: RedisType, tickers: list[tuple[str, str]]) -> dict[str, float]:
    """배치 대상 티커의 Redis 현재가 캐시를 일괄 조회."""
    price_map: dict[str, float] = {}
    if not redis:
        return price_map
    with contextlib.suppress(RedisError):
        cached_values = await redis.mget([current_price_key(t, m) for t, m in tickers])
        for (ticker, _), cached in zip(tickers, cached_values, strict=False):
            if cached:
                price_map[ticker] = float(cached)
    return price_map


async def _write_cached_prices(redis: RedisType, tickers: list[tuple[str, str]], price_map: dict[str, float]) -> None:
    """새로 조회된 가격을 Redis 현재가 캐시에 저장."""
    if not redis:
        return
    newly_fetched = [(t, m) for t, m in tickers if price_map.get(t)]
    if not newly_fetched:
        return
    with contextlib.suppress(RedisError):
        await asyncio.gather(
            *(
                redis.set(current_price_key(ticker, market), str(price_map[ticker]), ex=TTL_PRICE_CURRENT)
                for ticker, market in newly_fetched
            )
        )


async def fetch_prices_batch(
    user_id: uuid.UUID,
    tickers: list[tuple[str, str]],
    db: AsyncSession,
    redis: RedisType = None,
) -> dict[str, float]:
    """여러 종목 현재가를 한 번에 조회. {ticker: price}

    국내 종목은 Naver/pykrx로 먼저 채우고, 남은 종목만 Yahoo Finance 배치 조회 →
    그래도 실패한 종목은 KIS로 보완한다. Redis 15분 캐시를 우선 조회하고, 새로 조회한 가격은 캐시에 반영한다.
    """
    if not tickers:
        return {}

    loop = asyncio.get_running_loop()
    price_map: dict[str, float] = await _read_cached_prices(redis, tickers)
    remaining = [(t, m) for t, m in tickers if t not in price_map]

    domestic = [(t, m) for t, m in remaining if m.upper() in DOMESTIC_MARKETS]
    if domestic:
        domestic_results = await asyncio.gather(
            *(_domestic_price_fallback(t, loop) for t, _ in domestic), return_exceptions=True
        )
        for (ticker, _), result in zip(domestic, domestic_results, strict=False):
            if isinstance(result, (int, float)) and result > 0:
                price_map[ticker] = float(result)

    yahoo_targets = [(t, m) for t, m in remaining if t not in price_map]
    if yahoo_targets and yahoo_circuit.is_available():
        async with _yfinance_sem:
            yahoo_map = await loop.run_in_executor(None, partial(_sync_yahoo_batch, yahoo_targets))
        if yahoo_map:
            yahoo_circuit.record_success()
        else:
            yahoo_circuit.record_failure()
        price_map.update(yahoo_map)

    missing = [(t, m) for t, m in remaining if t not in price_map or price_map[t] == 0]
    if missing:
        account = await _get_any_kis_account(user_id, db)
        if account:
            fallback_tasks = [_fetch_fallback(account, ticker, market, db, redis) for ticker, market in missing]
            results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
            for (ticker, _), result in zip(missing, results, strict=False):
                if isinstance(result, (int, float)) and result > 0:
                    price_map[ticker] = float(result)

    await _write_cached_prices(redis, remaining, price_map)

    return price_map


async def get_historical_returns(
    tickers: list[tuple[str, str]],
    redis: RedisType = None,
    years: int = 10,
) -> dict[tuple[str, str], dict]:
    """각 종목의 최근 N년 누적/연환산 수익률을 반환한다.

    Yahoo Finance는 종목별 개별 호출 대신 한 번의 batch download로 조회한다(`_sync_calc_returns_batch`).
    Yahoo가 실패했거나(클라우드 호스팅 IP 차단 등) 회로가 열려 있어도, 국내(KOSPI/KOSDAQ) 종목은
    pykrx로 보완한다(`_sync_pykrx_returns_batch`) — 해외 종목은 대체 소스가 없어 그대로 누락된다.
    """
    if not tickers:
        return {}

    loop = asyncio.get_running_loop()
    return_map: dict[tuple[str, str], dict] = {}
    missing: list[tuple[str, str]] = []

    for ticker, market in tickers:
        cached = None
        if redis:
            with contextlib.suppress(RedisError):
                cached = await redis.get(price_return_key(years, ticker, market))
        if cached:
            return_map[(ticker, market)] = json.loads(cached)
        else:
            missing.append((ticker, market))

    newly_fetched: dict[tuple[str, str], dict] = {}

    if missing and yahoo_circuit.is_available():
        async with _yfinance_sem:
            batch_result = await loop.run_in_executor(None, partial(_sync_calc_returns_batch, missing, years))
        if batch_result:
            yahoo_circuit.record_success()
        else:
            yahoo_circuit.record_failure()
        newly_fetched.update(batch_result)
        missing = [tm for tm in missing if tm not in batch_result]

    domestic_missing = [(t, m) for t, m in missing if m.upper() in DOMESTIC_MARKETS]
    if domestic_missing:
        pykrx_result = await loop.run_in_executor(None, partial(_sync_pykrx_returns_batch, domestic_missing, years))
        newly_fetched.update(pykrx_result)

    return_map.update(newly_fetched)

    if newly_fetched and redis:
        with contextlib.suppress(RedisError):
            await asyncio.gather(
                *(
                    redis.setex(price_return_key(years, t, m), TTL_PRICE_RETURN, json.dumps(result))
                    for (t, m), result in newly_fetched.items()
                )
            )

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


async def _fetch_fallback(
    account: AssetAccount, ticker: str, market: str, db: AsyncSession, redis: RedisType
) -> float | None:
    try:
        price = await _price_via_kis(account, ticker, market, db, redis)
        if price:
            return price
    except Exception as e:
        logger.warning("kis_price_fallback_failed", ticker=ticker, error=str(e), exc_type=type(e).__name__)
    return None


async def _price_via_kis(
    account: AssetAccount, ticker: str, market: str, db: AsyncSession, redis: RedisType
) -> float | None:
    from app.kis.auth import get_access_token

    app_key = decrypt(account.kis_app_key)  # type: ignore[arg-type]
    app_secret = decrypt(account.kis_app_secret)  # type: ignore[arg-type]
    is_mock = account.is_mock_mode
    token = await get_access_token(
        app_key,
        app_secret,
        is_mock=is_mock,
        redis=redis,
        db=db,
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
