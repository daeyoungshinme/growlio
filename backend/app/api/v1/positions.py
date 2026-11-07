"""포지션(종목) CRUD 및 현재가 동기화 라우터 — /assets/{account_id}/positions"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._account_deps import get_owned_account
from app.core.cache_store import get_cache_store
from app.enums import DataSource
from app.kis.constants import OVERSEAS_MARKETS
from app.limiter import limiter
from app.models.asset import Position
from app.models.user import User
from app.schemas.asset import ManualPosition, PositionListResponse
from app.services.accounts.snapshot_service import sync_snapshot_positions, upsert_snapshot
from app.services.market_data.price_service import fetch_prices_batch
from app.services.portfolio._position_queries import fetch_manual_positions
from app.utils.cache_invalidation import invalidate_asset_account_caches
from app.utils.cache_keys import sync_lock_key
from app.utils.currency import fetch_usd_krw, require_live_usd_krw
from app.utils.inproc_lock import inproc_lock
from app.utils.kst import today_kst
from app.utils.pnl import calc_position_pnl, reprice_positions_krw

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
@limiter.limit("60/minute")
async def get_positions(
    request: Request,
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """수동 종목 목록 조회 (매입합계·평가합계·수익률 포함)."""
    account = await get_owned_account(account_id, current_user.id, db)
    pos_objs = await fetch_manual_positions(account.id, db)
    return _enrich_positions([p.to_dict() for p in pos_objs])


@router.put("/{account_id}/positions", response_model=PositionListResponse)
@limiter.limit("20/minute")
async def save_positions(
    request: Request,
    account_id: UUID,
    positions: list[ManualPosition],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """수동 종목 저장 — 평가액 + 예수금을 manual_amount와 오늘 스냅샷에 반영한다."""
    account = await get_owned_account(account_id, current_user.id, db)
    if account.data_source != DataSource.MANUAL:
        # 증권사 연동 계좌의 오늘 스냅샷을 MANUAL로 덮으면 다음 동기화 전까지 보유종목이 틀어진다(화면도 읽기 전용)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="연동 계좌의 종목은 직접 수정할 수 없습니다"
        )
    cache = await get_cache_store()

    lock_key = sync_lock_key(account_id)
    async with inproc_lock(cache, lock_key, ttl=30) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="포지션 저장이 이미 진행 중입니다. 잠시 후 다시 시도하세요.",
            )

        total_invested_dec = sum(Decimal(str(p.qty)) * Decimal(str(p.avg_price)) for p in positions)
        total_value_dec = sum(Decimal(str(p.current_price or p.avg_price)) * Decimal(str(p.qty)) for p in positions)
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
                currency="USD" if (p.avg_price_usd or p.market in OVERSEAS_MARKETS) else "KRW",
                usd_rate=p.usd_rate,
            )

        await db.execute(
            sql_delete(Position).where(
                Position.account_id == account.id,
                Position.snapshot_id.is_(None),
            )
        )
        for p in positions:
            db.add(_build(p, None))

        usd_rate = 1.0
        if account.deposit_usd:
            usd_rate = await require_live_usd_krw(cache)
        amount_krw = (
            float(total_value_dec) + float(account.deposit_krw or 0) + float(account.deposit_usd or 0) * usd_rate
        )
        # ManualProvider.sync와 같은 정의(평가액 + 예수금) — 예전엔 평가액만 넣어 저장 직후와 동기화 직후의
        # manual_amount가 예수금만큼 달랐다(plans/118 B5)
        account.manual_amount = amount_krw

        snap = await upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=today_kst(),
            amount_krw=amount_krw,
            invested_amount=float(total_invested_dec),
            unrealized_pnl=float(total_value_dec - total_invested_dec),
            source="MANUAL",
        )
        await db.execute(sql_delete(Position).where(Position.snapshot_id == snap.id))
        for p in positions:
            db.add(_build(p, snap.id))

        await db.commit()
        await invalidate_asset_account_caches(cache, account.user_id)
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
    cache = await get_cache_store()

    lock_key = sync_lock_key(account_id)
    async with inproc_lock(cache, lock_key, ttl=60) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="현재가 동기화가 이미 진행 중입니다. 잠시 후 다시 시도하세요.",
            )

        pos_objs = await fetch_manual_positions(account.id, db)
        if not pos_objs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="저장된 종목이 없습니다")

        tickers = [(p.ticker, p.market) for p in pos_objs]
        price_map = await fetch_prices_batch(current_user.id, tickers, db, cache)

        has_overseas = any(p.market in OVERSEAS_MARKETS for p in pos_objs)
        usd_rate: float | None = None
        if account.deposit_usd:
            # 달러 예수금은 스냅샷 합계에 들어가므로 환율 없이는 저장하지 않는다(`or 1`로 $1=1원이 되는 경로 차단)
            usd_rate = await require_live_usd_krw(cache, force_refresh=True)
        elif has_overseas:
            # 환율이 없으면 해외 종목은 기존 현재가를 유지한다(reprice_positions_krw)
            usd_rate = await fetch_usd_krw(cache, force_refresh=True, allow_fallback=False) or None

        reprice_positions_krw(pos_objs, price_map, usd_rate)
        updated_dicts = [p.to_dict() for p in pos_objs]

        account.manual_updated_at = datetime.now(UTC)

        total_value_dec = sum(Decimal(str(p["current_price"])) * Decimal(str(p["qty"])) for p in updated_dicts)
        total_invested_dec = sum(Decimal(str(p["avg_price"])) * Decimal(str(p["qty"])) for p in updated_dicts)
        account.manual_amount = float(total_value_dec)

        snap = await upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=today_kst(),
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
        await invalidate_asset_account_caches(cache, account.user_id)

        return _enrich_positions(updated_dicts)
