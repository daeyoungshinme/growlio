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


def is_us_market_open(now: datetime | None = None) -> bool:
    """NYSE/NASDAQ 정규 장 여부: 평일 09:30~16:00 ET (DST 자동 반영)."""
    t = (now or datetime.now(_EST)).astimezone(_EST)
    if t.weekday() >= 5:
        return False
    return _NYSE_OPEN <= t.time() <= _NYSE_CLOSE


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
