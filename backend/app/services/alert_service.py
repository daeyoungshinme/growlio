"""목표환율 알림 체크 서비스."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import ExchangeRateAlert
from app.models.user import User, UserSettings
from app.services.price_service import _sync_usdkrw

logger = structlog.get_logger()

_MULTI_TRIGGER_COOLDOWN = timedelta(hours=1)


async def get_current_usd_krw() -> float:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _sync_usdkrw)


async def check_and_trigger_alerts(db: AsyncSession) -> None:
    """활성 알림을 조회하고 조건 충족 시 이메일 발송 후 비활성화."""
    from app.services.email_service import send_exchange_rate_alert

    current_rate = await get_current_usd_krw()
    if current_rate <= 0:
        logger.warning("alert_check_skipped_no_rate")
        return

    result = await db.execute(
        select(ExchangeRateAlert, User.email, UserSettings.notification_email)
        .join(User, User.id == ExchangeRateAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(ExchangeRateAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, user_email, notification_email in rows:
        email = notification_email or user_email
        target = float(alert.target_rate)
        should_trigger = (
            (alert.direction == "BELOW" and current_rate <= target)
            or (alert.direction == "ABOVE" and current_rate >= target)
        )
        if not should_trigger:
            continue

        # 다회 발동 알림: 쿨다운 체크 (마지막 발동 후 1시간 이내면 건너뜀)
        if alert.max_trigger_count > 1 and alert.triggered_at:
            elapsed = datetime.now(tz=timezone.utc) - alert.triggered_at
            if elapsed < _MULTI_TRIGGER_COOLDOWN:
                continue

        try:
            await send_exchange_rate_alert(
                to_email=email,
                target_rate=target,
                direction=alert.direction,
                current_rate=current_rate,
            )
        except Exception as exc:
            logger.warning("exchange_rate_alert_email_failed", error=str(exc), alert_id=str(alert.id))
            continue

        alert.trigger_count += 1
        alert.triggered_at = datetime.now(tz=timezone.utc)
        if alert.trigger_count >= alert.max_trigger_count:
            alert.is_active = False
        triggered_count += 1

    if triggered_count:
        await db.commit()
        logger.info("exchange_rate_alerts_triggered", count=triggered_count, current_rate=current_rate)
