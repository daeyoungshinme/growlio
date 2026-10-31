"""한국 시간(KST) 기준 날짜/시각 헬퍼.

운영 서버(Render Docker)는 TZ 미설정 = UTC라 `date.today()`/`datetime.now()`는 KST 00:00~09:00
사이에 전날 날짜를 돌려준다(스냅샷 날짜·월별 대표값·알림 dedup이 하루 어긋남). 사용자 기준
"오늘"이 필요한 곳은 반드시 이 헬퍼를 쓴다. 미국 데이터 소스(FRED 등)처럼 상대 서버의 날짜
기준을 따라야 하는 곳은 예외.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    """현재 KST 시각 (tz-aware)."""
    return datetime.now(KST)


def today_kst() -> date:
    """KST 기준 오늘 날짜."""
    return now_kst().date()


def kst_day_start(d: date) -> datetime:
    """KST 날짜 d의 자정(tz-aware) — "오늘 이미 보냈나" 같은 하루 경계 비교용.

    `datetime(d.year, d.month, d.day, tzinfo=UTC)`로 쓰면 경계가 KST 09:00이 되어, 08:30 KST 잡의
    이력(전날 23:30 UTC)을 같은 날로 보지 못한다(plans/61 A2).
    """
    return datetime(d.year, d.month, d.day, tzinfo=KST)


def month_key(d: date) -> str:
    """`YYYY-MM`."""
    return d.strftime("%Y-%m")


def month_label(month_str: str) -> str:
    """`YYYY-MM` → `YYYY년 M월`."""
    y, m = month_str.split("-")
    return f"{y}년 {int(m)}월"
