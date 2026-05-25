import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.kis.auth import _fetch_and_store_token
from app.models.asset import AssetAccount
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.credential_service import decrypt

logger = structlog.get_logger()


async def refresh_all_user_tokens() -> None:
    """매일 06:00 KST — 모든 유저의 오픈뱅킹 토큰과 KIS 계좌별 토큰을 갱신."""
    redis = await get_redis()

    # 오픈뱅킹 토큰 갱신
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, UserSettings)
            .join(UserSettings, UserSettings.user_id == User.id)
            .where(User.is_active == True)  # noqa: E712
        )
        rows = result.all()

    for user, settings_row in rows:
        if settings_row.ob_refresh_token:
            try:
                from app.providers.openbanking import ensure_ob_token_fresh
                async with AsyncSessionLocal() as db:
                    settings_fresh = await db.get(UserSettings, user.id)
                    if settings_fresh and settings_fresh.ob_refresh_token:
                        await ensure_ob_token_fresh(settings_fresh, db)
            except Exception as e:
                logger.error("ob_token_refresh_failed", user_id=str(user.id), error=str(e))

    # 계좌별 KIS 자격증명 보유 계좌 토큰 갱신
    async with AsyncSessionLocal() as db:
        account_result = await db.execute(
            select(AssetAccount).where(
                AssetAccount.kis_app_key != None,  # noqa: E711
                AssetAccount.is_active == True,  # noqa: E712
                AssetAccount.data_source == "KIS_API",
            )
        )
        accounts_with_creds = account_result.scalars().all()

    for account in accounts_with_creds:
        try:
            app_key = decrypt(account.kis_app_key)
            app_secret = decrypt(account.kis_app_secret)
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
            logger.error(
                "kis_account_token_refresh_failed", account_id=str(account.id), error=str(e)
            )
