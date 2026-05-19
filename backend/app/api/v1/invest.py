"""적립식 투자(DCA) 복리계산 및 목표달성율 API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.invest import DCAAnalysisResponse
from app.services import dca_service

router = APIRouter(prefix="/invest", tags=["invest"])


@router.get("/dca-analysis", response_model=DCAAnalysisResponse)
async def get_dca_analysis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """적립식 투자 복리계산 및 월/년 목표달성율 분석."""
    result = await dca_service.get_dca_analysis(current_user.id, db)
    return result
