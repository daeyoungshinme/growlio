"""포지션(종목) CRUD 및 현재가 동기화 라우터 — /assets/{account_id}/positions"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1._account_deps import get_owned_account
from app.database import get_db
from app.kis.constants import OVERSEAS_MARKETS
from app.limiter import limiter
from app.models.asset import Position
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.asset import ManualPosition, PositionListResponse
from app.services.price_service import fetch_prices_batch
from app.services.snapshot_service import _upsert_snapshot, sync_snapshot_positions
from app.utils.currency import fetch_usd_krw
from app.utils.pnl import calc_position_pnl
from app.utils.redis_lock import redis_lock

router = APIRouter(tags=["positions"])


def _enrich_positions(positions: list[dict[str, Any]]) -> dict[str, Any]:
    """합계·수익률을 계산해 응답 형태로 변환."""
    items = []
    total_invested = 0.0
    total_value = 0.0

    for p in positions:
        qty = float(p.get("qty", 0))
        avg = float(p.get("avg_price", 0.0))
        cur = float(p.get("current_price") or avg)
        invested, value, pnl, rate = calc_position_pnl(qty, avg, cur)
        total_invested += invested
        total_value += value
        items.append(
            {
                **p,
                "current_price": cur,
                "invested_amount": invested,
                "value_amount": value,
                "pnl": pnl,
                "pnl_pct": round(rate, 2),
            }
        )

    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
    return {
        "positions": items,
        "summary": {
            "total_invested": total_invested,
            "total_value": total_value,
            "total_pnl": total_pnl,
            "total_pnl_pct": round(total_pnl_pct, 2),
        },
    }


@router.get("/{account_id}/positions", response_model=PositionListResponse)
async def get_positions(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """수동 종목 목록 조회 (매입합계·평가합계·수익률 포함)."""
    account = await get_owned_account(account_id, current_user.id, db)
    result = await db.execute(
        select(Position).where(
            Position.account_id == account.id,
            Position.snapshot_id == None,  # noqa: E711
        )
    )
    positions = [p.to_dict() for p in result.scalars().all()]
    return _enrich_positions(positions)


@router.put("/{account_id}/positions", response_model=PositionListResponse)
async def save_positions(
    account_id: UUID,
    positions: list[ManualPosition],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """수동 종목 저장 — 매입금액 합계를 manual_amount로 업데이트."""
    account = await get_owned_account(account_id, current_user.id, db)
    redis = await get_redis()

    lock_key = f"sync_lock:{account_id}"
    async with redis_lock(redis, lock_key, ttl=30) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="포지션 저장이 이미 진행 중입니다. 잠시 후 다시 시도하세요.",
            )

        total_invested_dec = sum(Decimal(str(p.qty)) * Decimal(str(p.avg_price)) for p in positions)
        total_value_dec = sum(Decimal(str(p.current_price or p.avg_price)) * Decimal(str(p.qty)) for p in positions)
        account.manual_amount = float(total_value_dec)
        account.manual_updated_at = datetime.now(UTC)

        def _build(p: ManualPosition, snapshot_id) -> Position:
            eff_price = p.current_price or p.avg_price
            return Position(
                account_id=account.id,
                snapshot_id=snapshot_id,
                ticker=p.ticker,
                name=p.name,
                market=p.market,
                qty=p.qty,
                avg_price=p.avg_price,
                avg_price_usd=p.avg_price_usd,
                current_price=eff_price,
                value_krw=eff_price * p.qty,
                currency="USD" if p.avg_price_usd else "KRW",
                usd_rate=p.usd_rate,
            )

        await db.execute(
            sql_delete(Position).where(
                Position.account_id == account.id,
                Position.snapshot_id == None,  # noqa: E711
            )
        )
        for p in positions:
            db.add(_build(p, None))

        usd_rate = 1.0
        if account.deposit_usd:
            usd_rate = await fetch_usd_krw(redis)

        snap = await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=(
                float(total_value_dec) + float(account.deposit_krw or 0) + float(account.deposit_usd or 0) * usd_rate
            ),
            invested_amount=float(total_invested_dec),
            unrealized_pnl=float(total_value_dec - total_invested_dec),
            source="MANUAL",
        )
        await db.execute(sql_delete(Position).where(Position.snapshot_id == snap.id))
        for p in positions:
            db.add(_build(p, snap.id))

        await db.commit()
        raw = [p.model_dump() for p in positions]
        return _enrich_positions(raw)


@router.post("/{account_id}/positions/sync-prices", response_model=PositionListResponse)
@limiter.limit("5/minute")
async def sync_position_prices(
    request: Request,
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재가를 조회해 positions를 갱신하고 스냅샷을 저장한다."""
    account = await get_owned_account(account_id, current_user.id, db)
    redis = await get_redis()

    lock_key = f"sync_lock:{account_id}"
    async with redis_lock(redis, lock_key, ttl=60) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="현재가 동기화가 이미 진행 중입니다. 잠시 후 다시 시도하세요.",
            )

        pos_result = await db.execute(
            select(Position).where(
                Position.account_id == account.id,
                Position.snapshot_id == None,  # noqa: E711
            )
        )
        pos_objs = pos_result.scalars().all()
        if not pos_objs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="저장된 종목이 없습니다")

        tickers = [(p.ticker, p.market) for p in pos_objs]
        price_map = await fetch_prices_batch(current_user.id, tickers, db, redis)

        has_overseas = any(p.market in OVERSEAS_MARKETS for p in pos_objs)
        usd_rate: float | None = None
        if has_overseas or account.deposit_usd:
            usd_rate = await fetch_usd_krw(redis, force_refresh=True) or None

        updated_dicts = []
        for p in pos_objs:
            raw_price = price_map.get(p.ticker)
            if raw_price and p.market in OVERSEAS_MARKETS and usd_rate:
                price_krw = raw_price * usd_rate
            elif raw_price:
                price_krw = raw_price
            else:
                price_krw = float(p.current_price or p.avg_price or 0)
            p.current_price = price_krw
            p.value_krw = price_krw * float(p.qty or 0)
            updated_dicts.append(p.to_dict())

        account.manual_updated_at = datetime.now(UTC)

        total_value_dec = sum(Decimal(str(p["current_price"])) * Decimal(str(p["qty"])) for p in updated_dicts)
        total_invested_dec = sum(Decimal(str(p["avg_price"])) * Decimal(str(p["qty"])) for p in updated_dicts)
        account.manual_amount = float(total_value_dec)

        snap = await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=(
                float(total_value_dec)
                + float(account.deposit_krw or 0)
                + float(account.deposit_usd or 0) * (usd_rate or 1)
            ),
            invested_amount=float(total_invested_dec),
            unrealized_pnl=float(total_value_dec - total_invested_dec),
            source="MANUAL",
        )
        await sync_snapshot_positions(db, snapshot_id=snap.id, account_id=account.id, positions=list(pos_objs))
        await db.commit()

        return _enrich_positions(updated_dicts)
