"""입출금 및 배당금 내역 관리 API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_resource
from app.database import get_db
from app.limiter import limiter
from app.models.asset import Transaction
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.asset import TransactionCreate, TransactionResponse, TransactionUpdate
from app.utils.cache_keys import dashboard_summary_key, dividend_summary_key, invalidate_user_caches

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionResponse])
@limiter.limit("60/minute")
async def list_transactions(
    request: Request,
    account_id: UUID | None = None,
    year: int | None = Query(None, ge=1900, le=2100),
    transaction_type: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if year:
        stmt = stmt.where(extract("year", Transaction.transaction_date) == year)
    if transaction_type:
        stmt = stmt.where(Transaction.transaction_type == transaction_type)
    stmt = (
        stmt.order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_transaction(
    request: Request,
    req: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tx = Transaction(
        user_id=current_user.id,
        account_id=req.account_id,
        transaction_type=req.transaction_type,
        amount=req.amount,
        transaction_date=req.transaction_date,
        ticker=req.ticker,
        notes=req.notes,
        fee=req.fee,
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    await _invalidate_tx_caches(current_user.id)
    return tx


@router.get("/{tx_id}", response_model=TransactionResponse)
@limiter.limit("60/minute")
async def get_transaction(
    request: Request,
    tx_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tx = await _get_owned_tx(tx_id, current_user.id, db)
    return tx


@router.put("/{tx_id}", response_model=TransactionResponse)
@limiter.limit("30/minute")
async def update_transaction(
    request: Request,
    tx_id: UUID,
    req: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tx = await _get_owned_tx(tx_id, current_user.id, db)
    if req.transaction_type is not None:
        tx.transaction_type = req.transaction_type
    if req.amount is not None:
        tx.amount = req.amount
    if req.transaction_date is not None:
        tx.transaction_date = req.transaction_date
    if req.ticker is not None:
        tx.ticker = req.ticker
    if req.notes is not None:
        tx.notes = req.notes
    if req.fee is not None:
        tx.fee = req.fee
    await db.commit()
    await db.refresh(tx)
    await _invalidate_tx_caches(current_user.id)
    return tx


@router.delete("/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_transaction(
    request: Request,
    tx_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tx = await _get_owned_tx(tx_id, current_user.id, db)
    await db.delete(tx)
    await db.commit()
    await _invalidate_tx_caches(current_user.id)


async def _invalidate_tx_caches(user_id: UUID) -> None:
    redis = await get_redis()
    await invalidate_user_caches(
        redis,
        dashboard_summary_key(user_id),
        dividend_summary_key(user_id),
    )


async def _get_owned_tx(tx_id: UUID, user_id: UUID, db: AsyncSession) -> Transaction:
    return await get_owned_resource(Transaction, tx_id, user_id, db)
