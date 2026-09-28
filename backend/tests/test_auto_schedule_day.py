"""AUTO 모드 스케줄일 판정(alerts.calculator.is_auto_schedule_day / next_auto_schedule_date) — 계획 37 E5.

AUTO 잡은 장이 열린 평일에만 돌기 때문에 지정일이 주말이면 다음 평일로 미뤄야 그달 실행이 누락되지 않는다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.services.alerts.calculator import is_auto_schedule_day, next_auto_schedule_date


def _alert(schedule_type="MONTHLY", day_of_month=None, day_of_week=None, last_triggered_at=None):
    return SimpleNamespace(
        schedule_type=schedule_type,
        schedule_day_of_month=day_of_month,
        schedule_day_of_week=day_of_week,
        last_triggered_at=last_triggered_at,
    )


def test_daily_is_always_due():
    assert is_auto_schedule_day(_alert("DAILY"), date(2026, 9, 26))


def test_monthly_weekday_target_is_due_only_on_that_day():
    alert = _alert(day_of_month=25)
    assert is_auto_schedule_day(alert, date(2026, 11, 25))  # 수요일
    assert not is_auto_schedule_day(alert, date(2026, 11, 24))
    assert not is_auto_schedule_day(alert, date(2026, 11, 26))


def test_monthly_weekend_target_rolls_to_next_monday():
    alert = _alert(day_of_month=25)  # 2026-10-25 = 일요일
    assert not is_auto_schedule_day(alert, date(2026, 10, 23))
    assert not is_auto_schedule_day(alert, date(2026, 10, 25))
    assert is_auto_schedule_day(alert, date(2026, 10, 26))


def test_month_end_weekend_target_rolls_into_next_month():
    alert = _alert(day_of_month=28)  # 2026-02-28 = 토요일 → 3월 2일(월)
    assert is_auto_schedule_day(alert, date(2026, 3, 2))
    assert not is_auto_schedule_day(alert, date(2026, 3, 3))


@pytest.mark.parametrize(
    ("day_of_week", "today", "expected"),
    [
        (2, date(2026, 9, 30), True),  # 수요일 지정 · 수요일
        (2, date(2026, 10, 1), False),
        (5, date(2026, 9, 26), False),  # 토요일 지정 · 토요일(장 안 열림)
        (5, date(2026, 9, 28), True),  # 토요일 지정 → 다음 월요일
        (6, date(2026, 9, 28), True),  # 일요일 지정 → 다음 월요일
    ],
)
def test_weekly(day_of_week, today, expected):
    assert is_auto_schedule_day(_alert("WEEKLY", day_of_week=day_of_week), today) is expected


def test_quarterly_respects_cooldown():
    recent = _alert("QUARTERLY", day_of_month=25, last_triggered_at=datetime(2026, 10, 26, tzinfo=UTC))
    assert not is_auto_schedule_day(recent, date(2026, 11, 25))
    old = _alert("QUARTERLY", day_of_month=25, last_triggered_at=datetime(2026, 8, 25, tzinfo=UTC))
    assert is_auto_schedule_day(old, date(2026, 11, 25))


def test_next_auto_schedule_date_excludes_today_and_rolls_weekend():
    alert = _alert(day_of_month=25)
    assert next_auto_schedule_date(alert, date(2026, 10, 22)) == date(2026, 10, 26)
    assert next_auto_schedule_date(alert, date(2026, 11, 25)) == date(2026, 12, 25)


# ── NOTIFY(should_fire_today)·AUTO 공용 규칙 일관성 (docs/plans/39 N2) ─────────────


def _days(start: date, n: int):
    from datetime import timedelta

    return [start + timedelta(days=i) for i in range(n)]


def _oracle_notify(alert, d: date) -> bool:
    """단일화 이전 should_fire_today의 규칙 — 지정일 그대로(주말 이월 없음)."""
    import calendar

    s = alert.schedule_type
    if s == "WEEKLY":
        return d.weekday() == (alert.schedule_day_of_week or 0)
    due = d.day == min(alert.schedule_day_of_month or 1, calendar.monthrange(d.year, d.month)[1])
    if s == "MONTHLY" or not due or alert.last_triggered_at is None:
        return due
    return (d - alert.last_triggered_at.date()).days >= {"QUARTERLY": 80, "SEMIANNUAL": 170, "ANNUAL": 350}[s]


_CONSISTENCY_ALERTS = [
    _alert("WEEKLY", day_of_week=2),
    _alert("WEEKLY", day_of_week=6),
    _alert("MONTHLY", day_of_month=1),
    _alert("MONTHLY", day_of_month=25),
    _alert("MONTHLY", day_of_month=31),
    _alert("QUARTERLY", day_of_month=15, last_triggered_at=datetime(2026, 1, 15, 1, tzinfo=UTC)),
    _alert("ANNUAL", day_of_month=31, last_triggered_at=None),
]


@pytest.mark.parametrize("alert", _CONSISTENCY_ALERTS)
def test_notify_and_auto_share_rules(alert):
    """NOTIFY는 이전 규칙과 동일하고, 평일 NOTIFY 발송일은 AUTO에서도 실행일이다(차이는 주말 이월뿐)."""
    from unittest.mock import patch

    from app.services.alerts import calculator

    for d in _days(date(2026, 1, 1), 730):
        with patch.object(calculator, "today_kst", return_value=d):
            notify = calculator.should_fire_today(alert)
        assert notify == _oracle_notify(alert, d), d
        if notify and d.weekday() < 5:
            assert is_auto_schedule_day(alert, d), d
        if is_auto_schedule_day(alert, d) and not notify:
            assert d.weekday() == 0, d  # 주말 지정일이 월요일로 밀린 경우만
