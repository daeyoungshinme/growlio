import structlog
from sqlalchemy import select

from app.constants import BROKER_API_DATA_SOURCES
from app.core.database import AsyncSessionLocal
from app.jobs._job_helpers import peak_rss_mb
from app.models.asset import AssetAccount
from app.services.accounts.sync_all_service import sync_accounts

logger = structlog.get_logger()


async def run_daily_asset_sync() -> None:
    """매일 18:00 KST — 모든 활성 계좌의 스냅샷을 저장."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AssetAccount).where(AssetAccount.is_active == True))
        accounts = result.scalars().all()

    logger.info("daily_asset_sync_start", account_count=len(accounts), peak_rss_mb=peak_rss_mb())
    await sync_accounts(list(accounts), "daily_sync")
    logger.info("daily_asset_sync_done", peak_rss_mb=peak_rss_mb())


async def run_intraday_asset_sync() -> None:
    """매일 15:30 KST — 장 마감 직후 증권사 API(KIS/키움/토스) 주식 계좌만 스냅샷 저장."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AssetAccount).where(
                AssetAccount.is_active == True,
                AssetAccount.data_source.in_(BROKER_API_DATA_SOURCES),
            )
        )
        accounts = result.scalars().all()

    logger.info("intraday_asset_sync_start", account_count=len(accounts), peak_rss_mb=peak_rss_mb())
    await sync_accounts(list(accounts), "intraday_sync")
    logger.info("intraday_asset_sync_done", peak_rss_mb=peak_rss_mb())
