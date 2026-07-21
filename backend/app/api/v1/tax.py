from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.redis_client import get_redis
from app.limiter import limiter
from app.models.user import User
from app.services.isa_service import get_isa_status_summary
from app.services.pension_contribution_service import calc_pension_contribution_status
from app.services.tax_service import get_overseas_positions_detail, get_tax_summary
from app.utils.cache_keys import TTL_TAX_OVERSEAS, get_cached_json, set_cached_json, tax_overseas_key

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/overseas-positions")
@limiter.limit("30/minute")
async def overseas_positions_tax(
    request: Request,
    account_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """해외 종목별 미실현 손익 목록. account_id 미지정 시 전체 계좌 통합 기준."""
    redis = await get_redis()
    cache_key = tax_overseas_key(current_user.id, account_id or "all")
    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached
    result = await get_overseas_positions_detail(current_user.id, db, uuid.UUID(account_id) if account_id else None)
    await set_cached_json(redis, cache_key, result, TTL_TAX_OVERSEAS)
    return result


@router.get("/summary")
@limiter.limit("30/minute")
async def tax_summary(
    request: Request,
    year: int | None = None,
    account_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """연도별 세금 추정 요약. account_id 미지정 시 전체 계좌 통합 기준."""
    current_year = date.today().year
    target_year = year if year is not None else current_year
    if target_year < 2000 or target_year > current_year + 1:
        raise HTTPException(status_code=400, detail="유효하지 않은 연도입니다.")
    return await get_tax_summary(current_user.id, target_year, db, uuid.UUID(account_id) if account_id else None)


@router.get("/isa-status")
@limiter.limit("30/minute")
async def isa_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_isa_status_summary(current_user.id, db)


@router.get("/pension-contribution")
@limiter.limit("30/minute")
async def pension_contribution(
    request: Request,
    year: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_year = date.today().year
    target_year = year if year is not None else current_year
    if target_year < 2000 or target_year > current_year + 1:
        raise HTTPException(status_code=400, detail="유효하지 않은 연도입니다.")
    return await calc_pension_contribution_status(current_user.id, target_year, db)
