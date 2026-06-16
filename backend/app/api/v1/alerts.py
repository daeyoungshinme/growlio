"""알림 API — 환율/리밸런싱/주가 알림 집계 + 이력 조회."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1 import exchange_rate_alerts, rebalancing_alerts, stock_price_alerts
from app.database import get_db
from app.limiter import limiter
from app.models.alert import AlertHistory
from app.models.user import User

router = APIRouter(prefix="/alerts", tags=["alerts"])

router.include_router(exchange_rate_alerts.router)
router.include_router(rebalancing_alerts.router)
router.include_router(stock_price_alerts.router)


class AlertHistoryItem(BaseModel):
    id: uuid.UUID
    alert_type: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/history", response_model=list[AlertHistoryItem])
@limiter.limit("30/minute")
async def list_alert_history(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 발송 이력 조회 (최신순)."""
    result = await db.execute(
        select(AlertHistory)
        .where(AlertHistory.user_id == current_user.id)
        .order_by(AlertHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
