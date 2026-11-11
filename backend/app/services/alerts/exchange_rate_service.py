"""환율 알림 체크 서비스."""

from __future__ import annotations

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FX_PLAN_ALERT_SOURCE
from app.core.cache_store import CacheStore
from app.core.job_runner import report_handled_failure
from app.models.alert import ExchangeRateAlert
from app.models.fx_extra_need import FxExtraNeed
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import (
    finalize_alert_batch,
    notify_and_record_trigger,
    run_isolated_alert_loop,
)
from app.services.alerts.calculator import should_trigger_exchange_rate
from app.utils.currency import fetch_usd_krw
from app.utils.kst import today_kst

logger = structlog.get_logger()

FX_PLAN_PUSH_TYPE = "FX_PLAN"
"""환전 계획 구간 알림 푸시 data.type — 프론트 `usePushNotifications.resolvePushDeepLink`가 적립 계획 탭으로 연다."""


async def check_and_trigger_alerts(db: AsyncSession, cache: CacheStore | None = None) -> None:
    """활성 환율 알림을 조회하고 조건 충족 시 이메일/푸시 발송 후 비활성화.

    cache를 함께 전달해야 fetch_usd_krw(force_refresh=True)로 가져온 실시간 환율이
    캐시(usd_krw_rate)에 반영된다 — 이 캐시는 market_signal_service의 환율 신호를
    비롯해 앱 전역에서 "현재 환율"로 참조하는 유일한 소스이므로, cache=None으로 호출하면
    이 job이 5분마다 실시간 값을 가져오고도 캐시에 저장하지 않아 fallback 값으로 굳어진다.
    allow_fallback=False — 실시간·캐시가 모두 없을 때(콜드스타트+Yahoo 장애) 고정 fallback으로
    판정하면 그보다 높은 BELOW 알림이 전부 거짓 발동하므로 이번 회차를 건너뛴다(plans/97 A1).
    """
    from app.services.notifications.email_service import send_exchange_rate_alert

    current_rate = await fetch_usd_krw(cache, force_refresh=True, allow_fallback=False)
    if current_rate <= 0:
        logger.warning("alert_check_skipped_no_rate")
        return

    result = await db.execute(
        select(
            ExchangeRateAlert,
            User.email,
            UserSettings.notification_email,
            UserSettings.fcm_token,
            FxExtraNeed.name,
        )
        .join(User, User.id == ExchangeRateAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .outerjoin(FxExtraNeed, FxExtraNeed.id == ExchangeRateAlert.fx_need_id)
        .where(
            ExchangeRateAlert.is_active == True,
            User.is_active == True,
            # 필요일이 지난 추가 환전 항목(plans/123)의 구간 알림은 보내지 않는다(여행이 끝난 뒤 환전하라는 알림)
            or_(ExchangeRateAlert.fx_need_id.is_(None), FxExtraNeed.due_date >= today_kst()),
        )
    )
    rows = result.all()

    async def _handle(row) -> bool:
        alert, user_email, notification_email, fcm_token, need_name = row
        if not should_trigger_exchange_rate(alert, current_rate):
            return False

        email = notification_email or user_email
        target = float(alert.target_rate)
        # 환전 계획 구간 알림이면 환전할 금액을 함께 알린다(plans/121)
        planned_usd = (
            float(alert.planned_usd) if alert.source == FX_PLAN_ALERT_SOURCE and alert.planned_usd is not None else None
        )
        email_sent = False
        try:
            email_sent = await send_exchange_rate_alert(
                to_email=email,
                target_rate=target,
                direction=alert.direction,
                current_rate=current_rate,
                planned_usd=planned_usd,
                plan_label=need_name,
            )
        except Exception as exc:
            report_handled_failure("exchange_rate_alert_email_failed", exc, user_id=str(alert.user_id))

        direction_label = "이하" if alert.direction == "BELOW" else "이상"
        summary = f"USD/KRW {current_rate:.0f}원 (목표 {target:.0f}원 {direction_label})"
        if planned_usd is not None:
            scope_label = f"{need_name} 구간" if need_name else "계획 구간"
            plan_note = f" — {scope_label} ${planned_usd:,.0f}(약 {planned_usd * current_rate:,.0f}원) 환전"
            push_title = "환전 계획 구간 도달"
            push_data: dict[str, str] | None = {"type": FX_PLAN_PUSH_TYPE}
        else:
            plan_note = ""
            push_title = "환율 알림"
            push_data = None
        return await notify_and_record_trigger(
            db,
            alert,
            "EXCHANGE_RATE",
            f"환율 알림: {summary}{plan_note}",
            alert.user_id,
            push_title,
            f"{summary}{plan_note}",
            fcm_token,
            email_sent=email_sent,
            push_data=push_data,
        )

    triggered_count = await run_isolated_alert_loop(db, rows, _handle, "exchange_rate_alert_item_failed")
    await finalize_alert_batch(db, "exchange_rate", triggered_count, current_rate=current_rate)
