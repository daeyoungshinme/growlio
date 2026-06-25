"""market_hours 유틸리티 단위 테스트 — 순수 함수, datetime 주입으로 결정론적 검증."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

_KST = ZoneInfo("Asia/Seoul")
_EST = ZoneInfo("America/New_York")

# 2024-01-08: Monday, 2024-01-06: Saturday, 2024-01-07: Sunday
_MON = 8
_SAT = 6
_SUN = 7


class TestIsKoreanMarketOpen:
    def test_open_at_market_start(self):
        from app.utils.market_hours import is_korean_market_open

        assert is_korean_market_open(datetime(2024, 1, _MON, 9, 0, tzinfo=_KST)) is True

    def test_open_at_market_close_boundary(self):
        from app.utils.market_hours import is_korean_market_open

        assert is_korean_market_open(datetime(2024, 1, _MON, 15, 30, tzinfo=_KST)) is True

    def test_closed_one_minute_after_close(self):
        from app.utils.market_hours import is_korean_market_open

        assert is_korean_market_open(datetime(2024, 1, _MON, 15, 31, tzinfo=_KST)) is False

    def test_closed_one_minute_before_open(self):
        from app.utils.market_hours import is_korean_market_open

        assert is_korean_market_open(datetime(2024, 1, _MON, 8, 59, tzinfo=_KST)) is False

    def test_closed_on_saturday(self):
        from app.utils.market_hours import is_korean_market_open

        assert is_korean_market_open(datetime(2024, 1, _SAT, 12, 0, tzinfo=_KST)) is False

    def test_closed_on_sunday(self):
        from app.utils.market_hours import is_korean_market_open

        assert is_korean_market_open(datetime(2024, 1, _SUN, 12, 0, tzinfo=_KST)) is False


class TestIsUsMarketOpen:
    def test_open_at_market_start(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2024, 1, _MON, 9, 30, tzinfo=_EST)) is True

    def test_open_at_market_close_boundary(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2024, 1, _MON, 16, 0, tzinfo=_EST)) is True

    def test_closed_one_minute_after_close(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2024, 1, _MON, 16, 1, tzinfo=_EST)) is False

    def test_closed_one_minute_before_open(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2024, 1, _MON, 9, 29, tzinfo=_EST)) is False

    def test_closed_on_saturday(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2024, 1, _SAT, 12, 0, tzinfo=_EST)) is False

    def test_closed_on_sunday(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2024, 1, _SUN, 12, 0, tzinfo=_EST)) is False


class TestIsAlertExecutionTime:
    def test_none_alert_time_always_true(self):
        from app.utils.market_hours import is_alert_execution_time

        assert is_alert_execution_time(None) is True

    def test_exact_time_match(self):
        from app.utils.market_hours import is_alert_execution_time

        now = datetime(2024, 1, _MON, 10, 0, tzinfo=_KST)
        assert is_alert_execution_time("10:00", now) is True

    def test_within_4_minutes_ahead(self):
        from app.utils.market_hours import is_alert_execution_time

        now = datetime(2024, 1, _MON, 10, 4, tzinfo=_KST)
        assert is_alert_execution_time("10:00", now) is True

    def test_within_4_minutes_behind(self):
        from app.utils.market_hours import is_alert_execution_time

        now = datetime(2024, 1, _MON, 9, 56, tzinfo=_KST)
        assert is_alert_execution_time("10:00", now) is True

    def test_5_minutes_ahead_returns_false(self):
        from app.utils.market_hours import is_alert_execution_time

        now = datetime(2024, 1, _MON, 10, 5, tzinfo=_KST)
        assert is_alert_execution_time("10:00", now) is False

    def test_5_minutes_behind_returns_false(self):
        from app.utils.market_hours import is_alert_execution_time

        now = datetime(2024, 1, _MON, 9, 55, tzinfo=_KST)
        assert is_alert_execution_time("10:00", now) is False

    def test_invalid_format_returns_false(self):
        from app.utils.market_hours import is_alert_execution_time

        now = datetime(2024, 1, _MON, 10, 0, tzinfo=_KST)
        assert is_alert_execution_time("invalid", now) is False

    def test_empty_string_returns_false(self):
        from app.utils.market_hours import is_alert_execution_time

        now = datetime(2024, 1, _MON, 10, 0, tzinfo=_KST)
        assert is_alert_execution_time("", now) is False
