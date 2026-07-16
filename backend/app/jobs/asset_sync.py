import asyncio
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.asset import AssetAccount
from app.services.asset_service import sync_account

logger = structlog.get_logger()

_STOCK_SOURCES = ("KIS_API", "KIWOOM_API")
_ACCOUNT_SYNC_CONCURRENCY = 3

ProgressCallback = Callable[[int, int], Awaitable[None]]


async def _sync_accounts(
    accounts: list[AssetAccount],
    job_name: str,
    on_progress: ProgressCallback | None = None,
) -> list[tuple[str, str, str]]:
    """세마포어(3)로 동시성을 제한하며 계좌들을 동기화한다.

    각 계좌는 자신만의 짧게 스코프된 AsyncSessionLocal을 열어서 사용하므로,
    이 함수를 호출하는 쪽의 요청 DB 커넥션을 오래 붙잡지 않는다.
    """
    redis = await get_redis()
    failed: list[tuple[str, str, str]] = []
    sem = asyncio.Semaphore(_ACCOUNT_SYNC_CONCURRENCY)
    done_count = 0
    progress_lock = asyncio.Lock()

    async def sync_one(account: AssetAccount) -> None:
        nonlocal done_count
        async with sem:
            try:
                async with AsyncSessionLocal() as db:
                    # account는 이 함수 호출 전 다른(이미 닫힌) 세션에서 조회되어 detached 상태이므로,
                    # merge로 새 세션에 편입해야 sync_account() 내부의 account.deposit_krw 등
                    # 속성 변경이 commit 시 실제로 반영된다.
                    merged_account = await db.merge(account)
                    await sync_account(merged_account, db, redis)
                logger.info("account_synced", job=job_name, account_id=str(account.id), name=account.name)
            except Exception as e:
                logger.error(
                    "account_sync_failed",
                    job=job_name,
                    account_id=str(account.id),
                    name=account.name,
                    error=str(e),
                )
                failed.append((str(account.id), account.name, str(e)))
        if on_progress:
            async with progress_lock:
                done_count += 1
                await on_progress(done_count, len(accounts))

    await asyncio.gather(*(sync_one(account) for account in accounts))

    if failed:
        logger.warning(
            f"{job_name}_partial_failure",
            total=len(accounts),
            failed=len(failed),
            failed_accounts=[{"id": fid, "name": fname} for fid, fname, _ in failed],
        )

    return failed


async def run_daily_asset_sync() -> None:
    """매일 18:00 KST — 모든 활성 계좌의 스냅샷을 저장."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AssetAccount).where(AssetAccount.is_active == True)  # noqa: E712
        )
        accounts = result.scalars().all()

    await _sync_accounts(list(accounts), "daily_sync")


async def run_intraday_asset_sync() -> None:
    """매일 15:30 KST — 장 마감 직후 KIS/Kiwoom 주식 계좌만 스냅샷 저장."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AssetAccount).where(
                AssetAccount.is_active == True,  # noqa: E712
                AssetAccount.data_source.in_(_STOCK_SOURCES),
            )
        )
        accounts = result.scalars().all()

    await _sync_accounts(list(accounts), "intraday_sync")
