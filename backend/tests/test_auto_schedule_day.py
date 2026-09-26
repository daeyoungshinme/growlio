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
