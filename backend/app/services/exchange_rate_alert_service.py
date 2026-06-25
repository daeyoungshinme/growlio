"""환율 알림 체크 서비스."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import ExchangeRateAlert
from app.models.user import User, UserSettings
from app.services.alert_calculator import should_trigger_exchange_rate
from app.services.alert_repository import apply_alert_trigger
from app.utils.currency import fetch_usd_krw
from app.utils.metrics import alert_trigger_count

logger = structlog.get_logger()


async def check_and_trigger_alerts(db: AsyncSession) -> None:
    """활성 환율 알림을 조회하고 조건 충족 시 이메일/푸시 발송 후 비활성화."""
    from app.services.email_service import send_exchange_rate_alert
    from app.services.push_service import send_push_to_user

    current_rate = await fetch_usd_krw(None, force_refresh=True)
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
        try:
            await send_exchange_rate_alert(
                to_email=email,
                target_rate=target,
                direction=alert.direction,
                current_rate=current_rate,
            )
        except Exception as exc:
            logger.error("exchange_rate_alert_email_failed", error=str(exc), alert_id=str(alert.id))
            continue

        direction_label = "이하" if alert.direction == "BELOW" else "이상"
        await send_push_to_user(
            user_id=alert.user_id,
            title="환율 알림",
            body=f"USD/KRW {current_rate:.0f}원 (목표 {target:.0f}원 {direction_label})",
            fcm_token=fcm_token,
        )

        await apply_alert_trigger(
            db,
            alert,
            "EXCHANGE_RATE",
            f"환율 알림: USD/KRW {current_rate:.0f}원 (목표 {target:.0f}원 {direction_label})",
        )
        triggered_count += 1

    if triggered_count:
        await db.commit()
        alert_trigger_count.labels(alert_type="exchange_rate").inc(triggered_count)
        logger.info("exchange_rate_alerts_triggered", count=triggered_count, current_rate=current_rate)
