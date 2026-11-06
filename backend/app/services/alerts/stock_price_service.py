"""주가 알림 체크 서비스."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_runner import report_handled_failure
from app.models.alert import StockPriceAlert
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import (
    finalize_alert_batch,
    notify_and_record_trigger,
    run_isolated_alert_loop,
)
from app.services.alerts.calculator import should_trigger_stock_price

logger = structlog.get_logger()


async def check_and_trigger_stock_price_alerts(db: AsyncSession, cache) -> None:
    """활성 주가 알림을 조회하고 조건 충족 시 이메일/푸시 발송 후 비활성화.

    목표가는 원화로 입력받으므로(설정 화면 "목표가 (원)") 해외 종목도 KRW 환산가로 비교한다 — USD 원시가와
    비교하면 BELOW 알림이 즉시 거짓 발동한다(plans/115 A8). 시세는 여러 유저 알림을 한 번에 조회하므로
    특정 유저의 KIS 자격증명으로 폴백하지 않는다(`kis_accounts={}` — 국내 Naver/pykrx·Yahoo만).
    """
    from app.services.market_data.price_service import fetch_prices_batch_krw
    from app.services.notifications.email_service import send_stock_price_alert

    result = await db.execute(
        select(
            StockPriceAlert,
            User.email,
            UserSettings.notification_email,
            UserSettings.fcm_token,
        )
        .join(User, User.id == StockPriceAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(StockPriceAlert.is_active == True, User.is_active == True)
    )
    rows = result.all()
    if not rows:
        return

    # price_map은 티커 키 — 시장별로 따로 조회해 같은 티커가 다른 시장에 있을 때 값이 섞이지 않게 한다.
    sample_user_id = rows[0][0].user_id
    price_maps: dict[str, dict[str, float]] = {}
    for market in {a.market for a, _, _, _ in rows}:
        tickers = list({(a.ticker, a.market) for a, _, _, _ in rows if a.market == market})
        price_maps[market] = await fetch_prices_batch_krw(sample_user_id, tickers, db, cache, kis_accounts={})

    async def _handle(row) -> bool:
        alert, user_email, notification_email, fcm_token = row
        price = price_maps.get(alert.market, {}).get(alert.ticker)
        if not price:
            return False
        if not should_trigger_stock_price(alert, price):
            return False

        email = notification_email or user_email
        target = float(alert.target_price)
        email_sent = False
        try:
            email_sent = await send_stock_price_alert(
                to_email=email,
                ticker=alert.ticker,
                name=alert.name,
                target_price=target,
                current_price=price,
                direction=alert.direction,
            )
        except Exception as exc:
            report_handled_failure("stock_price_alert_email_failed", exc, user_id=str(alert.user_id))

        direction_label = "이하" if alert.direction == "BELOW" else "이상"
        return await notify_and_record_trigger(
            db,
            alert,
            "STOCK_PRICE",
            f"주가 알림: {alert.name}({alert.ticker}) {price:,.0f}원 (목표 {target:,.0f}원 {direction_label})",
            alert.user_id,
            f"주가 알림: {alert.name}",
            f"{price:,.0f}원 (목표 {target:,.0f}원 {direction_label})",
            fcm_token,
            email_sent=email_sent,
        )

    triggered_count = await run_isolated_alert_loop(db, rows, _handle, "stock_price_alert_item_failed")
    await finalize_alert_batch(db, "stock_price", triggered_count)
