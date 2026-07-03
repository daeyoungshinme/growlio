"""시장 위험 신호 서비스 — VIX, 장단기 금리차(T10Y2Y), Fear & Greed Index,
하이일드 스프레드, 달러 인덱스, 금리인하기대(2Y-FEDFUNDS 대체지표) 통합."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

import httpx
import redis.asyncio as aioredis
import structlog

from app.utils.cache_keys import (
    TTL_MARKET_SIGNAL,
    TTL_MARKET_SIGNAL_LAST_LEVEL,
    get_cached_json,
    market_signal_last_level_key,
    market_signal_latest_key,
    set_cached_json,
)
from app.utils.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = structlog.get_logger()

FNG_API_URL = "https://api.alternative.me/fng/"

# Alternative.me API value_classification → 내부 ENUM 매핑
_FNG_CLASSIFICATION_MAP: dict[str, str] = {
    "extreme fear": "EXTREME_FEAR",
    "fear": "FEAR",
    "neutral": "NEUTRAL",
    "greed": "GREED",
    "extreme greed": "EXTREME_GREED",
}

_FNG_LABEL_EN_MAP: dict[str, str] = {
    "EXTREME_FEAR": "Extreme Fear",
    "FEAR": "Fear",
    "NEUTRAL": "Neutral",
    "GREED": "Greed",
    "EXTREME_GREED": "Extreme Greed",
}

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


async def fetch_high_yield_spread_signal() -> dict[str, Any] | None:
    """FRED BAMLH0A0HYM2(하이일드 채권 스프레드) 최신값으로 신용 경색 위험도를 판단한다."""
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal="high_yield_spread")
        return None
    from app.services.economic_indicator_service import _fred_get_observations

    try:
        obs = await fred_circuit.call(_fred_get_observations, "BAMLH0A0HYM2", limit=5)
    except (CircuitOpenError, Exception) as exc:
        logger.warning("high_yield_spread_fetch_failed", error=str(exc))
        return None
    value = _latest_value(obs)
    if value is None:
        return None

    if value < 4:
        level = "NORMAL"
        sub_score = 0
    elif value < 5:
        level = "ELEVATED"
        sub_score = 1
    elif value < 7:
        level = "STRESSED"
        sub_score = 2
    else:
        level = "CRISIS"
        sub_score = 4

    return {
        "value": value,
        "level": level,
        "date": _latest_date(obs),
        "sub_score": sub_score,
    }


async def fetch_dollar_index_signal() -> dict[str, Any] | None:
    """FRED DTWEXBGS(달러 인덱스) 20일 이동평균 대비 이격도로 달러 강세 돌파 신호를 판단한다.

    달러 급등(20일선 상향 이탈)은 신흥국·원자재 자산에서 자금이 이탈하는 신호로 해석한다.
    """
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal="dollar_index")
        return None
    from app.services.economic_indicator_service import _fred_get_observations, _parse_fred_obs

    try:
        obs = await fred_circuit.call(_fred_get_observations, "DTWEXBGS", limit=30)
    except (CircuitOpenError, Exception) as exc:
        logger.warning("dollar_index_fetch_failed", error=str(exc))
        return None

    points = _parse_fred_obs(obs)
    if len(points) < 20:
        return None

    recent = points[-20:]
    ma20 = sum(p["value"] for p in recent) / len(recent)
    latest = points[-1]
    if ma20 == 0:
        return None
    deviation_pct = (latest["value"] - ma20) / ma20 * 100

    if deviation_pct <= 1:
        level = "NORMAL"
        sub_score = 0
    elif deviation_pct <= 3:
        level = "ELEVATED"
        sub_score = 1
    elif deviation_pct <= 5:
        level = "HIGH"
        sub_score = 2
    else:
        level = "BREAKOUT"
        sub_score = 3

    return {
        "value": latest["value"],
        "ma20": round(ma20, 2),
        "deviation_pct": round(deviation_pct, 2),
        "level": level,
        "date": latest["date"],
        "sub_score": sub_score,
    }


async def fetch_rate_cut_expectation_signal() -> dict[str, Any] | None:
    """FRED DGS2(2년물)-FEDFUNDS(기준금리) 스프레드로 시장의 금리 인하 기대를 근사한다.

    CME FedWatch(금리선물 기반 실제 인하 확률)는 공식 무료 API가 없어 채택한 대체 지표 —
    스프레드가 깊이 마이너스일수록 인하 기대(또는 경기침체 우려)가 크다는 방향성만 참고한다.
    """
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal="rate_cut_expectation")
        return None
    import asyncio

    from app.services.economic_indicator_service import _fred_get_observations

    try:
        dgs2_obs, fedfunds_obs = await asyncio.gather(
            fred_circuit.call(_fred_get_observations, "DGS2", limit=5),
            fred_circuit.call(_fred_get_observations, "FEDFUNDS", limit=5),
        )
    except (CircuitOpenError, Exception) as exc:
        logger.warning("rate_cut_expectation_fetch_failed", error=str(exc))
        return None

    dgs2 = _latest_value(dgs2_obs)
    fedfunds = _latest_value(fedfunds_obs)
    if dgs2 is None or fedfunds is None:
        return None

    spread = dgs2 - fedfunds

    if spread >= -0.25:
        level = "NEUTRAL"
        sub_score = 0
    elif spread >= -0.75:
        level = "MILD_CUT_EXPECTED"
        sub_score = 1
    elif spread >= -1.5:
        level = "CUT_EXPECTED"
        sub_score = 2
    else:
        level = "DEEP_CUT_EXPECTED"
        sub_score = 3

    return {
        "value": round(spread, 2),
        "dgs2": dgs2,
        "fedfunds": fedfunds,
        "level": level,
        "date": _latest_date(dgs2_obs),
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

        # API 원본 분류를 그대로 사용해 Alternative.me 사이트 값과 일치시킴
        classification = _FNG_CLASSIFICATION_MAP.get(classification_raw, "NEUTRAL")

        # sub_score는 복합 신호(GREEN/YELLOW/RED) 산정용으로 value 기반 유지
        if value <= 25:
            sub_score = 2
        elif value <= 45:
            sub_score = 1
        elif value <= 55:
            sub_score = 0
        elif value <= 75:
            sub_score = 1
        else:
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
            "label_en": _FNG_LABEL_EN_MAP[classification],
            "sub_score": sub_score,
        }

    return None


# ---------------------------------------------------------------------------
# 복합 신호 계산
# ---------------------------------------------------------------------------


# 복합 점수 임계값 — 기존 3개 신호(상한 10) 배점 비율(GREEN 0-20%, YELLOW 30-50%, RED 60-100%)을
# 6개 신호(상한 20)로 확장하면서 그대로 보존: new_threshold = old_threshold * (20/10)
COMPOSITE_SCORE_MAX = 20
_GREEN_MAX = 4  # old: 2
_YELLOW_MAX = 10  # old: 5


def compute_composite_signal(
    vix: dict[str, Any] | None,
    yield_curve: dict[str, Any] | None,
    fear_greed: dict[str, Any] | None,
    high_yield_spread: dict[str, Any] | None = None,
    dollar_index: dict[str, Any] | None = None,
    rate_cut_expectation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """여섯 신호를 점수화해 GREEN/YELLOW/RED 복합 레벨을 반환한다.

    각 신호 조회 실패 시 해당 점수를 0으로 처리 (안전 방향 처리).
    총점 0–4 → GREEN, 5–10 → YELLOW, 11–20 → RED (상한 20 = 기존 VIX/YC/FG 상한 10에
    하이일드 스프레드·달러인덱스·금리인하기대 상한 10을 더한 값, 임계값은 옛 비율 그대로 2배 확장).
    """
    vix_score = vix["sub_score"] if vix else 0
    yc_score = yield_curve["sub_score"] if yield_curve else 0
    fg_score = fear_greed["sub_score"] if fear_greed else 0
    hy_score = high_yield_spread["sub_score"] if high_yield_spread else 0
    usd_score = dollar_index["sub_score"] if dollar_index else 0
    rate_score = rate_cut_expectation["sub_score"] if rate_cut_expectation else 0
    total = vix_score + yc_score + fg_score + hy_score + usd_score + rate_score

    if total <= _GREEN_MAX:
        level = "GREEN"
    elif total <= _YELLOW_MAX:
        level = "YELLOW"
    else:
        level = "RED"

    all_signals = (vix, yield_curve, fear_greed, high_yield_spread, dollar_index, rate_cut_expectation)
    none_count = sum(1 for s in all_signals if s is None)
    if none_count == len(all_signals):
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
        "composite_score_max": COMPOSITE_SCORE_MAX,
        "fear_greed_contrarian_buy": fear_greed_contrarian_buy,
        "fear_greed_extreme_greed": fear_greed_extreme_greed,
        "signals": {
            "vix": vix,
            "yield_curve": yield_curve,
            "fear_greed": fear_greed,
            "high_yield_spread": high_yield_spread,
            "dollar_index": dollar_index,
            "rate_cut_expectation": rate_cut_expectation,
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

    vix, yield_curve, fear_greed, high_yield_spread, dollar_index, rate_cut_expectation = await _fetch_all_signals()
    result = compute_composite_signal(
        vix, yield_curve, fear_greed, high_yield_spread, dollar_index, rate_cut_expectation
    )

    await set_cached_json(redis, cache_key, result, TTL_MARKET_SIGNAL)
    return result


async def get_last_composite_level(redis: aioredis.Redis | None) -> str | None:
    """등급 변화 감지 job이 마지막으로 관측한 composite_level을 조회한다. 없으면 None."""
    if redis is None:
        return None
    return await get_cached_json(redis, market_signal_last_level_key())


async def set_last_composite_level(redis: aioredis.Redis | None, level: str) -> None:
    """현재 composite_level을 다음 비교를 위해 저장한다."""
    await set_cached_json(redis, market_signal_last_level_key(), level, TTL_MARKET_SIGNAL_LAST_LEVEL)


async def _fetch_all_signals() -> tuple[
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """여섯 신호를 병렬로 조회한다. 개별 실패가 전체를 막지 않는다."""
    import asyncio

    results = await asyncio.gather(
        fetch_vix_signal(),
        fetch_yield_curve_signal(),
        fetch_fear_greed_signal(),
        fetch_high_yield_spread_signal(),
        fetch_dollar_index_signal(),
        fetch_rate_cut_expectation_signal(),
        return_exceptions=True,
    )

    def _safe(r: dict[str, Any] | BaseException | None) -> dict[str, Any] | None:
        if isinstance(r, BaseException):
            logger.warning("market_signal_fetch_error", error=str(r))
            return None
        return r

    return tuple(_safe(r) for r in results)  # type: ignore[return-value]


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
