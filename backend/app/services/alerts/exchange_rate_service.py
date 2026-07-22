"""환율 알림 체크 서비스."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache_store import CacheStore
from app.models.alert import ExchangeRateAlert
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import finalize_alert_batch, notify_and_record_trigger
from app.services.alerts.calculator import should_trigger_exchange_rate
from app.utils.currency import fetch_usd_krw

logger = structlog.get_logger()


async def check_and_trigger_alerts(db: AsyncSession, cache: CacheStore | None = None) -> None:
    """활성 환율 알림을 조회하고 조건 충족 시 이메일/푸시 발송 후 비활성화.

    cache를 함께 전달해야 fetch_usd_krw(force_refresh=True)로 가져온 실시간 환율이
    캐시(usd_krw_rate)에 반영된다 — 이 캐시는 market_signal_service의 환율 신호를
    비롯해 앱 전역에서 "현재 환율"로 참조하는 유일한 소스이므로, cache=None으로 호출하면
    이 job이 5분마다 실시간 값을 가져오고도 캐시에 저장하지 않아 fallback 값으로 굳어진다.
    """
    from app.services.email_service import send_exchange_rate_alert

    current_rate = await fetch_usd_krw(cache, force_refresh=True)
    if current_rate <= 0:
        logger.warning("alert_check_skipped_no_rate")
        return

    result = await db.execute(
        select(
            ExchangeRateAlert,
            User.email,
            UserSettings.notification_email,
            UserSettings.fcm_token,
        )
        .join(User, User.id == ExchangeRateAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(ExchangeRateAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, user_email, notification_email, fcm_token in rows:
        if not should_trigger_exchange_rate(alert, current_rate):
            continue

        email = notification_email or user_email
        target = float(alert.target_rate)
        sent = await send_exchange_rate_alert(
            to_email=email,
            target_rate=target,
            direction=alert.direction,
            current_rate=current_rate,
        )
        if not sent:
            continue

        direction_label = "이하" if alert.direction == "BELOW" else "이상"
        await notify_and_record_trigger(
            db,
            alert,
            "EXCHANGE_RATE",
            f"환율 알림: USD/KRW {current_rate:.0f}원 (목표 {target:.0f}원 {direction_label})",
            alert.user_id,
            "환율 알림",
            f"USD/KRW {current_rate:.0f}원 (목표 {target:.0f}원 {direction_label})",
            fcm_token,
        )
        triggered_count += 1

    await finalize_alert_batch(db, "exchange_rate", triggered_count, current_rate=current_rate)
