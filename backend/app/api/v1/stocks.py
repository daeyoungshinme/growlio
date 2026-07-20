"""종목 검색 및 환율 조회 API."""

from __future__ import annotations

import asyncio
import uuid
from functools import partial

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1._account_deps import get_owned_account
from app.constants import DOMESTIC_MARKETS
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.kis.constants import OVERSEAS_MARKETS
from app.limiter import limiter
from app.models.user import User
from app.services.price_service import _price_via_kis, domestic_price_fallback
from app.services.recommendation_universe import resolve_index_region
from app.services.stock_search_service import _has_korean, _search_naver, _search_yahoo
from app.utils.cache_keys import (
    TTL_ETF_INDEX_REGION,
    TTL_PRICE_CURRENT,
    current_price_display_key,
    etf_index_region_key,
    get_cached_json,
    set_cached_json,
)
from app.utils.cache_keys import (
    USD_KRW_RATE as _USD_KRW_KEY,
)
from app.utils.currency import cache_usd_krw_rate, get_usd_krw_rate

logger = structlog.get_logger()

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search")
@limiter.limit("30/minute")
async def search_stocks(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, le=20),
):
    """종목명·티커 검색.
    한글 입력 → 네이버 금융, 영문/티커 → Yahoo Finance.
    """
    if _has_korean(q):
        return await _search_naver(q, limit)
    return await _search_yahoo(q, limit)


@router.get("/index-region")
@limiter.limit("30/minute")
async def get_index_region(
    request: Request,
    ticker: str = Query(..., min_length=1, max_length=20),
    market: str = Query(...),
    redis: aioredis.Redis = Depends(get_redis),
):
    """종목이 추종하는 지수의 지역(DOMESTIC/OVERSEAS)을 조회한다.

    해외거래소 상장은 시장 구분만으로 자명하므로 네트워크 조회 없이 즉시 반환한다. KRX 상장
    종목은 Naver ETF 분석 API(`sync_naver_etf_index_region`)로 실제 추종지수의 국가별 편입
    비중을 조회해 판별 — ETF가 아니거나 조회 실패 시 `resolve_index_region`의 기존 폴백
    (큐레이션 목록 → 기본값 DOMESTIC)으로 넘어간다. 결과는 7일 캐싱(추종지수는 사실상 불변).
    """
    if market.upper() not in DOMESTIC_MARKETS:
        return {"index_region": "OVERSEAS"}

    cache_key = etf_index_region_key(ticker)
    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    from app.services.dividend.sync_sources import sync_naver_etf_index_region

    loop = asyncio.get_running_loop()
    fetched = await loop.run_in_executor(None, sync_naver_etf_index_region, ticker)
    index_region = fetched if fetched is not None else resolve_index_region(ticker, market, None)

    result = {"index_region": index_region}
    await set_cached_json(redis, cache_key, result, TTL_ETF_INDEX_REGION)
    return result


@router.get("/exchange-rate")
@limiter.limit("10/minute")
async def get_exchange_rate(request: Request, redis: aioredis.Redis = Depends(get_redis)):
    """현재 USD/KRW 환율 조회 (Redis 캐시 → yfinance, ~15분 지연)."""
    from app.services.yahoo_price import _sync_usdkrw

    cached = await redis.get(_USD_KRW_KEY)
    if cached:
        return {"usd_krw": float(cached)}
    loop = asyncio.get_running_loop()
    rate = await loop.run_in_executor(None, _sync_usdkrw)
    if rate > 0:
        await cache_usd_krw_rate(redis, rate)
    else:
        rate = await get_usd_krw_rate(redis)
    return {"usd_krw": rate}


async def _kis_price_fallback(
    account_id: uuid.UUID | None,
    ticker: str,
    market: str,
    current_user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> float | None:
    """다른 소스가 전부 실패했을 때만 쓰는 최후 폴백 — 소유 계좌 검증 후 KIS API로 조회.
    계좌 미검증/KIS 호출 실패는 가격 조회 전체를 깨지 않도록 조용히 무시한다."""
    if account_id is None:
        return None
    try:
        account = await get_owned_account(account_id, current_user.id, db)
        return await _price_via_kis(account, ticker, market, db, redis)
    except Exception as e:
        logger.warning("kis_price_endpoint_failed", ticker=ticker, error=str(e), exc_type=type(e).__name__)
        return None


@router.get("/price")
@limiter.limit("60/minute")
async def get_stock_price(
    request: Request,
    ticker: str = Query(..., min_length=1, max_length=20),
    market: str = Query(...),
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """단일 종목 현재가 조회.
    Yahoo Finance를 먼저 시도하고, 국내 종목이면서 Yahoo가 실패한 경우에만 Naver/pykrx로 폴백한다.
    그래도 없고 `account_id`(KIS 연동 보유 계좌)가 주어진 경우 최후로 KIS API를 시도한다.
    해외 종목은 USD → KRW 변환 후 반환. Redis 캐시 TTL 900s.
    """
    from app.services.yahoo_price import _sync_usdkrw, _sync_yahoo_price

    cache_key = current_price_display_key(ticker, market)
    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    loop = asyncio.get_running_loop()
    tried_stages = ["yahoo"]
    price = await loop.run_in_executor(None, partial(_sync_yahoo_price, ticker, market))
    if not price and market.upper() in DOMESTIC_MARKETS:
        tried_stages.append("domestic")
        price = await domestic_price_fallback(ticker, loop)
    if not price:
        tried_stages.append("kis" if account_id is not None else "kis_skipped_no_account")
        price = await _kis_price_fallback(account_id, ticker, market, current_user, db, redis)
    if not price:
        logger.warning("price_lookup_exhausted", ticker=ticker, market=market, tried_stages=tried_stages)
        return {"price_krw": None, "price_usd": None, "usd_rate": None}

    if market in OVERSEAS_MARKETS:
        usd_rate = await loop.run_in_executor(None, _sync_usdkrw)
        if not usd_rate:
            usd_rate = await get_usd_krw_rate(redis)
        result = {
            "price_krw": round(price * usd_rate) if usd_rate else None,
            "price_usd": price,
            "usd_rate": usd_rate or None,
        }
    else:
        result = {"price_krw": price, "price_usd": None, "usd_rate": None}

    if result["price_krw"] is not None:
        await set_cached_json(redis, cache_key, result, TTL_PRICE_CURRENT)
    return result


class _TickerMarket(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    market: str
    account_id: uuid.UUID | None = None  # KIS 연동 보유 계좌 — 다른 소스가 전부 실패했을 때만 사용


class _BatchRequest(BaseModel):
    items: list[_TickerMarket] = Field(..., max_length=50)


async def _resolve_batch_prices(
    to_fetch: list[tuple[str, str]],
    account_ids: dict[str, uuid.UUID],
    loop: asyncio.AbstractEventLoop,
    current_user: User,
    db: AsyncSession,
    redis: aioredis.Redis,
) -> dict[str, float]:
    """Yahoo 배치 조회로 먼저 채우고, 그중 국내 마켓이면서 여전히 없는 티커만 Naver/pykrx로 폴백한다.
    그래도 없고 `account_id`가 주어진 티커만 최후로 KIS API를 시도한다."""
    from app.services.yahoo_price import _sync_yahoo_batch

    price_map: dict[str, float] = await loop.run_in_executor(None, partial(_sync_yahoo_batch, to_fetch)) or {}

    domestic_missing = [(t, m) for t, m in to_fetch if t not in price_map and m.upper() in DOMESTIC_MARKETS]
    if domestic_missing:
        domestic_results = await asyncio.gather(
            *(domestic_price_fallback(t, loop) for t, _ in domestic_missing), return_exceptions=True
        )
        for (ticker, _), fallback_price in zip(domestic_missing, domestic_results, strict=False):
            if isinstance(fallback_price, (int, float)) and fallback_price > 0:
                price_map[ticker] = float(fallback_price)

    kis_missing = [(t, m) for t, m in to_fetch if t not in price_map and t in account_ids]
    if kis_missing:
        kis_results = await asyncio.gather(
            *(_kis_price_fallback(account_ids[t], t, m, current_user, db, redis) for t, m in kis_missing),
            return_exceptions=True,
        )
        for (ticker, _), kis_price in zip(kis_missing, kis_results, strict=False):
            if isinstance(kis_price, (int, float)) and kis_price > 0:
                price_map[ticker] = float(kis_price)

    still_missing = [(t, m) for t, m in to_fetch if t not in price_map]
    for ticker, market in still_missing:
        logger.warning(
            "price_lookup_exhausted",
            ticker=ticker,
            market=market,
            had_account_id=ticker in account_ids,
        )

    return price_map


@router.post("/prices-batch")
@limiter.limit("60/minute")
async def get_stock_prices_batch(
    request: Request,
    body: _BatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """복수 종목 현재가 일괄 조회.
    Response: {ticker: {price_krw, price_usd, usd_rate}}
    """
    if not body.items:
        return {}

    # 캐시 히트 먼저 처리
    result: dict[str, dict] = {}
    to_fetch: list[tuple[str, str]] = []
    account_ids: dict[str, uuid.UUID] = {}
    for item in body.items:
        cache_key = current_price_display_key(item.ticker, item.market)
        cached = await get_cached_json(redis, cache_key)
        if cached is not None:
            result[item.ticker] = cached
        else:
            to_fetch.append((item.ticker, item.market))
            if item.account_id is not None:
                account_ids[item.ticker] = item.account_id

    if not to_fetch:
        return result

    loop = asyncio.get_running_loop()
    price_map = await _resolve_batch_prices(to_fetch, account_ids, loop, current_user, db, redis)

    # 해외 종목이 있으면 환율 1회 조회
    overseas_tickers = {t for t, m in to_fetch if m in OVERSEAS_MARKETS}
    usd_rate: float = 0.0
    if overseas_tickers:
        from app.services.yahoo_price import _sync_usdkrw

        usd_rate = await loop.run_in_executor(None, _sync_usdkrw)
        if not usd_rate:
            usd_rate = await get_usd_krw_rate(redis)
        if usd_rate:
            await cache_usd_krw_rate(redis, usd_rate)

    for ticker, market in to_fetch:
        price = price_map.get(ticker)
        if not price:
            result[ticker] = {"price_krw": None, "price_usd": None, "usd_rate": None}
            continue

        if market in OVERSEAS_MARKETS:
            entry = {
                "price_krw": round(price * usd_rate) if usd_rate else None,
                "price_usd": price,
                "usd_rate": usd_rate or None,
            }
        else:
            entry = {"price_krw": price, "price_usd": None, "usd_rate": None}

        result[ticker] = entry
        if entry["price_krw"] is not None:
            await set_cached_json(redis, current_price_display_key(ticker, market), entry, TTL_PRICE_CURRENT)

    return result
