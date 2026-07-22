"""장 중 여부 판단 유틸리티 — KRX/NYSE 정규 거래시간 기준."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")
_EST = ZoneInfo("America/New_York")

# KRX 정규 거래시간 (KST)
_KRX_OPEN = time(9, 0)
_KRX_CLOSE = time(15, 30)

# NYSE/NASDAQ 정규 거래시간 (ET)
_NYSE_OPEN = time(9, 30)
_NYSE_CLOSE = time(16, 0)


def is_korean_market_open(now: datetime | None = None) -> bool:
    """KRX 정규 장 여부: 평일 09:00~15:30 KST."""
    t = (now or datetime.now(_KST)).astimezone(_KST)
    if t.weekday() >= 5:
        return False
    return _KRX_OPEN <= t.time() <= _KRX_CLOSE


def korean_market_close_datetime(now: datetime | None = None) -> datetime:
    """오늘(KST) KRX 정규장 마감 시각(15:30 KST)을 timezone-aware datetime으로 반환한다.

    리밸런싱 매도 승인 만료 시각(당일 장마감) 계산에 사용한다.
    """
    t = (now or datetime.now(_KST)).astimezone(_KST)
    return t.replace(hour=_KRX_CLOSE.hour, minute=_KRX_CLOSE.minute, second=0, microsecond=0)


def is_us_market_open(now: datetime | None = None) -> bool:
    """NYSE/NASDAQ 정규 장 여부: 평일 09:30~16:00 ET (DST 자동 반영)."""
    t = (now or datetime.now(_EST)).astimezone(_EST)
    if t.weekday() >= 5:
        return False
    return _NYSE_OPEN <= t.time() <= _NYSE_CLOSE


def us_market_close_datetime(now: datetime | None = None) -> datetime:
    """오늘(ET 기준) NYSE 정규장 마감 시각(16:00 ET)을 timezone-aware datetime으로 반환한다.

    ET 기준 "오늘"이므로 KST로 보면 자정을 넘어갈 수 있다(DST에 따라 익일 05:00~06:00 KST) —
    리밸런싱 해외 leg 매도 승인 만료 시각(당일 장마감) 계산에 사용한다.
    """
    t = (now or datetime.now(_EST)).astimezone(_EST)
    return t.replace(hour=_NYSE_CLOSE.hour, minute=_NYSE_CLOSE.minute, second=0, microsecond=0)


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
