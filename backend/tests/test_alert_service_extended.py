"""alert_service.py 추가 커버리지 테스트 (_should_fire_today MONTHLY/QUARTERLY 분기, check 함수들)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_KST = timezone(timedelta(hours=9))


def _make_alert(schedule_type="DAILY", schedule_day_of_week=None, schedule_day_of_month=None, last_triggered_at=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        schedule_type=schedule_type,
        schedule_day_of_week=schedule_day_of_week,
        schedule_day_of_month=schedule_day_of_month,
        last_triggered_at=last_triggered_at,
    )


# ── _should_fire_today ────────────────────────────────────────


class TestShouldFireToday:
    def test_daily_always_true(self, override_settings):
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        alert = _make_alert(schedule_type="DAILY")
        assert _should_fire_today(alert) is True

    def test_none_schedule_defaults_to_daily(self, override_settings):
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        alert = _make_alert(schedule_type=None)
        assert _should_fire_today(alert) is True

    def test_unknown_schedule_returns_false(self, override_settings):
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        alert = _make_alert(schedule_type="UNKNOWN_SCHEDULE")
        assert _should_fire_today(alert) is False

    def test_weekly_matches_today_dow(self, override_settings):
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today_dow = datetime.now(tz=_KST).date().weekday()
        alert = _make_alert(schedule_type="WEEKLY", schedule_day_of_week=today_dow)
        assert _should_fire_today(alert) is True

    def test_weekly_mismatches_today_dow(self, override_settings):
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today_dow = datetime.now(tz=_KST).date().weekday()
        mismatch_dow = (today_dow + 3) % 7
        alert = _make_alert(schedule_type="WEEKLY", schedule_day_of_week=mismatch_dow)
        assert _should_fire_today(alert) is False

    def test_monthly_matches_today_day(self, override_settings):
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today = datetime.now(tz=_KST).date()
        alert = _make_alert(schedule_type="MONTHLY", schedule_day_of_month=today.day)
        assert _should_fire_today(alert) is True

    def test_monthly_mismatches_today_day(self, override_settings):
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today = datetime.now(tz=_KST).date()
        mismatch_day = (today.day % 28) + 1  # never today
        if mismatch_day == today.day:
            mismatch_day = mismatch_day % 28 + 1
        alert = _make_alert(schedule_type="MONTHLY", schedule_day_of_month=mismatch_day)
        result = _should_fire_today(alert)
        # Only False if mismatch_day != today.day
        assert result is (mismatch_day == today.day)

    def test_monthly_defaults_to_day_1(self, override_settings):
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today = datetime.now(tz=_KST).date()
        alert = _make_alert(schedule_type="MONTHLY", schedule_day_of_month=None)
        expected = today.day == 1
        assert _should_fire_today(alert) is expected

    def test_quarterly_first_trigger(self, override_settings):
        """최초 발송(last_triggered_at=None)이면 True."""
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today = datetime.now(tz=_KST).date()
        alert = _make_alert(
            schedule_type="QUARTERLY",
            schedule_day_of_month=today.day,
            last_triggered_at=None,
        )
        # Only True if today.day matches schedule_day_of_month
        result = _should_fire_today(alert)
        assert result is True

    def test_quarterly_within_cooldown_returns_false(self, override_settings):
        """80일 쿨다운 이전에는 False."""
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today = datetime.now(tz=_KST).date()
        last_triggered = datetime.now(tz=_KST) - timedelta(days=30)
        alert = _make_alert(
            schedule_type="QUARTERLY",
            schedule_day_of_month=today.day,
            last_triggered_at=last_triggered,
        )
        assert _should_fire_today(alert) is False

    def test_quarterly_after_cooldown_returns_true(self, override_settings):
        """80일 이상 경과 후 True."""
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today = datetime.now(tz=_KST).date()
        last_triggered = datetime.now(tz=_KST) - timedelta(days=90)
        alert = _make_alert(
            schedule_type="QUARTERLY",
            schedule_day_of_month=today.day,
            last_triggered_at=last_triggered,
        )
        assert _should_fire_today(alert) is True

    def test_quarterly_day_mismatch_returns_false(self, override_settings):
        """발송일이 오늘과 다르면 False."""
        from app.services.alerts.calculator import should_fire_today as _should_fire_today

        today = datetime.now(tz=_KST).date()
        mismatch_day = (today.day % 28) + 1
        if mismatch_day == today.day:
            mismatch_day = mismatch_day % 28 + 1
        alert = _make_alert(
            schedule_type="QUARTERLY",
            schedule_day_of_month=mismatch_day,
        )
        result = _should_fire_today(alert)
        assert result is (mismatch_day == today.day)


# ── _already_fired_today ──────────────────────────────────────


class TestAlreadyFiredToday:
    def test_no_last_triggered_returns_false(self, override_settings):
        from app.services.alerts.calculator import already_fired_today as _already_fired_today

        alert = SimpleNamespace(last_triggered_at=None)
        assert _already_fired_today(alert) is False

    def test_fired_today_returns_true(self, override_settings):
        from app.services.alerts.calculator import already_fired_today as _already_fired_today

        alert = SimpleNamespace(last_triggered_at=datetime.now(tz=_KST))
        assert _already_fired_today(alert) is True

    def test_fired_yesterday_returns_false(self, override_settings):
        from app.services.alerts.calculator import already_fired_today as _already_fired_today

        yesterday = datetime.now(tz=_KST) - timedelta(days=1)
        alert = SimpleNamespace(last_triggered_at=yesterday)
        assert _already_fired_today(alert) is False


# ── check_and_trigger_alerts (exchange rate) ─────────────────


class TestCheckAndTriggerAlerts:
    @pytest.mark.asyncio
    async def test_skips_when_rate_is_zero(self, mock_db, override_settings):
        from app.services.alerts.alert_service import check_and_trigger_alerts

        with patch("app.services.alerts.exchange_rate_service.fetch_usd_krw", new=AsyncMock(return_value=0.0)):
            await check_and_trigger_alerts(mock_db)

        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_alerts_nothing_happens(self, mock_db, override_settings):
        from app.services.alerts.alert_service import check_and_trigger_alerts

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        with patch("app.services.alerts.exchange_rate_service.fetch_usd_krw", new=AsyncMock(return_value=1300.0)):
            await check_and_trigger_alerts(mock_db)

        mock_db.commit.assert_not_called()


# ── check_and_trigger_stock_price_alerts (stub) ───────────────


class TestCheckStockPriceAlerts:
    @pytest.mark.asyncio
    async def test_no_alerts_returns_early(self, mock_db, override_settings):
        from app.services.alerts.alert_service import check_and_trigger_stock_price_alerts

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        redis = AsyncMock()
        await check_and_trigger_stock_price_alerts(mock_db, redis)

        mock_db.commit.assert_not_called()
