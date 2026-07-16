import asyncio

import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.kis.auth import _fetch_and_store_token
from app.models.asset import AssetAccount
from app.services.credential_service import decrypt

logger = structlog.get_logger()

_TOKEN_REFRESH_CONCURRENCY = 3


async def refresh_all_user_tokens() -> None:
    """매일 06:00 KST — 계좌별 KIS 자격증명 보유 계좌 토큰을 갱신."""
    redis = await get_redis()

    async with AsyncSessionLocal() as db:
        account_result = await db.execute(
            select(AssetAccount).where(
                AssetAccount.kis_app_key != None,  # noqa: E711
                AssetAccount.is_active == True,  # noqa: E712
                AssetAccount.data_source == "KIS_API",
            )
        )
        accounts_with_creds = account_result.scalars().all()

    sem = asyncio.Semaphore(_TOKEN_REFRESH_CONCURRENCY)

    async def _refresh_one(account: AssetAccount) -> None:
        async with sem:
            try:
                app_key = decrypt(account.kis_app_key)  # type: ignore[arg-type]
                app_secret = decrypt(account.kis_app_secret)  # type: ignore[arg-type]
                async with AsyncSessionLocal() as db:
                    await _fetch_and_store_token(
                        app_key,
                        app_secret,
                        is_mock=account.is_mock_mode,
                        redis=redis,
                        db=db,
                        user_id=str(account.user_id),
                        account_id=str(account.id),
                    )
                logger.info("kis_account_token_refreshed", account_id=str(account.id))
            except Exception as e:
                logger.error("kis_account_token_refresh_failed", account_id=str(account.id), error=str(e))

    await asyncio.gather(*(_refresh_one(account) for account in accounts_with_creds))
