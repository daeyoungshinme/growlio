"""장 중 여부 판단 유틸리티 — KRX/NYSE 정규 거래시간·휴장일 기준.

휴장일은 `holidays` 패키지의 거래소 달력(XKRX·NYSE)을 쓴다. 반일장(NYSE 조기 폐장 13:00)과
KRX 연초 개장 지연(10:00)은 반영하지 않는다 — 그 날 늦은 시각 발주는 증권사가 거부한다(plans/122 A1).
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


def is_korean_market_open(now: datetime | None = None) -> bool:
    """KRX 정규 장 여부: 거래일 09:00~15:30 KST."""
    t = (now or datetime.now(_KST)).astimezone(_KST)
    if not is_krx_trading_day(t.date()):
        return False
    return _KRX_OPEN <= t.time() <= _KRX_CLOSE


def korean_market_close_datetime(now: datetime | None = None) -> datetime:
    """오늘(KST) KRX 정규장 마감 시각(15:30 KST)을 timezone-aware datetime으로 반환한다.

    리밸런싱 매도 승인 만료 시각(당일 장마감) 계산에 사용한다.
    """
    t = (now or datetime.now(_KST)).astimezone(_KST)
    return t.replace(hour=_KRX_CLOSE.hour, minute=_KRX_CLOSE.minute, second=0, microsecond=0)


def is_us_market_open(now: datetime | None = None) -> bool:
    """NYSE/NASDAQ 정규 장 여부: 거래일 09:30~16:00 ET (DST 자동 반영)."""
    t = (now or datetime.now(_EST)).astimezone(_EST)
    if not is_nyse_trading_day(t.date()):
        return False
    return _NYSE_OPEN <= t.time() <= _NYSE_CLOSE


def us_market_close_datetime(now: datetime | None = None) -> datetime:
    """오늘(ET 기준) NYSE 정규장 마감 시각(16:00 ET)을 timezone-aware datetime으로 반환한다.

    ET 기준 "오늘"이므로 KST로 보면 자정을 넘어갈 수 있다(DST에 따라 익일 05:00~06:00 KST) —
    리밸런싱 해외 leg 매도 승인 만료 시각(당일 장마감) 계산에 사용한다.
    """
    t = (now or datetime.now(_EST)).astimezone(_EST)
    return t.replace(hour=_NYSE_CLOSE.hour, minute=_NYSE_CLOSE.minute, second=0, microsecond=0)


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
    return day.replace(hour=_NYSE_CLOSE.hour, minute=_NYSE_CLOSE.minute, second=0, microsecond=0)


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
