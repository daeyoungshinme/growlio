"""경제지표 동기화 잡 — 매일 08:00 KST FRED 최신값 갱신 + FMP 캘린더 캐싱 및 구독자 알림."""
from __future__ import annotations

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.alert import AlertHistory
from app.models.indicator_subscription import IndicatorSubscription
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.economic_indicator_service import INDICATORS, sync_all_to_cache
from app.services.email_service import send_indicator_alert_email

logger = structlog.get_logger()


async def run_economic_indicator_sync() -> None:
    """매일 08:00 KST — FRED에서 최신값을 갱신하고 FMP 캘린더를 Redis에 캐싱한다."""
    logger.info("economic_indicator_sync_started")
    redis = await get_redis()
    try:
        results = await sync_all_to_cache(redis)
        logger.info("economic_indicator_sync_completed", count=len(results))
    except Exception as e:
        logger.error("economic_indicator_sync_failed", error=str(e))

    try:
        from app.services.economic_calendar_service import sync_calendar_to_cache
        await sync_calendar_to_cache(redis)
    except Exception as e:
        logger.error("fmp_calendar_sync_failed", error=str(e))


async def run_economic_indicator_alert_check() -> None:
    """매일 08:05 KST — 새 발표값이 있는 지표의 구독자에게 알림을 발송한다."""
    logger.info("economic_indicator_alert_check_started")
    redis = await get_redis()

    # 최신값 조회 (캐시에서)
    from app.services.economic_indicator_service import fetch_indicator_latest

    results = {}
    for code in INDICATORS:
        try:
            data = await fetch_indicator_latest(code, redis)
            if data:
                results[code] = data
        except Exception as e:
            logger.warning("indicator_fetch_failed", code=code, error=str(e))

    if not results:
        logger.info("economic_indicator_alert_check_no_data")
        return

    # 구독자별 알림 발송
    async with AsyncSessionLocal() as db:
        subs_result = await db.execute(
            select(IndicatorSubscription, User, UserSettings)
            .join(User, User.id == IndicatorSubscription.user_id)
            .join(UserSettings, UserSettings.user_id == User.id)
            .where(User.is_active == True)  # noqa: E712
        )
        subscriptions = subs_result.all()

    # 유저별 구독 지표 그룹화
    user_subs: dict = {}
    for sub, user, settings_row in subscriptions:
        if sub.indicator_code not in results:
            continue
        uid = str(user.id)
        if uid not in user_subs:
            user_subs[uid] = {"user": user, "settings": settings_row, "indicators": []}
        user_subs[uid]["indicators"].append(results[sub.indicator_code])

    for uid, info in user_subs.items():
        user = info["user"]
        settings_row = info["settings"]
        indicators_data = info["indicators"]
        to_email = getattr(settings_row, "notification_email", None) or user.email

        try:
            await send_indicator_alert_email(
                to_email=to_email,
                indicators=indicators_data,
            )

            async with AsyncSessionLocal() as db:
                names = ", ".join(d["name"] for d in indicators_data[:3])
                if len(indicators_data) > 3:
                    names += f" 외 {len(indicators_data) - 3}개"
                db.add(AlertHistory(
                    user_id=user.id,
                    alert_type="INDICATOR_RESULT",
                    message=f"경제지표 발표 알림: {names}",
                ))
                await db.commit()

            logger.info(
                "indicator_alert_sent",
                user_id=uid,
                to=to_email,
                count=len(indicators_data),
            )
        except Exception as e:
            logger.error("indicator_alert_failed", user_id=uid, error=str(e))
