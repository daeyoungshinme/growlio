"""종목 검색 및 환율 조회 API."""
from __future__ import annotations

import asyncio
import re
from functools import partial

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Query

from app.redis_client import get_redis

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
        results.append({
            "ticker": item.get("code", ""),
            "name": item.get("name", ""),
            "market": market,
            "exchange": type_code,
        })
        if len(results) >= limit:
            break
    return results


async def _search_yahoo(q: str, limit: int) -> list[dict]:
    """Yahoo Finance 검색 — 영문명·티커 검색용."""
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0}
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
        results.append({"ticker": ticker, "name": name, "market": market, "exchange": exchange})
        if len(results) >= limit:
            break
    return results


@router.get("/search")
async def search_stocks(q: str = Query(..., min_length=1), limit: int = Query(8, le=20)):
    """종목명·티커 검색.
    한글 입력 → 네이버 금융, 영문/티커 → Yahoo Finance.
    """
    if _has_korean(q):
        return await _search_naver(q, limit)
    return await _search_yahoo(q, limit)


def _sync_usdkrw() -> float:
    import yfinance as yf
    try:
        hist = yf.Ticker("USDKRW=X").history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            if rate > 0:
                return rate
    except Exception as e:
        logger.warning("usdkrw_fetch_failed", error=str(e))
    return 1350.0  # 조회 실패 시 기본값


_REDIS_USD_KRW_KEY = "usd_krw_rate"
_EXCHANGE_RATE_CACHE_TTL = 300  # 5분


@router.get("/exchange-rate")
async def get_exchange_rate(redis: aioredis.Redis = Depends(get_redis)):
    """현재 USD/KRW 환율 조회 (Redis 캐시 → yfinance, ~15분 지연)."""
    cached = await redis.get(_REDIS_USD_KRW_KEY)
    if cached:
        return {"usd_krw": float(cached)}
    loop = asyncio.get_event_loop()
    rate = await loop.run_in_executor(None, _sync_usdkrw)
    await redis.set(_REDIS_USD_KRW_KEY, rate, ex=_EXCHANGE_RATE_CACHE_TTL)
    return {"usd_krw": rate}


OVERSEAS_MARKETS = {"NYSE", "NASDAQ", "AMEX"}


@router.get("/price")
async def get_stock_price(ticker: str = Query(...), market: str = Query(...)):
    """단일 종목 현재가 조회 (인증 불필요 — Yahoo Finance).
    해외 종목은 USD → KRW 변환 후 반환.
    """
    from functools import partial as _partial
    from app.services.price_service import _sync_yahoo_price

    loop = asyncio.get_event_loop()
    price = await loop.run_in_executor(None, _partial(_sync_yahoo_price, ticker, market))
    if not price:
        return {"price_krw": None, "price_usd": None, "usd_rate": None}

    if market in OVERSEAS_MARKETS:
        usd_rate = await loop.run_in_executor(None, _sync_usdkrw)
        return {
            "price_krw": round(price * usd_rate),
            "price_usd": price,
            "usd_rate": usd_rate,
        }

    return {"price_krw": price, "price_usd": None, "usd_rate": None}
