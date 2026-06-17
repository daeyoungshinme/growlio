import asyncio

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.asset import AssetAccount
from app.redis_client import get_redis
from app.services.asset_service import sync_account

logger = structlog.get_logger()

_STOCK_SOURCES = ("KIS_API", "KIWOOM_API")


async def _sync_accounts(accounts: list[AssetAccount], job_name: str) -> None:
    redis = await get_redis()
    failed: list[tuple[str, str, str]] = []
    sem = asyncio.Semaphore(3)

    async def sync_one(account: AssetAccount) -> None:
        async with sem:
            try:
                async with AsyncSessionLocal() as db:
                    await sync_account(account, db, redis)
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

    await asyncio.gather(*(sync_one(account) for account in accounts))

    if failed:
        logger.warning(
            f"{job_name}_partial_failure",
            total=len(accounts),
            failed=len(failed),
            failed_accounts=[{"id": fid, "name": fname} for fid, fname, _ in failed],
        )


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
