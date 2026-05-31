"""목표환율 / 리밸런싱 알림 체크 서비스."""
from __future__ import annotations

import asyncio
import calendar
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import ExchangeRateAlert, RebalancingAlert
from app.models.portfolio import Portfolio
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


_KST = timezone(timedelta(hours=9))

# QUARTERLY/SEMIANNUAL/ANNUAL: 쿨다운(일) 경과 후 지정 날짜에 발송
_SCHEDULE_MIN_DAYS: dict[str, int] = {
    "QUARTERLY": 80,
    "SEMIANNUAL": 170,
    "ANNUAL": 350,
}


def _should_fire_today(alert: RebalancingAlert) -> bool:
    """오늘이 해당 알림의 발송일인지 확인."""
    today = datetime.now(tz=_KST).date()
    schedule = alert.schedule_type or "DAILY"

    if schedule == "DAILY":
        return True

    if schedule == "WEEKLY":
        target_dow = alert.schedule_day_of_week if alert.schedule_day_of_week is not None else 0
        return today.weekday() == target_dow

    if schedule == "MONTHLY":
        target_day = alert.schedule_day_of_month or 1
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.day == min(target_day, last_day)

    if schedule in _SCHEDULE_MIN_DAYS:
        target_day = alert.schedule_day_of_month or 1
        last_day = calendar.monthrange(today.year, today.month)[1]
        if today.day != min(target_day, last_day):
            return False
        if not alert.last_triggered_at:
            return True  # 최초 발송
        min_days = _SCHEDULE_MIN_DAYS[schedule]
        elapsed_days = (today - alert.last_triggered_at.astimezone(_KST).date()).days
        return elapsed_days >= min_days

    return False


def _already_fired_today(alert: RebalancingAlert) -> bool:
    """오늘 이미 발송됐는지 확인 (중복 방지)."""
    if not alert.last_triggered_at:
        return False
    today = datetime.now(tz=_KST).date()
    fired_date = alert.last_triggered_at.astimezone(_KST).date()
    return fired_date == today


async def check_rebalancing_alerts(db: AsyncSession) -> None:
    """활성 리밸런싱 알림을 조회하고 스케줄·조건에 따라 이메일 발송."""
    from app.api.v1.portfolio import _build_portfolio_overview
    from app.services.email_service import send_rebalancing_alert
    from app.services.rebalancing_service import analyze_rebalancing

    result = await db.execute(
        select(RebalancingAlert, Portfolio, User.email, UserSettings.notification_email)
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(RebalancingAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, portfolio, user_email, notification_email in rows:
        # 1. 오늘 발송일인지 확인
        if not _should_fire_today(alert):
            continue

        # 2. 오늘 이미 발송했으면 건너뜀
        if _already_fired_today(alert):
            continue

        # 3. 포트폴리오 분석
        saved_ids = getattr(portfolio, "account_ids", None)
        effective_account_ids: list[uuid.UUID] | None = (
            [uuid.UUID(aid) for aid in saved_ids] if saved_ids else None
        )

        try:
            overview = await _build_portfolio_overview(
                alert.user_id, db, account_ids=effective_account_ids
            )
        except Exception as exc:
            logger.warning("rebalancing_alert_overview_failed", alert_id=str(alert.id), error=str(exc))
            continue

        try:
            analysis = analyze_rebalancing(portfolio, overview)
        except Exception as exc:
            logger.warning("rebalancing_alert_analysis_failed", alert_id=str(alert.id), error=str(exc))
            continue

        threshold = float(alert.threshold_pct)
        drifting = [item for item in analysis.items if abs(item.weight_diff_pct) > threshold]

        # 4. 발송 여부 결정
        only_when_drift = getattr(alert, "only_when_drift", True)
        if only_when_drift:
            if not drifting:
                continue
            items_to_show = drifting
            is_scheduled_report = False
        else:
            items_to_show = analysis.items
            is_scheduled_report = True

        # 5. 이메일 발송
        email = notification_email or user_email
        try:
            await send_rebalancing_alert(
                to_email=email,
                portfolio_name=portfolio.name,
                threshold_pct=threshold,
                items_to_show=items_to_show,
                drifting_count=len(drifting),
                is_scheduled_report=is_scheduled_report,
                schedule_type=getattr(alert, "schedule_type", "DAILY"),
            )
        except Exception as exc:
            logger.warning("rebalancing_alert_email_failed", alert_id=str(alert.id), error=str(exc))
            continue

        alert.last_triggered_at = datetime.now(tz=timezone.utc)
        triggered_count += 1

    if triggered_count:
        await db.commit()
        logger.info("rebalancing_alerts_triggered", count=triggered_count)
