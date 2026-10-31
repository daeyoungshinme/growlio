"""통합 포트폴리오 CRUD API (백테스팅·리밸런싱 공용). DB 변경은 `services/portfolio/portfolio_crud_service`."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_or_404
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.portfolio import (
    IndexGroupSuggestionResponse,
    PortfolioCreate,
    PortfolioReorderRequest,
    PortfolioResponse,
    PortfolioUpdate,
)
from app.services.etf.index_exposure_service import get_index_group_suggestions
from app.services.portfolio import portfolio_crud_service as crud
from app.utils.cache_invalidation import invalidate_rebalancing_analysis_cache, invalidate_user_caches
from app.utils.cache_keys import TTL_PORTFOLIO_LIST, get_cached_json, insights_key, portfolio_list_key, set_cached_json

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=list[PortfolioResponse])
@limiter.limit("60/minute")
async def list_portfolios(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """저장된 포트폴리오 목록."""
    cache = await get_cache_store()
    cache_key = portfolio_list_key(current_user.id)
    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return cached

    portfolios = await crud.list_portfolios(db, current_user.id)
    result = [PortfolioResponse.model_validate(p).model_dump(mode="json") for p in portfolios]

    await set_cached_json(cache, cache_key, result, TTL_PORTFOLIO_LIST)
    return result


@router.get("/index-group-suggestions", response_model=IndexGroupSuggestionResponse)
@limiter.limit("10/minute")
async def index_group_suggestions(
    request: Request,
    account_ids: list[uuid.UUID] | None = Query(default=None, max_length=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 종목 기준 지수 그룹 제안(plans/74) — 같은 지수 추종 ETF 묶음 + 대표·국내 대체 매수 종목. 저장 안 함."""
    await crud.validate_owned_account_ids(db, current_user.id, account_ids)
    cache = await get_cache_store()
    return await get_index_group_suggestions(cache, db, current_user.id, account_ids or None)


@router.post("", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_portfolio(
    request: Request,
    body: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """새 포트폴리오 생성."""
    portfolio = await crud.create_portfolio(db, current_user.id, body)

    cache = await get_cache_store()
    await invalidate_user_caches(cache, portfolio_list_key(current_user.id), insights_key(current_user.id))
    return portfolio


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
@limiter.limit("30/minute")
async def update_portfolio(
    request: Request,
    portfolio_id: uuid.UUID,
    body: PortfolioUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 수정."""
    portfolio = await crud.update_portfolio(db, current_user.id, portfolio_id, body)

    cache = await get_cache_store()
    await invalidate_user_caches(cache, portfolio_list_key(current_user.id), insights_key(current_user.id))
    await invalidate_rebalancing_analysis_cache(cache, current_user.id, portfolio_id)
    return portfolio


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_portfolio(
    request: Request,
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 삭제."""
    portfolio = await get_owned_or_404(db, Portfolio, portfolio_id, current_user.id, crud.PORTFOLIO_NOT_FOUND)

    await db.delete(portfolio)
    await db.commit()

    cache = await get_cache_store()
    await invalidate_user_caches(cache, portfolio_list_key(current_user.id), insights_key(current_user.id))
    await invalidate_rebalancing_analysis_cache(cache, current_user.id, portfolio_id)


@router.patch("/reorder", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def reorder_portfolios(
    request: Request,
    body: PortfolioReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 순서 일괄 업데이트."""
    if not body.items:
        return
    await crud.reorder_portfolios(db, current_user.id, body.items)

    cache = await get_cache_store()
    await invalidate_user_caches(cache, portfolio_list_key(current_user.id))
