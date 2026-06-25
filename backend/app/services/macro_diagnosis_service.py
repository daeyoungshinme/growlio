"""거시경제 진단 서비스 — CPI 추세·기준금리·FOMC 일정을 종합해 리밸런싱 시사점을 반환한다."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal

import structlog

from app.utils.cache_keys import (
    TTL_MACRO_DIAGNOSIS,
    get_cached_json,
    macro_diagnosis_key,
    set_cached_json,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# FOMC 회의 일정 폴백 상수 (FMP/FRED 조회 실패 시 사용)
# 출처: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
# ---------------------------------------------------------------------------

FOMC_DATES_FALLBACK: list[str] = [
    "2025-07-30",
    "2025-09-17",
    "2025-11-05",
    "2025-12-17",
    "2026-01-28",
    "2026-03-18",
    "2026-04-29",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-16",
]

# CPI direction 판정 임계값 (지수값 기준, CPIAUCSL 단위)
_CPI_RISING_THRESHOLD = 0.15
_CPI_FALLING_THRESHOLD = -0.15

# 고금리 기준선 (%)
_FED_RATE_HIGH_THRESHOLD = 4.5


# ---------------------------------------------------------------------------
# 개별 분석 함수 (순수 계산 — 외부 IO 없음)
# ---------------------------------------------------------------------------


def _analyze_cpi_trend(
    history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """FRED CPIAUCSL 시계열에서 CPI 추세를 분석한다.

    history: fetch_indicator_history("CPI_US") 결과 (오름차순 날짜)
    """
    if len(history) < 2:
        return None

    # 월별 데이터 오름차순 정렬 확인
    sorted_hist = sorted(history, key=lambda x: x["date"])
    latest = sorted_hist[-1]
    latest_value: float = latest["value"]
    latest_date: str = latest["date"]

    # 3개월 변화량
    change_3m: float | None = None
    if len(sorted_hist) >= 4:
        three_months_ago = sorted_hist[-4]["value"]
        change_3m = latest_value - three_months_ago

    # 전년 동월 대비 YoY (12개월 전 데이터가 있으면 계산)
    yoy_pct: float | None = None
    if len(sorted_hist) >= 13:
        year_ago_value = sorted_hist[-13]["value"]
        if year_ago_value:
            yoy_pct = round((latest_value / year_ago_value - 1) * 100, 2)

    # 방향 판단
    if change_3m is not None:
        if change_3m > _CPI_RISING_THRESHOLD:
            direction: Literal["rising", "flat", "falling"] = "rising"
        elif change_3m < _CPI_FALLING_THRESHOLD:
            direction = "falling"
        else:
            direction = "flat"
    else:
        direction = "flat"

    return {
        "direction": direction,
        "latest_value": round(latest_value, 2),
        "latest_date": latest_date,
        "yoy_pct": yoy_pct,
        "change_3m": round(change_3m, 3) if change_3m is not None else None,
        "month_count": len(sorted_hist),
    }


def _analyze_fed_rate(
    history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """FRED FEDFUNDS 시계열에서 기준금리 현황을 분석한다."""
    if len(history) < 2:
        return None

    sorted_hist = sorted(history, key=lambda x: x["date"])
    latest = sorted_hist[-1]
    latest_value: float = latest["value"]

    # 6개월 전 대비 방향
    prev = sorted_hist[-7] if len(sorted_hist) >= 7 else sorted_hist[0]
    diff = latest_value - prev["value"]
    if diff > 0.1:
        direction: Literal["rising", "stable", "falling"] = "rising"
    elif diff < -0.1:
        direction = "falling"
    else:
        direction = "stable"

    return {
        "latest_value": round(latest_value, 2),
        "latest_date": latest["date"],
        "direction": direction,
        "is_high": latest_value >= _FED_RATE_HIGH_THRESHOLD,
    }


def _analyze_fomc_schedule(
    calendar_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """캘린더 이벤트 목록에서 FED_RATE 관련 이벤트를 필터링해 다음 FOMC 날짜를 반환한다.

    이벤트가 없으면 하드코딩된 FOMC 일정(FOMC_DATES_FALLBACK)을 폴백으로 사용한다.
    """
    today = date.today()

    # 1차: 캘린더 이벤트 중 FED_RATE 관련 항목 검색
    fed_events = [e for e in calendar_events if "기준금리" in e.get("event", "") or "Fed" in e.get("event", "")]
    for event in sorted(fed_events, key=lambda x: x["date"]):
        try:
            d = date.fromisoformat(event["date"])
        except (ValueError, TypeError):
            continue
        if d >= today:
            days_until = (d - today).days
            return {
                "next_meeting_date": d.isoformat(),
                "days_until": days_until,
                "source": "calendar",
            }

    # 2차 폴백: 하드코딩된 FOMC 일정
    for date_str in FOMC_DATES_FALLBACK:
        try:
            d = date.fromisoformat(date_str)
        except (ValueError, TypeError):
            continue
        if d >= today:
            days_until = (d - today).days
            return {
                "next_meeting_date": d.isoformat(),
                "days_until": days_until,
                "source": "fallback",
            }

    return {"next_meeting_date": None, "days_until": None, "source": "unknown"}


# ---------------------------------------------------------------------------
# 거시경제 → 리밸런싱 시사점 도출
# ---------------------------------------------------------------------------

_IMPLICATION_TABLE: dict[tuple[str, bool], dict[str, str]] = {
    ("rising", True): {
        "label": "긴축 지속 가능성",
        "growth_bias": "bearish",
        "message": (
            "CPI 상승세가 이어져 금리 인하 가능성이 낮습니다. "
            "성장주 비중 축소와 단기채·배당주 비중 확대를 고려하세요."
        ),
        "action": "성장주 비중 축소 고려",
    },
    ("flat", True): {
        "label": "금리 고점 유지",
        "growth_bias": "neutral",
        "message": (
            "물가 안정 초기 신호이나 금리는 당분간 현 수준 유지 가능성이 높습니다. "
            "현 포트폴리오 비중을 유지하세요."
        ),
        "action": "현 포지션 유지",
    },
    ("falling", True): {
        "label": "금리 인하 기대",
        "growth_bias": "bullish",
        "message": "인플레이션 둔화로 금리 인하 기대가 높아집니다. 성장주·장기채 비중 확대를 검토하세요.",
        "action": "성장주·장기채 비중 확대 고려",
    },
    ("rising", False): {
        "label": "스태그플레이션 주의",
        "growth_bias": "bearish",
        "message": "저금리 상황에서 물가가 재상승하고 있습니다. 실물자산·원자재·배당주 등 방어 포지션을 점검하세요.",
        "action": "방어적 포지션 점검",
    },
    ("flat", False): {
        "label": "경기 안정 국면",
        "growth_bias": "neutral",
        "message": "물가와 금리가 안정된 국면입니다. 목표 비중을 유지하며 정기 리밸런싱 주기를 지키세요.",
        "action": "목표 비중 유지",
    },
    ("falling", False): {
        "label": "경기 부양 국면",
        "growth_bias": "bullish",
        "message": "물가 안정 + 저금리 환경으로 위험자산 선호도가 높습니다. 성장주 비중을 목표 수준까지 유지하세요.",
        "action": "목표 비중 유지",
    },
}


def _derive_implication(
    cpi: dict[str, Any] | None,
    fed: dict[str, Any] | None,
) -> dict[str, str] | None:
    if cpi is None or fed is None:
        return None
    key = (cpi["direction"], fed["is_high"])
    return _IMPLICATION_TABLE.get(key)


# ---------------------------------------------------------------------------
# 메인 서비스 함수
# ---------------------------------------------------------------------------


async def get_macro_diagnosis(redis: Any) -> dict[str, Any]:
    """CPI 추세·기준금리·FOMC 일정을 종합한 거시경제 진단 딕셔너리를 반환한다.

    Redis 1시간 캐시. 개별 지표는 fetch_indicator_history 6시간 캐시를 재사용하므로
    FRED API 추가 호출이 발생하지 않는다.
    """
    from app.services.economic_calendar_service import get_calendar_events
    from app.services.economic_indicator_service import fetch_indicator_history

    cache_key = macro_diagnosis_key()
    if (hit := await get_cached_json(redis, cache_key)) is not None:
        return hit

    # 지표 시계열 + 캘린더 병렬 조회
    import asyncio

    async def _safe_fetch_cpi() -> list[dict[str, Any]]:
        try:
            return await fetch_indicator_history("CPI_US", months=14, redis=redis)
        except Exception as exc:
            logger.warning("macro_cpi_fetch_failed", error=str(exc))
            return []

    async def _safe_fetch_fed() -> list[dict[str, Any]]:
        try:
            return await fetch_indicator_history("FED_RATE", months=8, redis=redis)
        except Exception as exc:
            logger.warning("macro_fed_fetch_failed", error=str(exc))
            return []

    async def _safe_fetch_cal() -> list[dict[str, Any]]:
        try:
            return await get_calendar_events(redis)
        except Exception as exc:
            logger.warning("macro_calendar_fetch_failed", error=str(exc))
            return []

    cpi_hist, fed_hist, calendar_events = await asyncio.gather(_safe_fetch_cpi(), _safe_fetch_fed(), _safe_fetch_cal())

    cpi = _analyze_cpi_trend(cpi_hist)
    fed = _analyze_fed_rate(fed_hist)
    fomc = _analyze_fomc_schedule(calendar_events)
    implication = _derive_implication(cpi, fed)

    # data_freshness 판단
    has_cpi = cpi is not None
    has_fed = fed is not None
    if has_cpi and has_fed:
        freshness = "LIVE"
    elif has_cpi or has_fed:
        freshness = "PARTIAL"
    else:
        freshness = "STALE"

    result: dict[str, Any] = {
        "cpi": cpi,
        "fed_rate": fed,
        "fomc": fomc,
        "implication": implication,
        "data_freshness": freshness,
        "computed_at": datetime.now(tz=UTC).isoformat(),
    }

    await set_cached_json(redis, cache_key, result, TTL_MACRO_DIAGNOSIS)
    logger.info("macro_diagnosis_computed", freshness=freshness, cpi_dir=cpi and cpi["direction"])
    return result
