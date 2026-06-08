from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.limiter import limiter
from app.models.user import User
from app.services.tax_service import get_overseas_positions_detail, get_tax_summary

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/overseas-positions")
@limiter.limit("30/minute")
async def overseas_positions_tax(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await get_overseas_positions_detail(current_user.id, db)


@router.get("/summary")
@limiter.limit("30/minute")
async def tax_summary(
    request: Request,
    year: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_year = date.today().year
    target_year = year if year is not None else current_year
    if target_year < 2000 or target_year > current_year + 1:
        raise HTTPException(status_code=400, detail="유효하지 않은 연도입니다.")
    return await get_tax_summary(current_user.id, target_year, db)
