from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.services.accounts._snapshot_queries import latest_snapshot_subquery
from app.utils.kst import today_kst
from app.utils.pnl import eval_value


async def _upsert_snapshot(
    db: AsyncSession,
    *,
    account_id,
    user_id,
    snapshot_date,
    amount_krw,
    source,
    **kwargs,
) -> AssetSnapshot:
    set_values = {"amount_krw": amount_krw, "source": source, **kwargs}
    stmt = (
        pg_insert(AssetSnapshot)
        .values(
            account_id=account_id,
            user_id=user_id,
            snapshot_date=snapshot_date,
            amount_krw=amount_krw,
            source=source,
            **kwargs,
        )
        .on_conflict_do_update(
            constraint="uq_snapshot_account_date",
            set_=set_values,
        )
        .returning(AssetSnapshot)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_latest_snapshot(db: AsyncSession, account_id: uuid.UUID) -> AssetSnapshot | None:
    """계좌의 최신 스냅샷만 반환한다 (포지션 불필요한 호출부 전용 — `get_latest_snapshot_with_positions`은
    스냅샷이 없을 때 수동 포지션까지 별도 쿼리로 로드하므로, 포지션을 쓰지 않는 호출부에 쓰면 안 함)."""
    return await db.scalar(
        select(AssetSnapshot)
        .where(AssetSnapshot.account_id == account_id)
        .order_by(AssetSnapshot.snapshot_date.desc())
        .limit(1)
    )


async def get_latest_snapshots_by_account(
    db: AsyncSession, account_ids: list[uuid.UUID]
) -> dict[uuid.UUID, AssetSnapshot]:
    """계좌별 최신 스냅샷을 한 번에 조회한다 — 계좌마다 `get_latest_snapshot`을 부르는 N+1 대신.

    (account_id, snapshot_date)가 유일(uq_snapshot_account_date)이라 max(date) 조인은 계좌당 1행이다.
    """
    if not account_ids:
        return {}
    subq = latest_snapshot_subquery(account_ids=account_ids)
    rows = await db.scalars(
        select(AssetSnapshot).join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
    )
    return {snap.account_id: snap for snap in rows if snap.account_id is not None}


async def get_latest_snapshot_with_positions(
    db: AsyncSession, account_id: uuid.UUID
) -> tuple[AssetSnapshot | None, list[Position]]:
    """계좌의 최신 스냅샷과 그 포지션 목록을 반환한다.

    스냅샷이 없으면 아직 스냅샷에 속하지 않은 수동 포지션(snapshot_id IS NULL)을 반환한다.
    """
    latest_snap = await db.scalar(
        select(AssetSnapshot)
        .where(AssetSnapshot.account_id == account_id)
        .order_by(AssetSnapshot.snapshot_date.desc())
        .limit(1)
    )
    if latest_snap:
        pos_result = await db.execute(select(Position).where(Position.snapshot_id == latest_snap.id))
    else:
        pos_result = await db.execute(
            select(Position).where(
                Position.account_id == account_id,
                Position.snapshot_id.is_(None),
            )
        )
    return latest_snap, list(pos_result.scalars().all())


async def sync_snapshot_positions(
    db: AsyncSession,
    *,
    snapshot_id: uuid.UUID,
    account_id: uuid.UUID,
    positions: list[Any],
) -> None:
    """스냅샷 포지션을 초기화하고 positions를 복사한다.

    positions 원소는 .ticker/.name/.market/.qty/.avg_price/.avg_price_usd/
    .current_price/.value_krw/.currency/.usd_rate 속성을 가져야 한다.
    commit은 호출자가 처리한다.
    """
    # Row-level lock to prevent concurrent syncs for the same snapshot.
    await db.execute(select(AssetSnapshot).where(AssetSnapshot.id == snapshot_id).with_for_update())
    await db.execute(sql_delete(Position).where(Position.snapshot_id == snapshot_id))
    for p in positions:
        db.add(
            Position(
                account_id=account_id,
                snapshot_id=snapshot_id,
                ticker=p.ticker,
                name=p.name,
                market=p.market,
                qty=p.qty,
                avg_price=p.avg_price,
                avg_price_usd=p.avg_price_usd,
                current_price=p.current_price,
                value_krw=p.value_krw,
                currency=p.currency,
                usd_rate=p.usd_rate,
            )
        )


async def write_manual_deposit_snapshot(
    db: AsyncSession,
    account: AssetAccount,
    *,
    latest_snap: AssetSnapshot | None,
    positions: list[Position],
    usd_rate: float,
) -> tuple[AssetSnapshot, float]:
    """예수금이 바뀐 수동 계좌의 오늘 스냅샷을 다시 쓰고 (스냅샷, 총액)을 반환한다.

    총액 = 보유종목 평가액 + 원화 예수금 + 달러 예수금×환율. 투자원금·평가손익은 직전 스냅샷 값을 잇는다.
    positions(직전 스냅샷 포지션, 없으면 수동 포지션)를 새 스냅샷에 복사한다 — 빠뜨리면 오늘 스냅샷에
    포지션 행이 비어 스냅샷 기준 종목 집계에서 보유종목이 사라진다.
    `latest_snap`/`positions`는 이번 요청에서 스냅샷을 쓰기 **전에** 조회한 값이어야 한다. commit은 호출자가 한다.
    """
    total = eval_value(positions) + float(account.deposit_krw or 0) + float(account.deposit_usd or 0) * usd_rate
    snap = await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=today_kst(),
        amount_krw=total,
        invested_amount=latest_snap.invested_amount if latest_snap else None,
        unrealized_pnl=latest_snap.unrealized_pnl if latest_snap else None,
        source="MANUAL",
    )
    if positions:
        await sync_snapshot_positions(db, snapshot_id=snap.id, account_id=account.id, positions=positions)
    return snap, total
