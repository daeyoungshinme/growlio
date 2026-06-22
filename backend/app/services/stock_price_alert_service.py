"""주가 알림 체크 서비스."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import StockPriceAlert
from app.models.user import User, UserSettings
from app.services.alert_calculator import should_trigger_stock_price
from app.services.alert_repository import save_alert_history
from app.utils.metrics import alert_trigger_count

logger = structlog.get_logger()


async def check_and_trigger_stock_price_alerts(db: AsyncSession, redis) -> None:
    """활성 주가 알림을 조회하고 조건 충족 시 이메일/푸시 발송 후 비활성화."""
    from app.services.email_service import send_stock_price_alert
    from app.services.price_service import fetch_prices_batch
    from app.services.push_service import send_push_to_user

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
    price_map = await fetch_prices_batch(sample_user_id, unique_tickers, db, redis)

    triggered_count = 0
    for alert, user_email, notification_email, fcm_token in rows:
        price = price_map.get(alert.ticker)
        if not price:
            continue
        if not should_trigger_stock_price(alert, price):
            continue

        email = notification_email or user_email
        target = float(alert.target_price)
        try:
            await send_stock_price_alert(
                to_email=email,
                ticker=alert.ticker,
                name=alert.name,
                target_price=target,
                current_price=price,
                direction=alert.direction,
            )
        except Exception as exc:
            logger.error("stock_price_alert_email_failed", error=str(exc), alert_id=str(alert.id))
            continue

        direction_label = "이하" if alert.direction == "BELOW" else "이상"
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"주가 알림: {alert.name}",
            body=f"{price:,.0f}원 (목표 {target:,.0f}원 {direction_label})",
            fcm_token=fcm_token,
        )

        alert.trigger_count += 1
        alert.triggered_at = datetime.now(tz=UTC)
        if alert.trigger_count >= alert.max_trigger_count:
            alert.is_active = False
        await save_alert_history(
            db,
            alert.user_id,
            "STOCK_PRICE",
            (f"주가 알림: {alert.name}({alert.ticker}) {price:,.0f}원 (목표 {target:,.0f}원 {direction_label})"),
        )
        triggered_count += 1

    if triggered_count:
        await db.commit()
        alert_trigger_count.labels(alert_type="stock_price").inc(triggered_count)
        logger.info("stock_price_alerts_triggered", count=triggered_count)
