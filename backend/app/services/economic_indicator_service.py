"""경제지표 서비스 — FRED(미국) + ECOS 한국은행(한국) API 연동."""
from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import select

from app.config import settings
from app.models.indicator_subscription import IndicatorSubscription
from app.utils.cache_keys import (
    TTL_INDICATOR_HISTORY,
    TTL_INDICATOR_LATEST,
    economic_indicator_history_key,
    economic_indicator_latest_key,
    get_cached_json,
    invalidate_user_caches,
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


async def fetch_indicator_latest(code: str, redis=None) -> dict[str, Any] | None:
    """지표의 최신값 + 전월값 반환, Redis 1시간 캐시."""
    meta = INDICATORS.get(code)
    if not meta:
        return None

    cache_key = economic_indicator_latest_key(code)
    if (hit := await get_cached_json(redis, cache_key)) is not None:
        return hit

    raw = await _fred_get_observations(meta["series"], limit=3)
    points = _parse_fred_obs(raw)

    if not points:
        return None

    latest = points[-1]
    previous = points[-2] if len(points) >= 2 else None

    change = None
    change_pct = None
    if previous and previous["value"]:
        change = latest["value"] - previous["value"]
        change_pct = change / previous["value"] * 100

    result: dict[str, Any] = {
        "code": code,
        "name": meta["name"],
        "name_en": meta["name_en"],
        "unit": meta["unit"],
        "frequency": meta["frequency"],
        "description": meta["description"],
        "latest_value": latest["value"],
        "latest_date": latest["date"],
        "previous_value": previous["value"] if previous else None,
        "previous_date": previous["date"] if previous else None,
        "change": change,
        "change_pct": change_pct,
    }

    await set_cached_json(redis, cache_key, result, TTL_INDICATOR_LATEST)
    return result


async def fetch_all_indicators(redis=None) -> list[dict[str, Any]]:
    """모든 지표의 최신값 목록 반환."""
    import asyncio

    tasks = [fetch_indicator_latest(code, redis) for code in INDICATORS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, dict)]


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


# ---------------------------------------------------------------------------
# 구독 관리
# ---------------------------------------------------------------------------


async def get_user_subscriptions(user_id, db) -> list[str]:
    """사용자가 구독 중인 indicator_code 목록."""
    result = await db.execute(
        select(IndicatorSubscription.indicator_code)
        .where(IndicatorSubscription.user_id == user_id)
    )
    return [row[0] for row in result.all()]


async def subscribe_indicator(user_id, code: str, db) -> None:
    """경제지표 알림 구독 추가. 이미 구독 중이면 무시."""
    if code not in INDICATORS:
        raise ValueError(f"지원하지 않는 지표 코드: {code}")

    existing = await db.scalar(
        select(IndicatorSubscription).where(
            IndicatorSubscription.user_id == user_id,
            IndicatorSubscription.indicator_code == code,
        )
    )
    if existing:
        return

    db.add(IndicatorSubscription(user_id=user_id, indicator_code=code))
    await db.commit()


async def unsubscribe_indicator(user_id, code: str, db) -> None:
    """경제지표 알림 구독 해제."""
    existing = await db.scalar(
        select(IndicatorSubscription).where(
            IndicatorSubscription.user_id == user_id,
            IndicatorSubscription.indicator_code == code,
        )
    )
    if existing:
        await db.delete(existing)
        await db.commit()


# ---------------------------------------------------------------------------
# 내부 유틸 (알림 잡에서 사용)
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


async def sync_all_to_cache(redis) -> dict[str, dict[str, Any]]:
    """모든 지표 최신값을 FRED/ECOS에서 강제 갱신 후 반환."""
    import asyncio
    await invalidate_user_caches(redis, *[economic_indicator_latest_key(c) for c in INDICATORS])

    results = {}
    tasks = [(code, fetch_indicator_latest(code, redis)) for code in INDICATORS]
    gathered = await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)
    for (code, _), result in zip(tasks, gathered, strict=False):
        if isinstance(result, dict):
            results[code] = result
    return results
