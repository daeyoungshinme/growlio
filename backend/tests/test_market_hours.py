"""market_hours 유틸리티 단위 테스트 — 순수 함수, datetime 주입으로 결정론적 검증."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

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


class TestUsMarketCloseDatetime:
    def test_returns_today_close_in_et_winter(self):
        """겨울(EST, UTC-5) — 마감 16:00 ET는 KST로 보면 다음날 06:00."""
        from app.utils.market_hours import us_market_close_datetime

        now = datetime(2024, 1, _MON, 10, 0, tzinfo=_EST)
        close = us_market_close_datetime(now)

        assert close.hour == 16
        assert close.minute == 0
        assert close.tzinfo is not None

        close_kst = close.astimezone(_KST)
        assert close_kst.day == _MON + 1
        assert close_kst.hour == 6

    def test_returns_today_close_in_et_summer_dst(self):
        """여름(EDT, UTC-4) — 마감 16:00 ET는 KST로 보면 다음날 05:00 (DST로 1시간 당겨짐)."""
        from app.utils.market_hours import us_market_close_datetime

        # 2024-07-08: Monday (EDT 적용 기간)
        now = datetime(2024, 7, 8, 10, 0, tzinfo=_EST)
        close = us_market_close_datetime(now)

        assert close.hour == 16
        close_kst = close.astimezone(_KST)
        assert close_kst.day == 9
        assert close_kst.hour == 5

    def test_defaults_to_current_time_when_now_omitted(self):
        from app.utils.market_hours import us_market_close_datetime

        close = us_market_close_datetime()
        assert close.hour == 16
        assert close.minute == 0


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


class TestExchangeHolidays:
    """plans/122 A1 — 평일 휴장일을 장중으로 보면 닫힌 거래소로 발주돼 FAILED가 된다."""

    def test_us_closed_on_thanksgiving(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2026, 11, 26, 11, 0, tzinfo=_EST)) is False
        assert is_us_market_open(datetime(2026, 11, 27, 11, 0, tzinfo=_EST)) is True

    def test_next_us_open_skips_thanksgiving(self):
        from app.utils.market_hours import next_us_market_open

        nxt = next_us_market_open(datetime(2026, 11, 25, 17, 0, tzinfo=_EST))
        assert (nxt.date(), nxt.hour, nxt.minute) == (datetime(2026, 11, 27).date(), 9, 30)

    def test_fx_wait_deadline_counts_trading_days_only(self):
        from app.utils.market_hours import us_market_close_after_weekdays

        # 수(11-25)부터 거래일 5일: 금 27·월 30·화 12-1·수 2·목 3 (추수감사절 26일 제외)
        deadline = us_market_close_after_weekdays(5, datetime(2026, 11, 25, 12, 0, tzinfo=_EST))
        assert deadline.date() == datetime(2026, 12, 3).date()
        assert (deadline.hour, deadline.minute) == (16, 0)

    def test_krx_closed_on_chuseok_and_year_end(self):
        from app.utils.market_hours import is_korean_market_open

        assert is_korean_market_open(datetime(2026, 9, 25, 10, 0, tzinfo=_KST)) is False
        assert is_korean_market_open(datetime(2026, 12, 31, 10, 0, tzinfo=_KST)) is False
        assert is_korean_market_open(datetime(2026, 9, 28, 10, 0, tzinfo=_KST)) is True


class TestIrregularSessions:
    """plans/128 B — 거래시간이 다른 날을 평소대로 보면 닫힌 장에 발주하거나 열린 장을 놓친다."""

    def test_us_early_close_day_after_thanksgiving(self):
        from app.utils.market_hours import is_us_market_open, us_market_close_datetime

        assert is_us_market_open(datetime(2026, 11, 27, 12, 30, tzinfo=_EST)) is True
        assert is_us_market_open(datetime(2026, 11, 27, 13, 30, tzinfo=_EST)) is False
        close = us_market_close_datetime(datetime(2026, 11, 27, 10, 0, tzinfo=_EST))
        assert (close.hour, close.minute) == (13, 0)

    def test_us_early_close_christmas_eve_and_july_3(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2026, 12, 24, 14, 0, tzinfo=_EST)) is False
        assert is_us_market_open(datetime(2025, 7, 3, 14, 0, tzinfo=_EST)) is False
        # 2026-07-03은 독립기념일 대체 휴장 — 전날은 평소대로 16:00까지
        assert is_us_market_open(datetime(2026, 7, 2, 14, 0, tzinfo=_EST)) is True

    def test_us_regular_day_still_closes_at_four(self):
        from app.utils.market_hours import is_us_market_open

        assert is_us_market_open(datetime(2026, 11, 25, 15, 30, tzinfo=_EST)) is True

    def test_fx_wait_deadline_on_early_close_day(self):
        from app.utils.market_hours import us_market_close_after_weekdays

        # 금(11-20)부터 거래일 4일: 월 23·화 24·수 25·금 27(조기 폐장)
        deadline = us_market_close_after_weekdays(4, datetime(2026, 11, 20, 12, 0, tzinfo=_EST))
        assert (deadline.date(), deadline.hour) == (datetime(2026, 11, 27).date(), 13)

    def test_krx_csat_day_shifts_one_hour(self):
        from app.utils.market_hours import is_korean_market_open, korean_market_close_datetime

        assert is_korean_market_open(datetime(2026, 11, 19, 9, 30, tzinfo=_KST)) is False
        assert is_korean_market_open(datetime(2026, 11, 19, 16, 0, tzinfo=_KST)) is True
        assert is_korean_market_open(datetime(2026, 11, 19, 16, 40, tzinfo=_KST)) is False
        close = korean_market_close_datetime(datetime(2026, 11, 19, 11, 0, tzinfo=_KST))
        assert (close.hour, close.minute) == (16, 30)

    def test_krx_first_trading_day_opens_at_ten(self):
        from app.utils.market_hours import is_korean_market_open

        assert is_korean_market_open(datetime(2026, 1, 2, 9, 30, tzinfo=_KST)) is False
        assert is_korean_market_open(datetime(2026, 1, 2, 10, 30, tzinfo=_KST)) is True
        assert is_korean_market_open(datetime(2026, 1, 2, 15, 40, tzinfo=_KST)) is False
        assert is_korean_market_open(datetime(2026, 1, 5, 9, 30, tzinfo=_KST)) is True


class TestLastCompletedUsSession:
    """plans/128 C1 — 일봉 지표는 정규장이 끝난 거래일의 종가만 쓴다."""

    def test_during_session_is_previous_trading_day(self):
        from app.utils.market_hours import last_completed_us_session

        # 화요일 장중 → 월요일, 월요일 개장 전 → 지난 금요일
        assert last_completed_us_session(datetime(2026, 11, 10, 14, 0, tzinfo=_EST)) == datetime(2026, 11, 9).date()
        assert last_completed_us_session(datetime(2026, 11, 9, 8, 0, tzinfo=_EST)) == datetime(2026, 11, 6).date()

    def test_after_close_is_today(self):
        from app.utils.market_hours import last_completed_us_session

        assert last_completed_us_session(datetime(2026, 11, 10, 16, 0, tzinfo=_EST)) == datetime(2026, 11, 10).date()
        # 07:40 KST 수요일 = 화요일 17:40 ET — 국면 잡은 화요일 종가를 본다
        assert last_completed_us_session(datetime(2026, 11, 11, 7, 40, tzinfo=_KST)) == datetime(2026, 11, 10).date()

    def test_holiday_and_early_close(self):
        from app.utils.market_hours import last_completed_us_session

        # 추수감사절(휴장) 낮 → 수요일, 조기 폐장일 13:30 → 그날
        assert last_completed_us_session(datetime(2026, 11, 26, 12, 0, tzinfo=_EST)) == datetime(2026, 11, 25).date()
        assert last_completed_us_session(datetime(2026, 11, 27, 13, 30, tzinfo=_EST)) == datetime(2026, 11, 27).date()
