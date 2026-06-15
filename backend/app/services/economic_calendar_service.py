"""경제지표 발표 캘린더 서비스 — FRED API 기반으로 향후 발표 예정일 조회."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.utils.cache_keys import (
    TTL_INDICATOR_CALENDAR,
    economic_indicator_calendar_key,
    get_cached_json,
    set_cached_json,
)

from .economic_indicator_service import INDICATORS, _fred_get_release_dates

logger = structlog.get_logger()

_DAYS_AHEAD = 90

_IMPACT: dict[str, str] = {
    "CPI_US": "High",
    "CORE_CPI_US": "High",
    "FED_RATE": "High",
    "UNEMPLOYMENT_US": "High",
    "PPI_US": "Medium",
}


async def _fetch_fred_calendar_events(days_ahead: int = _DAYS_AHEAD) -> list[dict[str, Any]]:
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
            events.append({
                "event": meta["name"],
                "date": d.isoformat(),
                "time_kst": None,
                "country": "US",
                "actual": None,
                "estimate": None,
                "previous": None,
                "impact": _IMPACT.get(code),
                "currency": None,
            })

    events.sort(key=lambda e: e["date"])
    return events


async def sync_calendar_to_cache(redis: aioredis.Redis | None) -> list[dict[str, Any]]:
    """FRED에서 캘린더 이벤트를 조회해 Redis에 저장한다."""
    events = await _fetch_fred_calendar_events()

    if redis and events:
        await set_cached_json(redis, economic_indicator_calendar_key(), events, TTL_INDICATOR_CALENDAR)
        logger.info("fred_calendar_synced", count=len(events))

    return events


async def get_calendar_events(redis: aioredis.Redis | None) -> list[dict[str, Any]]:
    """캘린더 이벤트를 반환한다. Redis 캐시 hit 시 캐시값, miss 시 FRED 직접 조회."""
    if (hit := await get_cached_json(redis, economic_indicator_calendar_key())) is not None:
        return hit
    return await sync_calendar_to_cache(redis)
