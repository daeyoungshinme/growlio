"""주가 목표 알림 CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._alert_crud import count_user_alerts, register_alert_reactivate_delete
from app.constants import MAX_STOCK_PRICE_ALERTS_PER_USER
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
    # 음수 skip은 Postgres OFFSET 오류로 500이 났다 — 검증으로 422를 돌려준다(plans/118 B4)
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
):
    """주가 목표 알림 목록 조회."""
    result = await db.execute(
        select(StockPriceAlert)
        .where(StockPriceAlert.user_id == current_user.id)
        .order_by(StockPriceAlert.created_at.desc())
        .offset(skip)
        .limit(limit)
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
    if await count_user_alerts(db, StockPriceAlert, current_user.id) >= MAX_STOCK_PRICE_ALERTS_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"주가 알림은 {MAX_STOCK_PRICE_ALERTS_PER_USER}개까지 만들 수 있습니다. 안 쓰는 알림은 지워주세요",
        )
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
