"""알림 발동 조건 계산 — 순수 함수 (DB 접근 없음)."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta, timezone

from app.models.alert import ExchangeRateAlert, RebalancingAlert, StockPriceAlert

_KST = timezone(timedelta(hours=9))

_MULTI_TRIGGER_COOLDOWN = timedelta(hours=1)

# QUARTERLY/SEMIANNUAL/ANNUAL: 쿨다운(일) 경과 후 지정 날짜에 발송
_SCHEDULE_MIN_DAYS: dict[str, int] = {
    "QUARTERLY": 80,
    "SEMIANNUAL": 170,
    "ANNUAL": 350,
}


def should_fire_today(alert: RebalancingAlert) -> bool:
    """오늘이 해당 리밸런싱 알림의 발송일인지 확인."""
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


def already_fired_today(alert: RebalancingAlert) -> bool:
    """오늘 이미 발송됐는지 확인 (중복 방지)."""
    if not alert.last_triggered_at:
        return False
    today = datetime.now(tz=_KST).date()
    fired_date = alert.last_triggered_at.astimezone(_KST).date()
    return fired_date == today


def _should_trigger_price(
    direction: str,
    current: float,
    target: float,
    max_trigger_count: int,
    triggered_at: datetime | None,
) -> bool:
    """방향·현재값·목표값으로 알림 발동 여부를 판단하는 공통 로직."""
    hit = (direction == "BELOW" and current <= target) or (direction == "ABOVE" and current >= target)
    if not hit:
        return False
    return not (
        max_trigger_count > 1 and triggered_at and datetime.now(tz=UTC) - triggered_at < _MULTI_TRIGGER_COOLDOWN
    )


def should_trigger_exchange_rate(alert: ExchangeRateAlert, current_rate: float) -> bool:
    """환율 알림 발동 조건 충족 여부."""
    return _should_trigger_price(
        alert.direction,
        current_rate,
        float(alert.target_rate),
        alert.max_trigger_count,
        alert.triggered_at,
    )


def should_trigger_stock_price(alert: StockPriceAlert, price: float) -> bool:
    """주가 알림 발동 조건 충족 여부."""
    return _should_trigger_price(
        alert.direction,
        price,
        float(alert.target_price),
        alert.max_trigger_count,
        alert.triggered_at,
    )
