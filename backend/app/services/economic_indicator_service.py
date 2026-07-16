"""경제지표 서비스 — FRED(미국) + ECOS 한국은행(한국) API 연동."""

from __future__ import annotations

import asyncio
import math
from datetime import date, timedelta
from typing import Any

import httpx
import structlog

from app.core.config import settings
from app.utils.cache_keys import (
    TTL_INDICATOR_CALENDAR,
    TTL_INDICATOR_HISTORY,
    economic_indicator_calendar_key,
    economic_indicator_history_key,
    get_cached_json,
    set_cached_json,
)

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 지표 메타데이터 정의
# ---------------------------------------------------------------------------
# CPI/Core CPI 외 지표(VIX, T10Y2Y, 하이일드 스프레드, 달러 인덱스 등)는
# market_signal_service.py가 FRED 시리즈 ID를 직접 호출해 사용하므로 여기 중복 정의하지 않는다.

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
}

_IMPACT: dict[str, str] = {
    "CPI_US": "High",
    "CORE_CPI_US": "High",
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
# 발표 캘린더 (CPI/Core CPI 다음 발표일 조회용 — fetch_inflation_summary 전용 소비자)
# ---------------------------------------------------------------------------

_CALENDAR_DAYS_AHEAD = 90


async def _fetch_fred_calendar_events(days_ahead: int = _CALENDAR_DAYS_AHEAD) -> list[dict[str, Any]]:
    """FRED에서 각 지표의 향후 발표 예정일을 병렬로 조회해 캘린더 형식으로 반환한다."""
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)

    codes = list(INDICATORS.keys())
    series_ids = [INDICATORS[c]["series"] for c in codes]

    raw_results: list[list[str] | BaseException] = await asyncio.gather(
        *[_fred_get_release_dates(sid, upcoming=True) for sid in series_ids],
        return_exceptions=True,
    )

    events: list[dict[str, Any]] = []
    for code, dates_or_exc in zip(codes, raw_results, strict=False):
        if isinstance(dates_or_exc, BaseException):
            logger.warning("fred_calendar_fetch_failed", code=code, error=str(dates_or_exc))
            continue

        meta = INDICATORS[code]
        for release_date in dates_or_exc:
            try:
                d = date.fromisoformat(release_date)
            except (ValueError, TypeError):
                continue
            if not (today <= d <= cutoff):
                continue
            events.append(
                {
                    "event": meta["name"],
                    "date": d.isoformat(),
                    "time_kst": None,
                    "country": "US",
                    "actual": None,
                    "estimate": None,
                    "previous": None,
                    "impact": _IMPACT.get(code),
                    "currency": None,
                }
            )

    events.sort(key=lambda e: e["date"])
    return events


async def sync_calendar_to_cache(redis) -> list[dict[str, Any]]:
    """FRED에서 캘린더 이벤트를 조회해 Redis에 저장한다."""
    events = await _fetch_fred_calendar_events()

    if redis and events:
        await set_cached_json(redis, economic_indicator_calendar_key(), events, TTL_INDICATOR_CALENDAR)
        logger.info("fred_calendar_synced", count=len(events))

    return events


async def get_calendar_events(redis) -> list[dict[str, Any]]:
    """캘린더 이벤트를 반환한다. Redis 캐시 hit 시 캐시값, miss 시 FRED 직접 조회."""
    if (hit := await get_cached_json(redis, economic_indicator_calendar_key())) is not None:
        return hit
    return await sync_calendar_to_cache(redis)


# ---------------------------------------------------------------------------
# 공개 서비스 함수
# ---------------------------------------------------------------------------


_INFLATION_CODES = ("CPI_US", "CORE_CPI_US")


async def fetch_inflation_summary(redis=None) -> list[dict[str, Any]]:
    """CPI·Core CPI 요약 반환: 최신값, 전월/전년 대비 변화율, 다음 발표일.

    리밸런싱 화면 참고용 — history/calendar 캐시를 그대로 재사용하므로 신규 FRED 호출이 없다.
    """
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
