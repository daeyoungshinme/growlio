"""주가 알림 체크 서비스."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import StockPriceAlert
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import finalize_alert_batch, notify_and_record_trigger
from app.services.alerts.calculator import should_trigger_stock_price

logger = structlog.get_logger()


async def check_and_trigger_stock_price_alerts(db: AsyncSession, cache) -> None:
    """활성 주가 알림을 조회하고 조건 충족 시 이메일/푸시 발송 후 비활성화."""
    from app.services.email_service import send_stock_price_alert
    from app.services.price_service import fetch_prices_batch

    result = await db.execute(
        select(
            StockPriceAlert,
            User.email,
            UserSettings.notification_email,
            UserSettings.fcm_token,
        )
        .join(User, User.id == StockPriceAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(StockPriceAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()
    if not rows:
        return

    sample_user_id = rows[0][0].user_id
    unique_tickers = list({(a.ticker, a.market) for a, _, _, _ in rows})
    price_map = await fetch_prices_batch(sample_user_id, unique_tickers, db, cache)

    triggered_count = 0
    for alert, user_email, notification_email, fcm_token in rows:
        price = price_map.get(alert.ticker)
        if not price:
            continue
        if not should_trigger_stock_price(alert, price):
            continue

        email = notification_email or user_email
        target = float(alert.target_price)
        sent = await send_stock_price_alert(
            to_email=email,
            ticker=alert.ticker,
            name=alert.name,
            target_price=target,
            current_price=price,
            direction=alert.direction,
        )
        if not sent:
            continue

        direction_label = "이하" if alert.direction == "BELOW" else "이상"
        await notify_and_record_trigger(
            db,
            alert,
            "STOCK_PRICE",
            f"주가 알림: {alert.name}({alert.ticker}) {price:,.0f}원 (목표 {target:,.0f}원 {direction_label})",
            alert.user_id,
            f"주가 알림: {alert.name}",
            f"{price:,.0f}원 (목표 {target:,.0f}원 {direction_label})",
            fcm_token,
        )
        triggered_count += 1

    await finalize_alert_batch(db, "stock_price", triggered_count)
