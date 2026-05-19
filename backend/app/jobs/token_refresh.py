import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.kis.auth import _fetch_and_store_token
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.credential_service import decrypt

logger = structlog.get_logger()


async def refresh_all_user_tokens() -> None:
    """매일 06:00 KST — 모든 유저의 KIS·오픈뱅킹 토큰을 갱신."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, UserSettings)
            .join(UserSettings, UserSettings.user_id == User.id)
            .where(User.is_active == True)  # noqa: E712
        )
        rows = result.all()

    redis = await get_redis()
    for user, settings_row in rows:
        # KIS 토큰 갱신
        if settings_row.kis_app_key:
            try:
                app_key = decrypt(settings_row.kis_app_key)
                app_secret = decrypt(settings_row.kis_app_secret)
                async with AsyncSessionLocal() as db:
                    await _fetch_and_store_token(
                        app_key,
                        app_secret,
                        is_mock=settings_row.kis_is_mock,
                        redis=redis,
                        db=db,
                        user_id=str(user.id),
                    )
                logger.info("kis_token_refreshed", user_id=str(user.id))
            except Exception as e:
                logger.error("kis_token_refresh_failed", user_id=str(user.id), error=str(e))

        # 오픈뱅킹 토큰 갱신
        if settings_row.ob_refresh_token:
            try:
                from app.providers.openbanking import ensure_ob_token_fresh
                async with AsyncSessionLocal() as db:
                    settings_fresh = await db.get(UserSettings, user.id)
                    if settings_fresh and settings_fresh.ob_refresh_token:
                        await ensure_ob_token_fresh(settings_fresh, db)
            except Exception as e:
                logger.error("ob_token_refresh_failed", user_id=str(user.id), error=str(e))
