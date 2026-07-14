"""종목 검색 및 환율 조회 API."""

from __future__ import annotations

import asyncio
import re
from functools import partial

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.constants import DOMESTIC_MARKETS
from app.kis.constants import OVERSEAS_MARKETS
from app.limiter import limiter
from app.redis_client import get_redis
from app.services.recommendation_universe import guess_asset_class, resolve_index_region
from app.utils.cache_keys import (
    TTL_ETF_INDEX_REGION,
    TTL_PRICE_CURRENT,
    current_price_key,
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

EXCHANGE_TO_MARKET: dict[str, str] = {
    "KSC": "KOSPI",
    "KOE": "KOSDAQ",
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NYQ": "NYSE",
    "PCX": "NYSE",
    "ASE": "AMEX",
}

_KOREAN_RE = re.compile(r"[가-힣]")


def _has_korean(text: str) -> bool:
    return bool(_KOREAN_RE.search(text))


async def _search_naver(q: str, limit: int) -> list[dict]:
    """네이버 금융 자동완성 — 한글 종목명 검색용."""
    url = "https://ac.stock.naver.com/ac"
    params = {"q": q, "target": "stock,index"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("naver_search_failed", q=q, error=str(e))
        return []

    results = []
    for item in data.get("items", []):
        type_code = item.get("typeCode", "")
        market = type_code if type_code in ("KOSPI", "KOSDAQ") else type_code
        ticker = item.get("code", "")
        name = item.get("name", "")
        results.append(
            {
                "ticker": ticker,
                "name": name,
                "market": market,
                "exchange": type_code,
                "asset_class": guess_asset_class(name),
                "index_region": resolve_index_region(ticker, market, None),
            }
        )
        if len(results) >= limit:
            break
    return results


async def _search_yahoo(q: str, limit: int) -> list[dict]:
    """Yahoo Finance 검색 — 영문명·티커 검색용."""
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params: dict[str, str | int] = {"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("yahoo_search_failed", q=q, error=str(e))
        return []

    results = []
    for item in data.get("quotes", []):
        if item.get("quoteType") not in ("EQUITY", "ETF"):
            continue
        exchange = item.get("exchange", "")
        market = EXCHANGE_TO_MARKET.get(exchange, exchange)
        symbol: str = item.get("symbol", "")
        ticker = symbol.removesuffix(".KS").removesuffix(".KQ")
        name = item.get("shortname") or item.get("longname") or symbol
        results.append(
            {
                "ticker": ticker,
                "name": name,
                "market": market,
                "exchange": exchange,
                "asset_class": guess_asset_class(name),
                "index_region": resolve_index_region(ticker, market, None),
            }
        )
        if len(results) >= limit:
            break
    return results


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

    from app.services.dividend_sync_sources import sync_naver_etf_index_region

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


@router.get("/price")
@limiter.limit("60/minute")
async def get_stock_price(
    request: Request,
    ticker: str = Query(..., min_length=1, max_length=20),
    market: str = Query(...),
    redis: aioredis.Redis = Depends(get_redis),
):
    """단일 종목 현재가 조회 (인증 불필요 — Yahoo Finance).
    해외 종목은 USD → KRW 변환 후 반환. Redis 캐시 TTL 900s.
    """
    from app.services.yahoo_price import _sync_usdkrw, _sync_yahoo_price

    cache_key = current_price_key(ticker, market)
    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    loop = asyncio.get_running_loop()
    price = await loop.run_in_executor(None, partial(_sync_yahoo_price, ticker, market))
    if not price:
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


class _BatchRequest(BaseModel):
    items: list[_TickerMarket] = Field(..., max_length=50)


@router.post("/prices-batch")
@limiter.limit("60/minute")
async def get_stock_prices_batch(
    request: Request,
    body: _BatchRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    """복수 종목 현재가 일괄 조회. yfinance 단 1회 호출로 N개 조회.
    Response: {ticker: {price_krw, price_usd, usd_rate}}
    """
    from app.services.yahoo_price import _sync_usdkrw, _sync_yahoo_batch

    if not body.items:
        return {}

    # 캐시 히트 먼저 처리
    result: dict[str, dict] = {}
    to_fetch: list[tuple[str, str]] = []
    for item in body.items:
        cache_key = current_price_key(item.ticker, item.market)
        cached = await get_cached_json(redis, cache_key)
        if cached is not None:
            result[item.ticker] = cached
        else:
            to_fetch.append((item.ticker, item.market))

    if not to_fetch:
        return result

    # 배치 조회 (단 1회 yfinance.download)
    loop = asyncio.get_running_loop()
    price_map = await loop.run_in_executor(None, partial(_sync_yahoo_batch, to_fetch))

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
            await set_cached_json(redis, current_price_key(ticker, market), entry, TTL_PRICE_CURRENT)

    return result
