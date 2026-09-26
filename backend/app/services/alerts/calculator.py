"""알림 발동 조건 계산 — 순수 함수 (DB 접근 없음)."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta

from app.models.alert import ExchangeRateAlert, RebalancingAlert, StockPriceAlert
from app.utils.kst import KST as _KST

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


def _roll_to_weekday(d: date) -> date:
    """주말이면 다음 월요일로 미룬다(공휴일은 캘린더가 없어 고려하지 않음)."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _monthly_target(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def is_auto_schedule_day(alert: RebalancingAlert, today: date | None = None) -> bool:
    """AUTO 모드 전용 스케줄일 판정.

    `should_fire_today`(NOTIFY 경로 — 잡이 주말에도 돈다)와 규칙은 같되, AUTO 잡은 장이 열린 평일에만
    돌기 때문에 지정일이 주말이면 다음 평일로 미룬다 — 그대로 두면 "매월 25일"이 토요일인 달은 실행이
    통째로 누락된다. 월말 지정일이 주말이라 다음 달 초로 밀리는 경우, 주말 요일을 지정한 주간 설정도 처리한다.
    """
    today = today or datetime.now(tz=_KST).date()
    schedule = alert.schedule_type or "DAILY"

    if schedule == "DAILY":
        return True

    if schedule == "WEEKLY":
        target_dow = alert.schedule_day_of_week if alert.schedule_day_of_week is not None else 0
        this_week_target = today - timedelta(days=today.weekday()) + timedelta(days=target_dow)
        return any(_roll_to_weekday(t) == today for t in (this_week_target, this_week_target - timedelta(days=7)))

    target_day = alert.schedule_day_of_month or 1
    prev_month_last = today.replace(day=1) - timedelta(days=1)
    targets = (
        _monthly_target(today.year, today.month, target_day),
        _monthly_target(prev_month_last.year, prev_month_last.month, target_day),
    )
    if not any(_roll_to_weekday(t) == today for t in targets):
        return False
    if schedule == "MONTHLY":
        return True
    if schedule in _SCHEDULE_MIN_DAYS:
        if not alert.last_triggered_at:
            return True
        elapsed_days = (today - alert.last_triggered_at.astimezone(_KST).date()).days
        return elapsed_days >= _SCHEDULE_MIN_DAYS[schedule]
    return False


def next_auto_schedule_date(alert: RebalancingAlert, today: date | None = None, horizon_days: int = 400) -> date | None:
    """오늘 이후(오늘 제외) 첫 AUTO 스케줄일. `horizon_days` 안에 없으면 None."""
    today = today or datetime.now(tz=_KST).date()
    for offset in range(1, horizon_days + 1):
        d = today + timedelta(days=offset)
        if is_auto_schedule_day(alert, d):
            return d
    return None


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
