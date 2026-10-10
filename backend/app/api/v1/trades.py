"""수기 매매 기록 CRUD + 기간별(월/연) 매수 종목·수익률 조회 API."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PaginationDep, get_current_user, get_db, get_owned_or_404
from app.api.v1._account_deps import get_owned_account
from app.limiter import limiter
from app.models.trade import TradeRecord
from app.models.user import User
from app.schemas.trade import (
    TRADE_CLEARABLE_FIELDS,
    PeriodPurchaseSummary,
    TradeCreate,
    TradeResponse,
    TradeUpdate,
)
from app.services.period_purchase_service import get_period_purchases, resolve_period
from app.utils.kst import today_kst

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/period-summary", response_model=PeriodPurchaseSummary)
@limiter.limit("30/minute")
async def period_summary(
    request: Request,
    period: Literal["month", "year"] = "month",
    year: int | None = Query(None, ge=2000, le=2100),
    month: int | None = Query(None, ge=1, le=12),
    account_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = today_kst()
    year = year or today.year
    if period == "month" and month is None:
        month = today.month if year == today.year else 12
    if account_id:
        await get_owned_account(account_id, current_user.id, db)
    start, end = resolve_period(period, year, month)
    if start > today:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="미래 기간은 조회할 수 없습니다")
    return await get_period_purchases(db, current_user.id, start, end, today, account_id)


@router.get("", response_model=list[TradeResponse])
@limiter.limit("60/minute")
async def list_trades(
    request: Request,
    pagination: PaginationDep,
    account_id: UUID | None = None,
    ticker: str | None = None,
    market: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TradeRecord).where(TradeRecord.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(TradeRecord.account_id == account_id)
    if ticker:
        stmt = stmt.where(TradeRecord.ticker == ticker)
    if market:
        stmt = stmt.where(TradeRecord.market == market)
    stmt = (
        stmt.order_by(TradeRecord.trade_date.desc(), TradeRecord.created_at.desc())
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_trade(
    request: Request,
    req: TradeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_account(req.account_id, current_user.id, db)
    trade = TradeRecord(
        user_id=current_user.id,
        account_id=req.account_id,
        side=req.side,
        ticker=req.ticker.strip().upper(),
        market=req.market,
        name=req.name,
        qty=req.qty,
        price_krw=req.price_krw,
        fee=req.fee,
        trade_date=req.trade_date,
        notes=req.notes,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return trade


@router.put("/{trade_id}", response_model=TradeResponse)
@limiter.limit("30/minute")
async def update_trade(
    request: Request,
    trade_id: UUID,
    req: TradeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    trade = await get_owned_or_404(db, TradeRecord, trade_id, current_user.id, "매매 기록을 찾을 수 없습니다")
    for field_name, value in req.model_dump(exclude_unset=True).items():
        if value is not None or field_name in TRADE_CLEARABLE_FIELDS:
            setattr(trade, field_name, value)
    await db.commit()
    await db.refresh(trade)
    return trade


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_trade(
    request: Request,
    trade_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    trade = await get_owned_or_404(db, TradeRecord, trade_id, current_user.id, "매매 기록을 찾을 수 없습니다")
    await db.delete(trade)
    await db.commit()
