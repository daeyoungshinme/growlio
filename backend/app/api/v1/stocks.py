"""종목 검색 및 환율 조회 API."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1._account_deps import get_owned_account
from app.constants import DOMESTIC_MARKETS
from app.core.cache_store import CacheStore, get_cache_store
from app.core.database import get_db
from app.kis.constants import OVERSEAS_MARKETS
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.user import User
from app.schemas.stock import StockPriceBatchRequest
from app.services.goal.recommendation_universe import resolve_index_region
from app.services.market_data.price_service import fetch_prices_batch
from app.services.market_data.stock_search_service import search_stocks_by_query
from app.utils.cache_keys import (
    TTL_ETF_INDEX_REGION,
    etf_index_region_key,
    get_cached_json,
    set_cached_json,
)
from app.utils.cache_keys import (
    USD_KRW_RATE as _USD_KRW_KEY,
)
from app.utils.currency import refresh_usd_krw

logger = structlog.get_logger()

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("/search")
@limiter.limit("30/minute")
async def search_stocks(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=20),
):
    """종목명·티커 검색.
    한글 입력 → 네이버 금융, 영문/티커 → Yahoo Finance.
    """
    return await search_stocks_by_query(q, limit)


@router.get("/index-region")
@limiter.limit("30/minute")
async def get_index_region(
    request: Request,
    ticker: str = Query(..., min_length=1, max_length=20),
    market: str = Query(...),
    cache: CacheStore = Depends(get_cache_store),
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
    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return cached

    from app.services.dividend.sync_sources import sync_naver_etf_index_region

    loop = asyncio.get_running_loop()
    fetched = await loop.run_in_executor(None, sync_naver_etf_index_region, ticker)
    index_region = fetched if fetched is not None else resolve_index_region(ticker, market, None)

    result = {"index_region": index_region}
    await set_cached_json(cache, cache_key, result, TTL_ETF_INDEX_REGION)
    return result


@router.get("/exchange-rate")
@limiter.limit("10/minute")
async def get_exchange_rate(request: Request, cache: CacheStore = Depends(get_cache_store)):
    """현재 USD/KRW 환율 조회 (캐시 → yfinance, ~15분 지연)."""
    cached = await cache.get(_USD_KRW_KEY)
    if cached:
        return {"usd_krw": float(cached), "is_fallback": False}
    rate, is_live = await refresh_usd_krw(cache)
    # is_fallback이면 프론트는 환율 없음과 같게 다룬다 — 구버전 앱을 위해 usd_krw는 계속 내려준다
    return {"usd_krw": rate, "is_fallback": not is_live}


async def _owned_kis_accounts(
    account_ids: dict[str, uuid.UUID], current_user: User, db: AsyncSession
) -> dict[str, AssetAccount]:
    """티커별로 지정된 계좌 중 소유가 확인된 것만 남긴다 — 남의 계좌·삭제된 계좌는 KIS 폴백 없이 조용히 건너뛴다."""
    owned: dict[uuid.UUID, AssetAccount | None] = {}
    result: dict[str, AssetAccount] = {}
    for ticker, account_id in account_ids.items():
        if account_id not in owned:
            try:
                owned[account_id] = await get_owned_account(account_id, current_user.id, db)
            except Exception as e:
                logger.warning("kis_price_account_rejected", ticker=ticker, error=str(e), exc_type=type(e).__name__)
                owned[account_id] = None
        account = owned[account_id]
        if account is not None:
            result[ticker] = account
    return result


async def _price_entries(
    items: list[tuple[str, str, uuid.UUID | None]],
    current_user: User,
    db: AsyncSession,
    cache: CacheStore,
) -> dict[str, dict]:
    """{ticker: {price_krw, price_usd, usd_rate}} — 시세는 내부와 같은 `fetch_prices_batch`
    (캐시 → 국내 Naver/pykrx → Yahoo → 지정 계좌 KIS)로 얻고, 해외 종목만 환율로 환산한다.
    원시 시세가 캐시되므로 환산 결과는 캐시하지 않는다(fallback 환율 금액이 TTL 동안 남지 않게)."""
    tickers = [(t, m) for t, m, _ in items]
    account_ids = {t: a for t, _, a in items if a is not None}
    kis_accounts = await _owned_kis_accounts(account_ids, current_user, db)
    price_map = await fetch_prices_batch(current_user.id, tickers, db, cache, kis_accounts=kis_accounts)

    usd_rate = 0.0
    if any(m in OVERSEAS_MARKETS and price_map.get(t) for t, m in tickers):
        usd_rate, _is_live = await refresh_usd_krw(cache)

    result: dict[str, dict] = {}
    for ticker, market in tickers:
        price = price_map.get(ticker)
        if not price:
            logger.warning("price_lookup_exhausted", ticker=ticker, market=market, had_account_id=ticker in account_ids)
            result[ticker] = {"price_krw": None, "price_usd": None, "usd_rate": None}
        elif market in OVERSEAS_MARKETS:
            result[ticker] = {
                "price_krw": round(price * usd_rate) if usd_rate else None,
                "price_usd": round(price, 2),
                "usd_rate": usd_rate or None,
            }
        else:
            result[ticker] = {"price_krw": price, "price_usd": None, "usd_rate": None}
    return result


@router.get("/price")
@limiter.limit("60/minute")
async def get_stock_price(
    request: Request,
    ticker: str = Query(..., min_length=1, max_length=20),
    market: str = Query(...),
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheStore = Depends(get_cache_store),
):
    """단일 종목 현재가 조회 — `/prices-batch`와 같은 경로(`_price_entries`).
    `account_id`(KIS 연동 보유 계좌)는 다른 소스가 전부 실패했을 때만 쓴다. 해외 종목은 USD → KRW 환산.
    """
    entries = await _price_entries([(ticker, market.upper(), account_id)], current_user, db, cache)
    return entries[ticker]


@router.post("/prices-batch")
@limiter.limit("60/minute")
async def get_stock_prices_batch(
    request: Request,
    body: StockPriceBatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheStore = Depends(get_cache_store),
):
    """복수 종목 현재가 일괄 조회.
    Response: {ticker: {price_krw, price_usd, usd_rate}}
    ticker 키라 같은 티커가 여러 시장으로 오면 마지막 것만 남는다(계약 유지).
    """
    if not body.items:
        return {}
    items = [(item.ticker, item.market.upper(), item.account_id) for item in body.items]
    return await _price_entries(items, current_user, db, cache)
