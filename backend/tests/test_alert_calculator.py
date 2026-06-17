"""alert_calculator.py 단위 테스트 — 순수 함수 검증."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.alert_calculator import (
    already_fired_today,
    should_fire_today,
    should_trigger_exchange_rate,
    should_trigger_stock_price,
)

_KST = timezone(timedelta(hours=9))


def _make_rebalancing_alert(**kwargs):
    return SimpleNamespace(
        id=uuid.uuid4(),
        schedule_type=kwargs.get("schedule_type", "DAILY"),
        schedule_day_of_week=kwargs.get("schedule_day_of_week"),
        schedule_day_of_month=kwargs.get("schedule_day_of_month"),
        last_triggered_at=kwargs.get("last_triggered_at"),
    )


def _make_exchange_rate_alert(**kwargs):
    return SimpleNamespace(
        id=uuid.uuid4(),
        target_rate=kwargs.get("target_rate", 1300.0),
        direction=kwargs.get("direction", "BELOW"),
        max_trigger_count=kwargs.get("max_trigger_count", 1),
        triggered_at=kwargs.get("triggered_at"),
    )


def _make_stock_alert(**kwargs):
    return SimpleNamespace(
        id=uuid.uuid4(),
        target_price=kwargs.get("target_price", 50000.0),
        direction=kwargs.get("direction", "BELOW"),
        max_trigger_count=kwargs.get("max_trigger_count", 1),
        triggered_at=kwargs.get("triggered_at"),
    )


# ── should_trigger_exchange_rate ─────────────────────────────────────────────

class TestShouldTriggerExchangeRate:
    def test_below_triggers_when_rate_at_or_below_target(self):
        alert = _make_exchange_rate_alert(target_rate=1300.0, direction="BELOW")
        assert should_trigger_exchange_rate(alert, 1300.0) is True
        assert should_trigger_exchange_rate(alert, 1250.0) is True

    def test_below_does_not_trigger_when_rate_above_target(self):
        alert = _make_exchange_rate_alert(target_rate=1300.0, direction="BELOW")
        assert should_trigger_exchange_rate(alert, 1350.0) is False

    def test_above_triggers_when_rate_at_or_above_target(self):
        alert = _make_exchange_rate_alert(target_rate=1300.0, direction="ABOVE")
        assert should_trigger_exchange_rate(alert, 1300.0) is True
        assert should_trigger_exchange_rate(alert, 1400.0) is True

    def test_above_does_not_trigger_when_rate_below_target(self):
        alert = _make_exchange_rate_alert(target_rate=1300.0, direction="ABOVE")
        assert should_trigger_exchange_rate(alert, 1250.0) is False

    def test_multi_trigger_within_cooldown_returns_false(self):
        recent = datetime.now(tz=UTC) - timedelta(minutes=30)
        alert = _make_exchange_rate_alert(
            target_rate=1300.0,
            direction="BELOW",
            max_trigger_count=5,
            triggered_at=recent,
        )
        assert should_trigger_exchange_rate(alert, 1250.0) is False

    def test_multi_trigger_after_cooldown_returns_true(self):
        old = datetime.now(tz=UTC) - timedelta(hours=2)
        alert = _make_exchange_rate_alert(
            target_rate=1300.0,
            direction="BELOW",
            max_trigger_count=5,
            triggered_at=old,
        )
        assert should_trigger_exchange_rate(alert, 1250.0) is True

    def test_single_trigger_ignores_cooldown(self):
        recent = datetime.now(tz=UTC) - timedelta(minutes=5)
        alert = _make_exchange_rate_alert(
            target_rate=1300.0,
            direction="BELOW",
            max_trigger_count=1,
            triggered_at=recent,
        )
        assert should_trigger_exchange_rate(alert, 1250.0) is True

    def test_no_triggered_at_skips_cooldown_check(self):
        alert = _make_exchange_rate_alert(
            target_rate=1300.0,
            direction="BELOW",
            max_trigger_count=5,
            triggered_at=None,
        )
        assert should_trigger_exchange_rate(alert, 1250.0) is True


# ── should_trigger_stock_price ───────────────────────────────────────────────

class TestShouldTriggerStockPrice:
    def test_below_triggers_when_price_at_or_below_target(self):
        alert = _make_stock_alert(target_price=50000.0, direction="BELOW")
        assert should_trigger_stock_price(alert, 50000.0) is True
        assert should_trigger_stock_price(alert, 45000.0) is True

    def test_below_does_not_trigger_when_price_above_target(self):
        alert = _make_stock_alert(target_price=50000.0, direction="BELOW")
        assert should_trigger_stock_price(alert, 55000.0) is False

    def test_above_triggers_when_price_at_or_above_target(self):
        alert = _make_stock_alert(target_price=50000.0, direction="ABOVE")
        assert should_trigger_stock_price(alert, 50000.0) is True
        assert should_trigger_stock_price(alert, 60000.0) is True

    def test_above_does_not_trigger_when_price_below_target(self):
        alert = _make_stock_alert(target_price=50000.0, direction="ABOVE")
        assert should_trigger_stock_price(alert, 40000.0) is False

    def test_multi_trigger_within_cooldown_returns_false(self):
        recent = datetime.now(tz=UTC) - timedelta(minutes=30)
        alert = _make_stock_alert(
            target_price=50000.0,
            direction="BELOW",
            max_trigger_count=3,
            triggered_at=recent,
        )
        assert should_trigger_stock_price(alert, 45000.0) is False

    def test_multi_trigger_after_cooldown_returns_true(self):
        old = datetime.now(tz=UTC) - timedelta(hours=2)
        alert = _make_stock_alert(
            target_price=50000.0,
            direction="BELOW",
            max_trigger_count=3,
            triggered_at=old,
        )
        assert should_trigger_stock_price(alert, 45000.0) is True

    def test_single_trigger_ignores_cooldown(self):
        recent = datetime.now(tz=UTC) - timedelta(minutes=5)
        alert = _make_stock_alert(
            target_price=50000.0,
            direction="BELOW",
            max_trigger_count=1,
            triggered_at=recent,
        )
        assert should_trigger_stock_price(alert, 45000.0) is True


# ── should_fire_today (edge case) ────────────────────────────────────────────

def test_should_fire_today_semiannual_after_cooldown():
    today = datetime.now(tz=_KST).date()
    last_triggered = datetime.now(tz=_KST) - timedelta(days=180)
    alert = _make_rebalancing_alert(
        schedule_type="SEMIANNUAL",
        schedule_day_of_month=today.day,
        last_triggered_at=last_triggered,
    )
    assert should_fire_today(alert) is True


def test_should_fire_today_semiannual_within_cooldown():
    today = datetime.now(tz=_KST).date()
    last_triggered = datetime.now(tz=_KST) - timedelta(days=90)
    alert = _make_rebalancing_alert(
        schedule_type="SEMIANNUAL",
        schedule_day_of_month=today.day,
        last_triggered_at=last_triggered,
    )
    assert should_fire_today(alert) is False


def test_should_fire_today_annual_after_cooldown():
    today = datetime.now(tz=_KST).date()
    last_triggered = datetime.now(tz=_KST) - timedelta(days=365)
    alert = _make_rebalancing_alert(
        schedule_type="ANNUAL",
        schedule_day_of_month=today.day,
        last_triggered_at=last_triggered,
    )
    assert should_fire_today(alert) is True


# ── already_fired_today (edge case) ──────────────────────────────────────────

def test_already_fired_today_exact_utc_now():
    """UTC 기준 지금 시각도 오늘로 인식된다."""
    now_utc = datetime.now(tz=UTC)
    alert = SimpleNamespace(last_triggered_at=now_utc)
    assert already_fired_today(alert) is True
