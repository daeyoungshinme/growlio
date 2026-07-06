"""시장 위험 신호등 등급 변화(GREEN/YELLOW/RED 전환) 감지 및 즉시 알림.

포트폴리오별 드리프트 알림(rebalancing_alert_service.py)과 달리, 시장 신호 자체의
등급 전환만을 감지해 특정 포트폴리오 알림 설정 여부와 무관하게 발송한다. 대상 유저는
UserSettings.composite_signal_alerts_enabled가 True(기본값 포함)이고 활성 RebalancingAlert를
하나라도 가진 유저로 한정한다 — 신규 구독 모델을 만들지 않고 기존
"드리프트 없어도 복합신호로 알림받기" 의사표시(이제는 유저 단위 단일 설정)를 재사용한다.
"""

from __future__ import annotations

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import RebalancingAlert
from app.models.user import User, UserSettings
from app.services.alert_service import save_alert_history
from app.services.market_signal_service import (
    get_last_composite_level,
    get_market_signal,
    set_last_composite_level,
)
from app.services.rebalancing_diagnosis_service import _MARKET_NOTES
from app.utils.cache_keys import RedisType

logger = structlog.get_logger()


async def _get_composite_subscribers(db: AsyncSession) -> list[tuple[User, UserSettings | None]]:
    """composite_signal_alerts_enabled가 True(기본값 포함)이고 활성 RebalancingAlert를 가진 유저 목록(중복 제거)."""
    result = await db.execute(
        select(User, UserSettings)
        .join(RebalancingAlert, RebalancingAlert.user_id == User.id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(
            RebalancingAlert.is_active == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
            or_(UserSettings.user_id.is_(None), UserSettings.composite_signal_alerts_enabled == True),  # noqa: E712
        )
        .distinct()
    )
    return [(user, user_settings) for user, user_settings in result.all()]


async def check_market_signal_level_change(db: AsyncSession, redis: RedisType) -> None:
    """시장 위험 신호등 등급이 이전 관측값과 달라졌으면 구독 유저 전체에게 즉시 알림한다.

    최초 실행(이전 관측값 없음)은 저장만 하고 발송하지 않는다 — 배포 직후 스팸 방지.
    """
    from app.services.email_service import send_market_signal_change_alert
    from app.services.push_service import send_push_to_user
    from app.services.rebalancing_alert_service import _mark_composite_alert_sent_today

    try:
        signal = await get_market_signal(redis)
        new_level: str = signal.get("composite_level", "GREEN")
    except Exception as exc:
        logger.warning("market_signal_level_check_fetch_failed", error=str(exc))
        return

    old_level = await get_last_composite_level(redis)

    if old_level is None:
        await set_last_composite_level(redis, new_level)
        return

    if old_level == new_level:
        return

    reason = _MARKET_NOTES.get(new_level)
    subscribers = await _get_composite_subscribers(db)

    sent_count = 0
    for user, user_settings in subscribers:
        to_email = getattr(user_settings, "notification_email", None) or user.email
        fcm_token = getattr(user_settings, "fcm_token", None)

        email_sent = False
        try:
            email_sent = await send_market_signal_change_alert(to_email, old_level, new_level, reason)
        except Exception as exc:
            logger.error("market_signal_change_email_failed", user_id=str(user.id), error=str(exc))

        push_sent = False
        try:
            push_sent = await send_push_to_user(
                user_id=user.id,
                title="시장 위험 신호 변경",
                body=f"시장 위험 신호가 {old_level} → {new_level}로 변경되었습니다.",
                fcm_token=fcm_token,
                data={"type": "MARKET_SIGNAL"},
            )
        except Exception as exc:
            logger.error("market_signal_change_push_failed", user_id=str(user.id), error=str(exc))

        if email_sent or push_sent:
            await save_alert_history(db, user.id, "MARKET_SIGNAL", f"시장 위험 신호: {old_level} → {new_level}")
            # 같은 날 rebalancing_alert_service의 복합신호 알림과 중복 발송되지 않도록 dedup을 공유한다.
            await _mark_composite_alert_sent_today(redis, user.id)
            sent_count += 1

    if sent_count:
        await db.commit()
        logger.info(
            "market_signal_level_change_notified",
            old_level=old_level,
            new_level=new_level,
            count=sent_count,
        )

    await set_last_composite_level(redis, new_level)
