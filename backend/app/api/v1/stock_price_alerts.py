"""주가 목표 알림 CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._alert_crud import register_alert_reactivate_delete
from app.limiter import limiter
from app.models.alert import StockPriceAlert
from app.models.user import User
from app.schemas.alert import StockPriceAlertCreate, StockPriceAlertResponse

router = APIRouter()


@router.get("/stock-price", response_model=list[StockPriceAlertResponse])
@limiter.limit("30/minute")
async def list_stock_price_alerts(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 200,
):
    """주가 목표 알림 목록 조회."""
    result = await db.execute(
        select(StockPriceAlert)
        .where(StockPriceAlert.user_id == current_user.id)
        .order_by(StockPriceAlert.created_at.desc())
        .offset(skip)
        .limit(min(limit, 500))
    )
    return [StockPriceAlertResponse.model_validate(a) for a in result.scalars().all()]


@router.post("/stock-price", response_model=StockPriceAlertResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_stock_price_alert(
    request: Request,
    req: StockPriceAlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """주가 목표 알림 생성."""
    alert = StockPriceAlert(
        user_id=current_user.id,
        ticker=req.ticker,
        market=req.market,
        name=req.name,
        target_price=req.target_price,
        direction=req.direction,
        max_trigger_count=req.max_trigger_count,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return StockPriceAlertResponse.model_validate(alert)


register_alert_reactivate_delete(
    router,
    path_prefix="/stock-price",
    model=StockPriceAlert,
    response_model=StockPriceAlertResponse,
)
