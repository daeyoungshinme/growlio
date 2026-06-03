"""계좌 동기화 오케스트레이터.

집계/대시보드 로직 → asset_aggregator.py
스냅샷 upsert → snapshot_service.py
"""

from __future__ import annotations

import contextlib
from datetime import date
from typing import Any

import structlog
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.providers.base import BrokerProvider
from app.providers.kis_provider import KISProvider
from app.providers.kiwoom_provider import KiwoomProvider
from app.providers.manual_provider import ManualProvider
from app.providers.openbanking_provider import OpenBankingProvider
from app.services.snapshot_service import _upsert_snapshot, sync_snapshot_positions
from app.utils.cache_keys import monthly_trend_key

logger = structlog.get_logger()

_PROVIDERS: dict[str, BrokerProvider] = {
    "KIS_API": KISProvider(),
    "KIWOOM_API": KiwoomProvider(),
    "OPEN_BANKING": OpenBankingProvider(),
    "MANUAL": ManualProvider(),
}


async def sync_account(account: AssetAccount, db: AsyncSession, redis: Any) -> AssetSnapshot:
    """모든 데이터 소스를 통합 처리하는 계좌 동기화 진입점.

    SyncError 계층 예외를 그대로 전파한다. API 레이어에서 HTTPException으로 변환.
    """
    from app.exceptions import ProviderCredentialError

    provider = _PROVIDERS.get(account.data_source)
    if provider is None:
        raise ProviderCredentialError(f"지원하지 않는 데이터 소스: {account.data_source}")
    balance = await provider.sync(account, db, redis)

    if balance.deposit_krw:
        account.deposit_krw = balance.deposit_krw
    if balance.deposit_foreign:
        account.deposit_usd = balance.deposit_foreign

    if balance.positions:
        await db.execute(
            sql_delete(Position).where(Position.account_id == account.id, Position.snapshot_id == None)  # noqa: E711, E501
        )
        for p in balance.positions:
            db.add(Position(
                account_id=account.id,
                snapshot_id=None,
                ticker=p.ticker, name=p.name, market=p.market,
                qty=p.qty, avg_price=p.avg_price, avg_price_usd=p.avg_price_usd,
                current_price=p.current_price,
                value_krw=p.value_krw,
                currency=p.currency, usd_rate=p.usd_rate,
            ))

    # 현재 포지션 업데이트·스냅샷 생성·스냅샷 포지션 복사를 단일 트랜잭션으로 처리.
    # 중간 실패 시 전체 롤백되어 부분 동기화 상태를 방지한다.
    await db.flush()

    today = balance.extra.get("snapshot_date", date.today())
    source = balance.extra.get("source", account.data_source)

    snapshot = await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=today,
        amount_krw=balance.total_value_krw,
        invested_amount=balance.invested_krw or None,
        unrealized_pnl=balance.pnl_krw or None,
        usd_krw_rate=balance.usd_krw_rate if balance.usd_krw_rate != 1300.0 else None,
        source=source,
    )

    if balance.positions:
        await sync_snapshot_positions(
            db, snapshot_id=snapshot.id, account_id=account.id, positions=balance.positions
        )
    await db.commit()

    # sync 완료 후 월별 추이 캐시 무효화 — sync 직후에도 최신 데이터 표시
    with contextlib.suppress(Exception):
        await redis.delete(monthly_trend_key(account.user_id))

    logger.info(
        "account_synced",
        account_id=str(account.id),
        source=source,
        total_krw=balance.total_value_krw,
    )
    return snapshot
