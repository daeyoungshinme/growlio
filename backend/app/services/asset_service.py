"""계좌 동기화 오케스트레이터.

집계/대시보드 로직 → asset_aggregator.py
스냅샷 upsert → snapshot_service.py
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

import structlog
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.exceptions import ProviderNetworkError
from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.providers.base import BalanceResult, BrokerProvider
from app.providers.kis_provider import KISProvider
from app.providers.kiwoom_provider import KiwoomProvider
from app.providers.manual_provider import ManualProvider
from app.services._account_queries import active_accounts_stmt
from app.services.snapshot_service import _upsert_snapshot, sync_snapshot_positions
from app.utils.cache_keys import (
    CacheStoreType,
    invalidate_account_caches,
    invalidate_asset_account_caches,
)
from app.utils.circuit_breaker import CircuitBreaker, kis_circuit, kiwoom_circuit
from app.utils.metrics import broker_sync_duration

logger = structlog.get_logger()

_PROVIDERS: dict[str, BrokerProvider] = {
    "KIS_API": KISProvider(),
    "KIWOOM_API": KiwoomProvider(),
    "MANUAL": ManualProvider(),
}

_CIRCUITS: dict[str, CircuitBreaker] = {
    "KIS_API": kis_circuit,
    "KIWOOM_API": kiwoom_circuit,
}


def get_provider(account: AssetAccount) -> BrokerProvider:
    """data_source에 맞는 BrokerProvider를 반환한다.

    지원하지 않는 데이터 소스면 ProviderCredentialError를 raise한다.
    """
    from app.exceptions import ProviderCredentialError

    provider = _PROVIDERS.get(account.data_source)
    if provider is None:
        raise ProviderCredentialError(f"지원하지 않는 데이터 소스: {account.data_source}")
    return provider


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(ProviderNetworkError),
    reraise=True,
)
async def _retry_provider_sync(
    provider: BrokerProvider, account: AssetAccount, db: AsyncSession, cache: CacheStoreType
) -> BalanceResult:
    """ProviderNetworkError에 한해 지수 백오프(2s→4s→8s, 최대 30s) 재시도."""
    return await provider.sync(account, db, cache)


async def sync_account(account: AssetAccount, db: AsyncSession, cache: CacheStoreType) -> AssetSnapshot:
    """모든 데이터 소스를 통합 처리하는 계좌 동기화 진입점.

    SyncError 계층 예외 및 CircuitOpenError를 그대로 전파한다.
    API 레이어에서 HTTPException으로 변환.
    """
    import time as _time

    _sync_start = _time.monotonic()
    provider = get_provider(account)
    circuit = _CIRCUITS.get(account.data_source)

    if circuit:
        balance = await circuit.call(_retry_provider_sync, provider, account, db, cache)
    else:
        balance = await _retry_provider_sync(provider, account, db, cache)

    if balance.deposit_krw is not None:
        account.deposit_krw = balance.deposit_krw
    if balance.deposit_foreign:
        account.deposit_usd = balance.deposit_foreign

    if balance.positions:
        await db.execute(
            sql_delete(Position).where(Position.account_id == account.id, Position.snapshot_id == None)  # noqa: E711, E501
        )
        for p in balance.positions:
            db.add(
                Position(
                    account_id=account.id,
                    snapshot_id=None,
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
        usd_krw_rate=(balance.usd_krw_rate if balance.usd_krw_rate != settings.usd_krw_fallback_rate else None),
        source=source,
    )

    if balance.positions:
        await sync_snapshot_positions(db, snapshot_id=snapshot.id, account_id=account.id, positions=balance.positions)
    await db.commit()

    # sync 완료 후 관련 캐시 즉시 무효화 — sync 직후에도 최신 데이터 표시
    await invalidate_account_caches(cache, account.user_id)

    broker_sync_duration.labels(data_source=account.data_source, status="success").observe(
        _time.monotonic() - _sync_start
    )
    logger.info(
        "account_synced",
        account_id=str(account.id),
        source=source,
        total_krw=balance.total_value_krw,
    )
    return snapshot


async def sync_account_now(
    account: AssetAccount, user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType
) -> dict[str, str | float]:
    """계좌 동기화 실행 + 관련 캐시 무효화 + API 응답 dict 반환 (assets.py `/sync` 엔드포인트 전용).

    SyncError/CircuitOpenError는 main.py 전역 핸들러가 처리한다.
    """
    snapshot = await sync_account(account, db, cache)

    await invalidate_asset_account_caches(cache, user_id, account.id)
    return {
        "detail": "동기화 완료",
        "snapshot_date": str(snapshot.snapshot_date),
        "amount_krw": float(snapshot.amount_krw),
    }


# ---------------------------------------------------------------------------
# 조회 헬퍼 — API 레이어에서 직접 쿼리하지 않도록 서비스 레이어에서 제공
# ---------------------------------------------------------------------------


async def list_accounts(
    user_id: uuid.UUID,
    db: AsyncSession,
    skip: int = 0,
    limit: int = 200,
) -> Sequence[AssetAccount]:
    result = await db.execute(
        active_accounts_stmt(user_id)
        .order_by(AssetAccount.sort_order, AssetAccount.created_at)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def list_snapshots_in_range(
    user_id: uuid.UUID,
    db: AsyncSession,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = 0,
    limit: int = 365,
) -> Sequence[AssetSnapshot]:
    query = select(AssetSnapshot).where(AssetSnapshot.user_id == user_id)
    if start_date:
        query = query.where(AssetSnapshot.snapshot_date >= start_date)
    if end_date:
        query = query.where(AssetSnapshot.snapshot_date <= end_date)
    query = query.order_by(AssetSnapshot.snapshot_date.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def list_accounts_by_ids(
    account_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Sequence[AssetAccount]:
    result = await db.execute(
        select(AssetAccount).where(
            AssetAccount.id.in_(account_ids),
            AssetAccount.user_id == user_id,
        )
    )
    return result.scalars().all()
