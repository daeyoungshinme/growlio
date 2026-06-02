from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.tax_service import get_overseas_positions_detail, get_tax_summary

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/overseas-positions")
async def overseas_positions_tax(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await get_overseas_positions_detail(current_user.id, db)


@router.get("/summary")
async def tax_summary(
    year: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_year = date.today().year
    target_year = year if year is not None else current_year
    if target_year < 2000 or target_year > current_year + 1:
        raise HTTPException(status_code=400, detail="유효하지 않은 연도입니다.")
    return await get_tax_summary(current_user.id, target_year, db)
