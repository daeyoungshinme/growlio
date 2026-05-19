"""목표환율 알림 체크 서비스."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import ExchangeRateAlert
from app.models.user import User, UserSettings

logger = structlog.get_logger()


def _sync_usdkrw() -> float:
    import yfinance as yf
    try:
        hist = yf.Ticker("USDKRW=X").history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            if rate > 0:
                return rate
    except Exception as e:
        logger.warning("alert_usdkrw_fetch_failed", error=str(e))
    return 0.0


async def get_current_usd_krw() -> float:
    loop = asyncio.get_event_loop()
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

        alert.is_active = False
        alert.triggered_at = datetime.now(tz=timezone.utc)
        triggered_count += 1

        try:
            await send_exchange_rate_alert(
                to_email=email,
                target_rate=target,
                direction=alert.direction,
                current_rate=current_rate,
            )
        except Exception:
            pass  # 이메일 실패해도 알림 상태는 비활성화 유지

    if triggered_count:
        await db.commit()
        logger.info("exchange_rate_alerts_triggered", count=triggered_count, current_rate=current_rate)
