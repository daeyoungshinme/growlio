from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services.tax_service import get_tax_summary

router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/summary")
async def tax_summary(
    year: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target_year = year if year is not None else date.today().year
    return await get_tax_summary(current_user.id, target_year, db)
