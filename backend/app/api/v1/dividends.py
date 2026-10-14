"""배당금 현황 API."""

import uuid

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PaginationDep, get_current_user, get_db
from app.core.cache_store import CacheStore, get_cache_store
from app.limiter import limiter
from app.models.user import User
from app.services.dividend.aggregator import get_dividend_summary
from app.services.dividend.drip_service import calc_monthly_optimization
from app.services.dividend.orchestrator import get_position_dividend_yields, get_ticker_dividend_summary
from app.utils.cache_keys import (
    TTL_DIVIDENDS_POSITIONS,
    dividends_positions_key,
    get_cached_json,
    set_cached_json,
)

router = APIRouter(prefix="/dividends", tags=["dividends"])
logger = structlog.get_logger()


@router.get("/summary")
@limiter.limit("10/minute")
async def dividend_summary(
    request: Request,
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: CacheStore = Depends(get_cache_store),
):
    """연간 배당 요약. account_id 미지정 시 전체 계좌 통합 기준."""
    return await get_dividend_summary(current_user.id, db, cache, account_id=account_id)


@router.get("/positions")
@limiter.limit("5/minute")
async def position_dividend_yields(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 종목별 배당수익률 및 예상 배당금 (yfinance, 비실시간). account_id 미지정 시 전체 계좌 통합 기준."""
    cache = await get_cache_store()
    cache_key = dividends_positions_key(current_user.id, str(account_id) if account_id else "all")
    if skip == 0:
        cached = await get_cached_json(cache, cache_key)
        if cached is not None:
            return cached[:limit]
    result = await get_position_dividend_yields(current_user.id, db, account_id)
    if skip == 0:
        await set_cached_json(cache, cache_key, result, TTL_DIVIDENDS_POSITIONS)
    return result[skip : skip + limit]


@router.get("/by-ticker")
@limiter.limit("10/minute")
async def ticker_dividend_summary(
    request: Request,
    pagination: PaginationDep,
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """종목별 실수령(올해) + 예상 배당금 통합 (24h 캐시). account_id 미지정 시 전체 계좌 통합 기준."""
    result = await get_ticker_dividend_summary(current_user.id, db, account_ids=[account_id] if account_id else None)
    return result[pagination.skip : pagination.skip + pagination.limit]


# ---------------------------------------------------------------------------
# 월별 균등화 제안
# ---------------------------------------------------------------------------


@router.get("/monthly-optimization")
@limiter.limit("10/minute")
async def monthly_optimization(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """배당 약한 달 추가 매수 종목 제안."""
    ticker_summaries = await get_ticker_dividend_summary(current_user.id, db)
    return calc_monthly_optimization(ticker_summaries)
