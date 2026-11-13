"""장 중 여부 판단 유틸리티 — KRX/NYSE 정규 거래시간·휴장일 기준.

휴장일은 `holidays` 패키지의 거래소 달력(XKRX·NYSE)을 쓴다. 거래시간이 다른 날도 반영한다(plans/128 B) —
NYSE 조기 폐장(13:00 ET: 추수감사절 다음 날·12/24·7/3), KRX 지연 개장(연초 개장일 10:00, 수능일 10:00~16:30).
수능일은 규칙으로 구할 수 없어 `_KRX_CSAT_DAYS`에 해마다 넣는다.
"""

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import holidays

from app.utils.kst import KST as _KST

_EST = ZoneInfo("America/New_York")

# KRX 정규 거래시간 (KST)
_KRX_OPEN = time(9, 0)
_KRX_CLOSE = time(15, 30)

# NYSE/NASDAQ 정규 거래시간 (ET)
_NYSE_OPEN = time(9, 30)
_NYSE_CLOSE = time(16, 0)
_NYSE_EARLY_CLOSE = time(13, 0)

# KRX 지연 개장(1시간)
_KRX_LATE_OPEN = time(10, 0)
_KRX_CSAT_CLOSE = time(16, 30)
# 대학수학능력시험일 — 개장·마감이 모두 1시간 늦다. 거래소가 해마다 공지하므로 날짜가 확정되면 추가한다
_KRX_CSAT_DAYS: frozenset[date] = frozenset({date(2026, 11, 19)})


@lru_cache(maxsize=8)
def _krx_holidays(year: int) -> frozenset[date]:
    return frozenset(holidays.financial_holidays("XKRX", years=year))


@lru_cache(maxsize=8)
def _nyse_holidays(year: int) -> frozenset[date]:
    return frozenset(holidays.financial_holidays("NYSE", years=year))


def is_krx_trading_day(d: date) -> bool:
    """KRX 거래일 여부 — 주말·거래소 휴장일(설·추석·선거일·연말 휴장 등)이면 False."""
    return d.weekday() < 5 and d not in _krx_holidays(d.year)


def is_nyse_trading_day(d: date) -> bool:
    """NYSE 거래일 여부 — 주말·거래소 휴장일(추수감사절·Good Friday 등)이면 False. d는 ET 기준 날짜."""
    return d.weekday() < 5 and d not in _nyse_holidays(d.year)


@lru_cache(maxsize=8)
def _first_krx_trading_day(year: int) -> date:
    d = date(year, 1, 1)
    while not is_krx_trading_day(d):
        d += timedelta(days=1)
    return d


def krx_session_hours(d: date) -> tuple[time, time]:
    """그 날 KRX 정규장 (개장, 마감) — 평소 09:00~15:30, 수능일 10:00~16:30, 연초 개장일 10:00~15:30."""
    if d in _KRX_CSAT_DAYS:
        return _KRX_LATE_OPEN, _KRX_CSAT_CLOSE
    if d == _first_krx_trading_day(d.year):
        return _KRX_LATE_OPEN, _KRX_CLOSE
    return _KRX_OPEN, _KRX_CLOSE


def _thanksgiving(year: int) -> date:
    """11월 넷째 목요일."""
    first = date(year, 11, 1)
    return first + timedelta(days=(3 - first.weekday()) % 7 + 21)


def nyse_close_time(d: date) -> time:
    """그 날 NYSE 정규장 마감(ET) — 추수감사절 다음 날·12/24·7/3이 거래일이면 13:00 조기 폐장, 아니면 16:00."""
    early = {_thanksgiving(d.year) + timedelta(days=1), date(d.year, 12, 24), date(d.year, 7, 3)}
    return _NYSE_EARLY_CLOSE if d in early and is_nyse_trading_day(d) else _NYSE_CLOSE


def is_korean_market_open(now: datetime | None = None) -> bool:
    """KRX 정규 장 여부: 거래일의 `krx_session_hours`(평소 09:00~15:30 KST) 안인지."""
    t = (now or datetime.now(_KST)).astimezone(_KST)
    if not is_krx_trading_day(t.date()):
        return False
    open_at, close_at = krx_session_hours(t.date())
    return open_at <= t.time() <= close_at


def korean_market_close_datetime(now: datetime | None = None) -> datetime:
    """오늘(KST) KRX 정규장 마감 시각(평소 15:30, 수능일 16:30 KST)을 timezone-aware datetime으로 반환한다.

    리밸런싱 매도 승인 만료 시각(당일 장마감) 계산에 사용한다.
    """
    t = (now or datetime.now(_KST)).astimezone(_KST)
    close_at = krx_session_hours(t.date())[1]
    return t.replace(hour=close_at.hour, minute=close_at.minute, second=0, microsecond=0)


def is_us_market_open(now: datetime | None = None) -> bool:
    """NYSE/NASDAQ 정규 장 여부: 거래일 09:30~16:00 ET(조기 폐장일은 13:00까지, DST 자동 반영)."""
    t = (now or datetime.now(_EST)).astimezone(_EST)
    if not is_nyse_trading_day(t.date()):
        return False
    return _NYSE_OPEN <= t.time() <= nyse_close_time(t.date())


def us_market_close_datetime(now: datetime | None = None) -> datetime:
    """오늘(ET 기준) NYSE 정규장 마감 시각(16:00 ET, 조기 폐장일 13:00)을 timezone-aware datetime으로 반환한다.

    ET 기준 "오늘"이므로 KST로 보면 자정을 넘어갈 수 있다(DST에 따라 익일 05:00~06:00 KST) —
    리밸런싱 해외 leg 매도 승인 만료 시각(당일 장마감) 계산에 사용한다.
    """
    t = (now or datetime.now(_EST)).astimezone(_EST)
    close_at = nyse_close_time(t.date())
    return t.replace(hour=close_at.hour, minute=close_at.minute, second=0, microsecond=0)


def last_completed_us_session(now: datetime | None = None) -> date:
    """정규장이 끝난 가장 최근 NYSE 거래일(ET 날짜) — 일봉 종가가 확정된 마지막 날.

    장중·개장 전이면 직전 거래일이다. 그날 일봉은 종가가 아니라 현재가라 일봉 지표에 쓰면 안 된다(plans/128 C1).
    """
    t = (now or datetime.now(_EST)).astimezone(_EST)
    d = t.date()
    if not (is_nyse_trading_day(d) and t.time() >= nyse_close_time(d)):
        d -= timedelta(days=1)
        while not is_nyse_trading_day(d):
            d -= timedelta(days=1)
    return d


def next_us_market_open(now: datetime | None = None) -> datetime:
    """다음 NYSE 정규장 개장 시각(09:30 ET, 거래일) — 지금 장중이면 오늘 개장 시각이 아니라 다음 거래일 개장."""
    t = (now or datetime.now(_EST)).astimezone(_EST)
    candidate = t.replace(hour=_NYSE_OPEN.hour, minute=_NYSE_OPEN.minute, second=0, microsecond=0)
    if candidate <= t:
        candidate += timedelta(days=1)
    while not is_nyse_trading_day(candidate.date()):
        candidate += timedelta(days=1)
    return candidate


def us_market_close_after_weekdays(weekdays: int, now: datetime | None = None) -> datetime:
    """ET 기준 오늘부터 거래일 `weekdays`일 뒤의 NYSE 정규장 마감 시각 — 환전 대기 자동 재확인 기한 계산용.

    휴장일은 세지 않는다 — 추수감사절 주에도 재확인 기회가 거래일 기준으로 줄지 않는다.
    """
    t = (now or datetime.now(_EST)).astimezone(_EST)
    day = t
    remaining = weekdays
    while remaining > 0:
        day += timedelta(days=1)
        if is_nyse_trading_day(day.date()):
            remaining -= 1
    close_at = nyse_close_time(day.date())
    return day.replace(hour=close_at.hour, minute=close_at.minute, second=0, microsecond=0)


def is_alert_execution_time(alert_time_str: str | None, now: datetime | None = None) -> bool:
    """alert의 auto_execution_time(HH:MM)이 현재 KST 시각과 일치하는지 확인 (±4분 허용).

    5분 간격 job에서 호출되므로 ±4분 범위 내에 있으면 실행 대상으로 판단한다.
    None이면 항상 True (기본 실행 대상).
    """
    t_now = (now or datetime.now(_KST)).astimezone(_KST)
    if alert_time_str is None:
        return True

    try:
        hh, mm = alert_time_str.split(":")
        target = time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return False

    now_minutes = t_now.hour * 60 + t_now.minute
    target_minutes = target.hour * 60 + target.minute
    return abs(now_minutes - target_minutes) <= 4
