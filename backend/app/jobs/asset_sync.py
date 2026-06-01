import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.asset import AssetAccount
from app.redis_client import get_redis
from app.services.asset_service import sync_account

logger = structlog.get_logger()


async def run_daily_asset_sync() -> None:
    """매일 18:00 KST — 모든 활성 계좌의 스냅샷을 저장."""
    redis = await get_redis()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AssetAccount).where(AssetAccount.is_active == True)  # noqa: E712
        )
        accounts = result.scalars().all()

    failed: list[tuple[str, str, str]] = []  # (account_id, name, error)

    for account in accounts:
        try:
            async with AsyncSessionLocal() as db:
                await sync_account(account, db, redis)
            logger.info("account_synced", account_id=str(account.id), name=account.name)
        except Exception as e:
            logger.error("account_sync_failed", account_id=str(account.id), name=account.name, error=str(e))
            failed.append((str(account.id), account.name, str(e)))

    if failed:
        logger.warning(
            "daily_sync_partial_failure",
            total=len(accounts),
            failed=len(failed),
            failed_accounts=[{"id": fid, "name": fname} for fid, fname, _ in failed],
        )
