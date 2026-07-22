"""시장 위험 신호등 등급 변화(GREEN/YELLOW/RED 전환) 감지 및 즉시 알림 + 매일 요약 다이제스트.

포트폴리오별 드리프트 알림(rebalancing/alert_check.py)과 달리, 시장 신호 자체의
등급 전환만을 감지해 특정 포트폴리오 알림 설정 여부와 무관하게 발송한다. 대상 유저는
UserSettings.composite_signal_alerts_enabled가 True(기본값 포함)인 활성 유저 전체 —
수동 리밸런싱만 쓰거나 알림을 하나도 설정하지 않은 유저도 이 토글만으로 구독된다.

이와 별개로 `send_market_signal_daily_digest`는 등급 전환 여부와 무관하게 매일 08:30 KST에
현재 시장 신호를 요약 발송하는 옵트인(기본 OFF) 기능 — 구독 조건도 별도
(UserSettings.market_signal_daily_digest_enabled).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.alert import AlertHistory
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import save_alert_history
from app.services.market_signal_service import (
    get_last_composite_level,
    get_market_signal,
    set_last_composite_level,
)
from app.services.rebalancing.diagnosis_service import _MARKET_NOTES
from app.utils.cache_keys import CacheStoreType

logger = structlog.get_logger()

_DIGEST_CONCURRENCY = 5


async def _get_composite_subscribers(db: AsyncSession) -> list[tuple[User, UserSettings | None]]:
    """composite_signal_alerts_enabled가 True(기본값 포함)인 활성 유저 목록(활성 리밸런싱 알림 보유 여부와 무관)."""
    result = await db.execute(
        select(User, UserSettings)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.is_active == True,  # noqa: E712
            or_(UserSettings.user_id.is_(None), UserSettings.composite_signal_alerts_enabled == True),  # noqa: E712
        )
        .distinct()
    )
    return [(user, user_settings) for user, user_settings in result.all()]


async def check_market_signal_level_change(db: AsyncSession, cache: CacheStoreType) -> None:
    """시장 위험 신호등 등급이 이전 관측값과 달라졌으면 구독 유저 전체에게 즉시 알림한다.

    최초 실행(이전 관측값 없음)은 저장만 하고 발송하지 않는다 — 배포 직후 스팸 방지.
    """
    from app.services.email_service import send_market_signal_change_alert
    from app.services.push_service import send_push_to_user
    from app.services.rebalancing.alert_check import _mark_composite_alert_sent_today

    try:
        signal = await get_market_signal(cache)
        new_level: str = signal.get("composite_level", "GREEN")
    except Exception as exc:
        logger.warning("market_signal_level_check_fetch_failed", error=str(exc))
        return

    old_level = await get_last_composite_level(db)

    if old_level is None:
        await set_last_composite_level(db, new_level)
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
            # 같은 날 rebalancing/alert_check의 복합신호 알림과 중복 발송되지 않도록 dedup을 공유한다.
            await _mark_composite_alert_sent_today(db, user.id)
            sent_count += 1

    if sent_count:
        await db.commit()
        logger.info(
            "market_signal_level_change_notified",
            old_level=old_level,
            new_level=new_level,
            count=sent_count,
        )

    await set_last_composite_level(db, new_level)


async def _get_daily_digest_subscribers(db: AsyncSession) -> list[tuple[User, UserSettings]]:
    """market_signal_daily_digest_enabled가 True인 활성 유저 목록. 기본값이 OFF이므로 inner join으로 충분."""
    result = await db.execute(
        select(User, UserSettings)
        .join(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.is_active == True,  # noqa: E712
            UserSettings.market_signal_daily_digest_enabled == True,  # noqa: E712
        )
    )
    return [(user, user_settings) for user, user_settings in result.all()]


async def _already_sent_digest_today(db: AsyncSession, user_id) -> bool:  # noqa: ANN001
    """오늘 이미 다이제스트를 발송했으면 True — 스케줄러 재시작/misfire로 인한 중복 발송 방지."""
    today = date.today()
    day_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    result = await db.execute(
        select(AlertHistory.id)
        .where(
            AlertHistory.user_id == user_id,
            AlertHistory.alert_type == "MARKET_SIGNAL_DIGEST",
            AlertHistory.created_at >= day_start,
        )
        .limit(1)
    )
    return result.scalar() is not None


async def _send_digest_to_user(
    user: User, user_settings: UserSettings, level: str, reason: str, sem: asyncio.Semaphore
) -> None:
    from app.services.email_service import send_market_signal_daily_digest_alert
    from app.services.push_service import send_push_to_user

    async with sem:
        try:
            async with AsyncSessionLocal() as db:
                if await _already_sent_digest_today(db, user.id):
                    return

                to_email = user_settings.notification_email or user.email

                email_sent = False
                try:
                    email_sent = await send_market_signal_daily_digest_alert(to_email, level, reason)
                except Exception as exc:
                    logger.error("market_signal_daily_digest_email_failed", user_id=str(user.id), error=str(exc))

                push_sent = False
                try:
                    push_sent = await send_push_to_user(
                        user_id=user.id,
                        title="오늘의 시장 신호",
                        body=f"오늘의 시장 위험 신호: {level}. {reason}",
                        fcm_token=user_settings.fcm_token,
                        data={"type": "MARKET_SIGNAL_DIGEST"},
                    )
                except Exception as exc:
                    logger.error("market_signal_daily_digest_push_failed", user_id=str(user.id), error=str(exc))

                if email_sent or push_sent:
                    await save_alert_history(db, user.id, "MARKET_SIGNAL_DIGEST", f"오늘의 시장 신호: {level}")
                    await db.commit()
        except Exception as exc:
            logger.error("market_signal_daily_digest_user_failed", user_id=str(user.id), error=str(exc))


async def send_market_signal_daily_digest(db: AsyncSession, cache: CacheStoreType) -> None:
    """매일 08:30 KST — 옵트인한 유저에게 등급 전환 여부와 무관하게 현재 시장 위험 신호를 요약 발송한다.

    등급전환 알림(check_market_signal_level_change)과는 별도의 옵트인 토글
    (market_signal_daily_digest_enabled, 기본 OFF)로 구독 여부를 판단한다 —
    "그냥 매일 시장 상황만 보고 싶다"는 니즈를 독립적으로 충족하기 위함.
    """
    try:
        signal = await get_market_signal(cache)
        level: str = signal.get("composite_level", "GREEN")
    except Exception as exc:
        logger.warning("market_signal_daily_digest_fetch_failed", error=str(exc))
        return

    reason = _MARKET_NOTES.get(level) or "오늘도 안정적입니다."
    subscribers = await _get_daily_digest_subscribers(db)

    sem = asyncio.Semaphore(_DIGEST_CONCURRENCY)
    await asyncio.gather(
        *(_send_digest_to_user(user, user_settings, level, reason, sem) for user, user_settings in subscribers)
    )
    logger.info("market_signal_daily_digest_completed", level=level, subscriber_count=len(subscribers))
