"""포트폴리오 API — 전체 계좌 통합 조회."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.user import User
from app.services.portfolio_history_service import get_allocation_history
from app.services.portfolio_service import build_portfolio_overview
from app.services.rebalancing.strategy_service import get_rebalancing_strategy
from app.services.risk_service import get_portfolio_risk_metrics

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/allocation-history")
@limiter.limit("20/minute")
async def portfolio_allocation_history(
    request: Request,
    months: int = Query(default=12, ge=3, le=36),
    account_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """월별 자산 유형별 배분 이력 — 최근 N개월. account_id 미지정 시 전체 계좌 통합 기준."""
    cache = await get_cache_store()
    return await get_allocation_history(
        current_user.id,
        db,
        months=months,
        cache=cache,
        account_id=uuid.UUID(account_id) if account_id else None,
    )


@router.get("/overview")
@limiter.limit("10/minute")
async def portfolio_overview(
    request: Request,
    lite: bool = Query(default=False),
    account_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌 자산을 통합해 포트폴리오 현황을 반환한다. account_id 미지정 시 전체 계좌 통합 기준."""
    cache = await get_cache_store()
    account_ids = [uuid.UUID(account_id)] if account_id else None
    return await build_portfolio_overview(current_user.id, db, account_ids=account_ids, cache=cache, lite=lite)


# ---------------------------------------------------------------------------
# 위험 분석
# ---------------------------------------------------------------------------


@router.get("/risk")
@limiter.limit("5/minute")
async def portfolio_risk(
    request: Request,
    portfolio_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 위험 지표 — VaR, 베타, 변동성, 분산도. portfolio_id 미지정 시 전체 계좌 통합 기준."""
    cache = await get_cache_store()
    return await get_portfolio_risk_metrics(current_user.id, db, cache, portfolio_id=portfolio_id)


@router.get("/rebalancing-strategy")
@limiter.limit("3/minute")
async def portfolio_rebalancing_strategy(
    request: Request,
    portfolio_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """팩터·프론티어 분석 기반 리밸런싱 전략 제시."""
    cache = await get_cache_store()
    result = await get_rebalancing_strategy(current_user.id, portfolio_id, db, cache)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result
