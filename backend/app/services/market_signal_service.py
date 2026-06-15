"""시장 위험 신호 서비스 — VIX, 장단기 금리차(T10Y2Y), Fear & Greed Index 통합."""
from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

import httpx
import redis.asyncio as aioredis
import structlog

from app.utils.cache_keys import (
    TTL_MARKET_SIGNAL,
    get_cached_json,
    market_signal_latest_key,
    set_cached_json,
)
from app.utils.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger()

FNG_API_URL = "https://api.alternative.me/fng/"

# Fear & Greed API 전용 서킷브레이커 (3회 실패 → 120초 차단)
fear_greed_circuit = CircuitBreaker("FearGreedAPI", fail_max=3, reset_timeout=120.0)
# FRED API 서킷브레이커 — VIX·장단기금리차 공유 (4회 실패 → 300초 차단)
fred_circuit = CircuitBreaker("FREDAPI", fail_max=4, reset_timeout=300.0)

# ---------------------------------------------------------------------------
# 개별 신호 조회
# ---------------------------------------------------------------------------


async def fetch_vix_signal() -> dict[str, Any] | None:
    """FRED VIXCLS 시리즈에서 VIX 최신값을 가져와 위험 레벨을 판단한다."""
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal="vix")
        return None
    from app.services.economic_indicator_service import _fred_get_observations

    try:
        obs = await fred_circuit.call(_fred_get_observations, "VIXCLS", limit=5)
    except (CircuitOpenError, Exception) as exc:
        logger.warning("vix_fetch_failed", error=str(exc))
        return None
    value = _latest_value(obs)
    if value is None:
        return None

    if value < 20:
        level = "LOW"
        sub_score = 0
    elif value < 25:
        level = "MEDIUM"
        sub_score = 1
    elif value < 30:
        level = "MEDIUM_HIGH"
        sub_score = 2
    else:
        level = "HIGH"
        sub_score = 4

    return {
        "value": value,
        "level": level,
        "date": _latest_date(obs),
        "sub_score": sub_score,
    }


async def fetch_yield_curve_signal() -> dict[str, Any] | None:
    """FRED T10Y2Y 시리즈에서 10Y-2Y 스프레드 최신값을 가져와 커브 상태를 판단한다."""
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal="yield_curve")
        return None
    from app.services.economic_indicator_service import _fred_get_observations

    try:
        obs = await fred_circuit.call(_fred_get_observations, "T10Y2Y", limit=5)
    except (CircuitOpenError, Exception) as exc:
        logger.warning("yield_curve_fetch_failed", error=str(exc))
        return None
    value = _latest_value(obs)
    if value is None:
        return None

    if value > 0.5:
        state = "POSITIVE"
        sub_score = 0
    elif value > 0:
        state = "FLAT"
        sub_score = 1
    elif value > -0.5:
        state = "INVERTED"
        sub_score = 2
    else:
        state = "DEEPLY_INVERTED"
        sub_score = 3

    return {
        "value": value,
        "state": state,
        "date": _latest_date(obs),
        "sub_score": sub_score,
    }


async def _call_fng_api() -> dict[str, Any]:
    """Alternative.me Fear & Greed Index API를 실제 호출한다."""
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(FNG_API_URL, params={"limit": 1, "format": "json"})
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("data", [])
        if not entries:
            raise ValueError("fear_greed_empty_response")
        return entries[0]


async def fetch_fear_greed_signal() -> dict[str, Any] | None:
    """Alternative.me Fear & Greed Index를 조회한다 (무료, API 키 불필요).

    crypto 기반 지표이나 일반 시장 심리 프록시로 활용한다.
    서킷브레이커 차단 또는 HTTP 오류 시 None 반환.
    """
    if not fear_greed_circuit.is_available():
        logger.warning("fear_greed_circuit_open")
        return None

    try:
        entry = await fear_greed_circuit.call(_call_fng_api)
    except (CircuitOpenError, Exception) as exc:
        logger.warning("fear_greed_fetch_failed", error=str(exc))
        return None

    with contextlib.suppress(ValueError, TypeError):
        value_raw = entry.get("value", "50")
        value = int(value_raw)
        classification_raw = (entry.get("value_classification") or "Neutral").lower()

        if value <= 25:
            classification = "EXTREME_FEAR"
            sub_score = 2
        elif value <= 45:
            classification = "FEAR"
            sub_score = 1
        elif value <= 55:
            classification = "NEUTRAL"
            sub_score = 0
        elif value <= 75:
            classification = "GREED"
            sub_score = 1
        else:
            classification = "EXTREME_GREED"
            sub_score = 3

        label_map = {
            "EXTREME_FEAR": "극도의 공포",
            "FEAR": "공포",
            "NEUTRAL": "중립",
            "GREED": "탐욕",
            "EXTREME_GREED": "극도의 탐욕",
        }

        return {
            "value": value,
            "classification": classification,
            "label": label_map[classification],
            "label_en": classification_raw.replace("_", " ").title(),
            "sub_score": sub_score,
        }

    return None


# ---------------------------------------------------------------------------
# 복합 신호 계산
# ---------------------------------------------------------------------------


def compute_composite_signal(
    vix: dict[str, Any] | None,
    yield_curve: dict[str, Any] | None,
    fear_greed: dict[str, Any] | None,
) -> dict[str, Any]:
    """세 신호를 점수화해 GREEN/YELLOW/RED 복합 레벨을 반환한다.

    각 신호 조회 실패 시 해당 점수를 0으로 처리 (안전 방향 처리).
    총점 0–2 → GREEN, 3–5 → YELLOW, 6–10 → RED.
    """
    vix_score = vix["sub_score"] if vix else 0
    yc_score = yield_curve["sub_score"] if yield_curve else 0
    fg_score = fear_greed["sub_score"] if fear_greed else 0
    total = vix_score + yc_score + fg_score

    if total <= 2:
        level = "GREEN"
    elif total <= 5:
        level = "YELLOW"
    else:
        level = "RED"

    none_count = sum(1 for s in (vix, yield_curve, fear_greed) if s is None)
    if none_count == 3:
        data_freshness = "STALE"
    elif none_count > 0:
        data_freshness = "PARTIAL"
    else:
        data_freshness = "LIVE"

    fg_value = (fear_greed or {}).get("value", 50)
    fear_greed_contrarian_buy = bool(fear_greed and fg_value <= 25)
    fear_greed_extreme_greed = bool(fear_greed and fg_value >= 75)

    return {
        "composite_level": level,
        "composite_score": total,
        "fear_greed_contrarian_buy": fear_greed_contrarian_buy,
        "fear_greed_extreme_greed": fear_greed_extreme_greed,
        "signals": {
            "vix": vix,
            "yield_curve": yield_curve,
            "fear_greed": fear_greed,
        },
        "computed_at": datetime.now(UTC).isoformat(),
        "data_freshness": data_freshness,
    }


# ---------------------------------------------------------------------------
# 캐시 포함 메인 진입점
# ---------------------------------------------------------------------------


async def get_market_signal(redis: aioredis.Redis | None = None) -> dict[str, Any]:
    """복합 시장 위험 신호를 반환한다. Redis 1시간 캐시."""
    cache_key = market_signal_latest_key()

    if redis is not None and (data := await get_cached_json(redis, cache_key)) is not None:
        if isinstance(data, dict) and data.get("data_freshness") != "STALE":
            data["data_freshness"] = "CACHED"
        return data

    vix, yield_curve, fear_greed = await _fetch_all_signals()
    result = compute_composite_signal(vix, yield_curve, fear_greed)

    await set_cached_json(redis, cache_key, result, TTL_MARKET_SIGNAL)
    return result


async def _fetch_all_signals() -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """세 신호를 병렬로 조회한다. 개별 실패가 전체를 막지 않는다."""
    import asyncio

    results = await asyncio.gather(
        fetch_vix_signal(),
        fetch_yield_curve_signal(),
        fetch_fear_greed_signal(),
        return_exceptions=True,
    )

    def _safe(r: dict[str, Any] | BaseException | None) -> dict[str, Any] | None:
        if isinstance(r, BaseException):
            logger.warning("market_signal_fetch_error", error=str(r))
            return None
        return r

    return _safe(results[0]), _safe(results[1]), _safe(results[2])


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _latest_value(obs: list[dict[str, Any]]) -> float | None:
    """FRED 관측치 리스트에서 '.' 제외 최신 값을 반환한다."""
    for o in obs:
        raw = o.get("value", ".")
        if raw != ".":
            with contextlib.suppress(ValueError):
                return float(raw)
    return None


def _latest_date(obs: list[dict[str, Any]]) -> str:
    for o in obs:
        if o.get("value", ".") != ".":
            return o.get("date", "")
    return ""
