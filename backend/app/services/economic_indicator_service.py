"""경제지표 서비스 — FRED(미국) + ECOS 한국은행(한국) API 연동."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import httpx
import structlog

from app.config import settings
from app.utils.cache_keys import (
    TTL_INDICATOR_HISTORY,
    economic_indicator_history_key,
    get_cached_json,
    set_cached_json,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 지표 메타데이터 정의
# ---------------------------------------------------------------------------

INDICATORS: dict[str, dict[str, str]] = {
    "CPI_US": {
        "name": "미국 CPI",
        "name_en": "US CPI",
        "source": "fred",
        "series": "CPIAUCSL",
        "unit": "지수",
        "frequency": "monthly",
        "description": "소비자물가지수 (기준: 1982-84=100)",
    },
    "CORE_CPI_US": {
        "name": "미국 Core CPI",
        "name_en": "US Core CPI",
        "source": "fred",
        "series": "CPILFESL",
        "unit": "지수",
        "frequency": "monthly",
        "description": "식품·에너지 제외 소비자물가지수",
    },
    "FED_RATE": {
        "name": "미국 기준금리",
        "name_en": "Fed Funds Rate",
        "source": "fred",
        "series": "FEDFUNDS",
        "unit": "%",
        "frequency": "monthly",
        "description": "연방준비제도 기준금리 (실효금리)",
    },
    "UNEMPLOYMENT_US": {
        "name": "미국 실업률",
        "name_en": "US Unemployment Rate",
        "source": "fred",
        "series": "UNRATE",
        "unit": "%",
        "frequency": "monthly",
        "description": "민간 실업률 (계절조정)",
    },
    "PPI_US": {
        "name": "미국 PPI",
        "name_en": "US PPI",
        "source": "fred",
        "series": "PPIACO",
        "unit": "지수",
        "frequency": "monthly",
        "description": "생산자물가지수 (기준: 1982=100)",
    },
    "VIX": {
        "name": "VIX 공포지수",
        "name_en": "VIX Volatility Index",
        "source": "fred",
        "series": "VIXCLS",
        "unit": "지수",
        "frequency": "daily",
        "description": "CBOE 변동성 지수 — 시장 불안 심리 측정 (20 이상: 주의, 30 이상: 공포)",
    },
    "T10Y2Y": {
        "name": "장단기 금리차 (10Y-2Y)",
        "name_en": "10Y-2Y Treasury Yield Spread",
        "source": "fred",
        "series": "T10Y2Y",
        "unit": "%",
        "frequency": "daily",
        "description": "10년물-2년물 미국 국채 스프레드 — 역전(-) 시 경기침체 선행지표",
    },
    "HIGH_YIELD_SPREAD": {
        "name": "하이일드 채권 스프레드",
        "name_en": "US High Yield Spread",
        "source": "fred",
        "series": "BAMLH0A0HYM2",
        "unit": "%",
        "frequency": "daily",
        "description": "ICE BofA 하이일드 채권 옵션조정스프레드 — 급등 시 신용 경색·부도위험 확대 신호",
    },
    "DOLLAR_INDEX": {
        "name": "달러 인덱스 (Broad)",
        "name_en": "Trade Weighted US Dollar Index (Broad)",
        "source": "fred",
        "series": "DTWEXBGS",
        "unit": "지수",
        "frequency": "daily",
        "description": "주요 교역국 대비 미 달러 가치 — 급등 시 신흥국·원자재 자금 이탈 신호",
    },
    "RATE_2Y": {
        "name": "미국 2년물 국채금리",
        "name_en": "US 2-Year Treasury Yield",
        "source": "fred",
        "series": "DGS2",
        "unit": "%",
        "frequency": "daily",
        "description": "기준금리 대비 낮을수록 시장의 금리 인하 기대가 큼을 시사",
    },
}

FRED_BASE = "https://api.stlouisfed.org/fred"

# ---------------------------------------------------------------------------
# FRED API (미국 지표)
# ---------------------------------------------------------------------------


async def _fred_get_observations(series_id: str, limit: int = 36) -> list[dict[str, Any]]:
    """FRED에서 최근 limit개 관측치를 가져온다."""
    if not settings.fred_api_key:
        logger.warning("fred_api_key_not_configured", series=series_id)
        return []

    url = f"{FRED_BASE}/series/observations"
    params: dict[str, str | int] = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
        "observation_start": (date.today() - timedelta(days=limit * 35)).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("observations", [])
    except Exception as e:
        logger.error("fred_fetch_failed", series=series_id, error=str(e))
        return []


async def _fred_get_release_dates(series_id: str, upcoming: bool = False) -> list[str]:
    """FRED에서 시리즈의 발표 날짜를 가져온다.

    upcoming=True: realtime_start=오늘, sort_order=asc → 향후 예정일 반환
    upcoming=False: sort_order=desc, limit=3 → 최근 3개 과거 날짜 반환 (기본 동작)
    """
    if not settings.fred_api_key:
        return []

    url = f"{FRED_BASE}/series/release"
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            release_data = resp.json()
            releases = release_data.get("releases", [])
            if not releases:
                return []
            release_id = releases[0]["id"]

        dates_url = f"{FRED_BASE}/release/dates"
        dates_params: dict[str, str | int] = {
            "release_id": release_id,
            "api_key": settings.fred_api_key,
            "file_type": "json",
            "sort_order": "asc" if upcoming else "desc",
            "limit": 6 if upcoming else 3,
            "include_release_dates_with_no_data": "true" if upcoming else "false",
        }
        if upcoming:
            dates_params["realtime_start"] = date.today().isoformat()

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(dates_url, params=dates_params)
            resp.raise_for_status()
            dates_data = resp.json()
            return [d["date"] for d in dates_data.get("release_dates", [])]
    except Exception as e:
        logger.warning("fred_release_dates_failed", series=series_id, error=str(e))
        return []


# ---------------------------------------------------------------------------
# 공통 변환 함수
# ---------------------------------------------------------------------------


def _parse_fred_obs(obs: list[dict]) -> list[dict[str, Any]]:
    points = []
    for o in reversed(obs):  # FRED는 desc 정렬이므로 역전
        val_str = o.get("value", ".")
        if val_str == ".":
            continue
        try:
            value = float(val_str)
        except (ValueError, KeyError):
            continue
        if not math.isfinite(value):  # NaN / Inf 방어
            continue
        points.append({"date": o["date"], "value": value})
    return points


# ---------------------------------------------------------------------------
# 공개 서비스 함수
# ---------------------------------------------------------------------------


_INFLATION_CODES = ("CPI_US", "CORE_CPI_US")


async def fetch_inflation_summary(redis=None) -> list[dict[str, Any]]:
    """CPI·Core CPI 요약 반환: 최신값, 전월/전년 대비 변화율, 다음 발표일.

    리밸런싱 화면 참고용 — history/calendar 캐시를 그대로 재사용하므로 신규 FRED 호출이 없다.
    """
    from .economic_calendar_service import get_calendar_events  # 순환 임포트 회피

    calendar_events = await get_calendar_events(redis)
    next_release_by_name: dict[str, str] = {}
    for event in calendar_events:
        name = event.get("event")
        event_date = event.get("date")
        if name and event_date and name not in next_release_by_name:
            next_release_by_name[name] = event_date

    summaries: list[dict[str, Any]] = []
    for code in _INFLATION_CODES:
        meta = INDICATORS[code]
        points = await fetch_indicator_history(code, months=13, redis=redis)
        if not points:
            continue

        latest = points[-1]
        mom_change_pct = None
        if len(points) >= 2 and points[-2]["value"]:
            mom_change_pct = (latest["value"] - points[-2]["value"]) / points[-2]["value"] * 100

        yoy_change_pct = None
        if len(points) >= 13 and points[-13]["value"]:
            yoy_change_pct = (latest["value"] - points[-13]["value"]) / points[-13]["value"] * 100

        summaries.append(
            {
                "code": code,
                "name": meta["name"],
                "latest_value": latest["value"],
                "latest_date": latest["date"],
                "mom_change_pct": mom_change_pct,
                "yoy_change_pct": yoy_change_pct,
                "next_release_date": next_release_by_name.get(meta["name"]),
            }
        )

    return summaries


async def fetch_indicator_history(code: str, months: int = 24, redis=None) -> list[dict[str, Any]]:
    """지표의 최근 N개월 시계열 반환, Redis 6시간 캐시."""
    meta = INDICATORS.get(code)
    if not meta:
        return []

    cache_key = economic_indicator_history_key(code, months)
    if (hit := await get_cached_json(redis, cache_key)) is not None:
        return hit

    raw = await _fred_get_observations(meta["series"], limit=months + 3)
    points = _parse_fred_obs(raw)

    # 최근 months개만 반환
    result = points[-months:] if len(points) > months else points

    await set_cached_json(redis, cache_key, result, TTL_INDICATOR_HISTORY)
    return result
