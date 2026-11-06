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

from functools import partial

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.job_runner import report_job_failure, run_per_user
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import already_sent_alert_today
from app.services.market_signal.market_signal_service import (
    get_confirmed_composite_level,
    get_market_signal,
)
from app.services.rebalancing.diagnosis_service import MARKET_NOTES
from app.utils.cache_keys import (
    TTL_MARKET_SIGNAL_CHANGE_SENT,
    CacheStoreType,
    market_signal_change_attempts_key,
    market_signal_change_sent_key,
    market_signal_last_notified_level_key,
)
from app.utils.durable_state import delete_durable, get_durable, set_durable

logger = structlog.get_logger()

_DIGEST_CONCURRENCY = 5


async def _get_composite_subscribers(db: AsyncSession) -> list[tuple[User, UserSettings | None]]:
    """composite_signal_alerts_enabled가 True(기본값 포함)인 활성 유저 목록(활성 리밸런싱 알림 보유 여부와 무관)."""
    result = await db.execute(
        select(User, UserSettings)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.is_active == True,
            or_(UserSettings.user_id.is_(None), UserSettings.composite_signal_alerts_enabled == True),
        )
        .distinct()
    )
    return [(user, user_settings) for user, user_settings in result.all()]


_MAX_LEVEL_NOTICE_ATTEMPTS = 3  # 시간당 잡 기준 3시간 — 수신 채널이 없는 사용자 때문에 끝없이 돌지 않게


async def _finish_level_notice(db: AsyncSession, new_level: str, failed_count: int) -> None:
    """전원 처리했으면 통지 등급을 갱신한다. 실패가 남으면 다음 실행에 재시도하되 정해진 횟수까지만."""
    attempts = 0
    raw_attempts = await get_durable(db, market_signal_change_attempts_key())
    if raw_attempts:
        level, _, count = raw_attempts.partition(":")
        attempts = int(count) if level == new_level and count.isdigit() else 0
    attempts += 1
    if failed_count and attempts < _MAX_LEVEL_NOTICE_ATTEMPTS:
        await set_durable(db, market_signal_change_attempts_key(), f"{new_level}:{attempts}")
        return
    if failed_count:
        logger.warning("market_signal_change_gave_up", new_level=new_level, failed=failed_count, attempts=attempts)
    await set_durable(db, market_signal_last_notified_level_key(), new_level)
    await delete_durable(db, market_signal_change_attempts_key())


async def check_market_signal_level_change(db: AsyncSession, cache: CacheStoreType) -> None:
    """confirmed(hysteresis 적용) 등급이 마지막으로 알린 등급과 달라졌으면 구독 유저 전체에게 알린다.

    raw 레벨이 아닌 confirmed 레벨(연속 CONFIRM_STREAK_REQUIRED회 관측 후에만 반영)을 기준으로 비교해, 경계값 근처에서
    등급이 잦게 오갈 때의 알림 flapping을 억제한다. 비교 대상은 확정 등급의 이전 값이 아니라 "마지막으로 알린 등급"이다.
    확정은 5~10분 주기 잡들이 먼저 하므로, 이전 값과 비교하면 이 시간당 잡은 변화를 거의 보지 못해 알림이 유실됐다.
    최초 실행(알린 등급 없음)은 저장만 하고 발송하지 않는다 — 배포 직후 스팸 방지.
    """
    from app.services.alerts._dispatch import dispatch_dual_channel_alert
    from app.services.notifications.email_service import send_market_signal_change_alert
    from app.services.rebalancing.alert_check import _mark_composite_alert_sent_today

    try:
        new_level, _ = await get_confirmed_composite_level(cache, db)
    except Exception as exc:
        logger.warning("market_signal_level_check_fetch_failed", error=str(exc))
        return

    old_level = await get_durable(db, market_signal_last_notified_level_key())
    if old_level is None:
        await set_durable(db, market_signal_last_notified_level_key(), new_level)
        return

    if old_level == new_level:
        return

    reason = MARKET_NOTES.get(new_level)
    subscribers = await _get_composite_subscribers(db)
    await db.commit()  # 발송 내내 커넥션을 잡고 있지 않는다 — 유저마다 새 세션을 연다

    # 유저마다 새 세션 — 공유 세션이면 한 유저의 DB 오류가 뒤 유저 발송을 전부 막는다(docs/plans/39 N3).
    sent_count = 0
    failed_count = 0
    for user, user_settings in subscribers:
        to_email = getattr(user_settings, "notification_email", None) or user.email
        fcm_token = getattr(user_settings, "fcm_token", None)
        sent_key = market_signal_change_sent_key(user.id, old_level, new_level)
        try:
            async with AsyncSessionLocal() as user_db:
                if await get_durable(user_db, sent_key) is not None:
                    continue

                async def _after_sent(session: AsyncSession = user_db, key: str = sent_key, uid=user.id) -> None:
                    # 같은 날 rebalancing/alert_check의 복합신호 알림과 중복 발송되지 않도록 dedup을 공유한다.
                    await _mark_composite_alert_sent_today(session, uid)
                    await set_durable(session, key, "1", ttl=TTL_MARKET_SIGNAL_CHANGE_SENT)

                sent = await dispatch_dual_channel_alert(
                    user_db,
                    user.id,
                    event_prefix="market_signal_change",
                    alert_type="MARKET_SIGNAL",
                    history_message=f"시장 위험 신호: {old_level} → {new_level}",
                    send_email=partial(send_market_signal_change_alert, to_email, old_level, new_level, reason),
                    push_title="시장 위험 신호 변경",
                    push_body=f"시장 위험 신호가 {old_level} → {new_level}로 변경되었습니다.",
                    push_type="MARKET_SIGNAL",
                    fcm_token=fcm_token,
                    after_sent=_after_sent,
                )
        except Exception as exc:
            report_job_failure("market_signal_change_user_failed", exc, user_id=str(user.id))
            failed_count += 1
            continue
        if sent:
            sent_count += 1
        else:
            failed_count += 1

    await _finish_level_notice(db, new_level, failed_count)

    if sent_count:
        logger.info(
            "market_signal_level_change_notified",
            old_level=old_level,
            new_level=new_level,
            count=sent_count,
        )


async def _get_daily_digest_subscribers(db: AsyncSession) -> list[tuple[User, UserSettings]]:
    """market_signal_daily_digest_enabled가 True인 활성 유저 목록. 기본값이 OFF이므로 inner join으로 충분."""
    result = await db.execute(
        select(User, UserSettings)
        .join(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.is_active == True,
            UserSettings.market_signal_daily_digest_enabled == True,
        )
    )
    return [(user, user_settings) for user, user_settings in result.all()]


async def _already_sent_digest_today(db: AsyncSession, user_id) -> bool:
    return await already_sent_alert_today(db, user_id, "MARKET_SIGNAL_DIGEST")


async def _send_digest_to_user(
    user: User, user_settings: UserSettings, to_email: str, *, level: str, reason: str
) -> None:
    from app.services.alerts._dispatch import dispatch_dual_channel_alert
    from app.services.notifications.email_service import send_market_signal_daily_digest_alert

    async with AsyncSessionLocal() as db:
        if await _already_sent_digest_today(db, user.id):
            return

        await dispatch_dual_channel_alert(
            db,
            user.id,
            event_prefix="market_signal_daily_digest",
            alert_type="MARKET_SIGNAL_DIGEST",
            history_message=f"오늘의 시장 신호: {level}",
            send_email=partial(send_market_signal_daily_digest_alert, to_email, level, reason),
            push_title="오늘의 시장 신호",
            push_body=f"오늘의 시장 위험 신호: {level}. {reason}",
            push_type="MARKET_SIGNAL_DIGEST",
            fcm_token=user_settings.fcm_token,
        )


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

    reason = MARKET_NOTES.get(level) or "오늘도 안정적입니다."
    subscribers = await _get_daily_digest_subscribers(db)

    await run_per_user(
        subscribers,
        partial(_send_digest_to_user, level=level, reason=reason),
        concurrency=_DIGEST_CONCURRENCY,
        failure_event="market_signal_daily_digest_user_failed",
        release_session=db,
    )
    logger.info("market_signal_daily_digest_completed", level=level, subscriber_count=len(subscribers))
