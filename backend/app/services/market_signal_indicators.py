"""시장 위험 신호 — 개별 지표 조회(FRED·Yahoo·환율).

`market_signal_service.py`(835줄)에서 분리(docs/plans/41). 지표별 sub_score 산정까지 여기서 하고,
복합 점수·레벨은 `market_signal_scoring`, 캐시·hysteresis 진입점은 `market_signal_service`가 담당한다.
외부 호출부는 계속 `market_signal_service`에서 import한다(재노출).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import structlog

from app.utils.circuit_breaker import CircuitOpenError, fred_circuit

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

logger = structlog.get_logger()

# FRED API 서킷브레이커(VIX·미국 금리 커브 공유)는 app/utils/circuit_breaker.py에서 생성 —
# 임계값은 config.py의 cb_fred_* 필드로 조정

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


async def fetch_us_rate_curve_signal() -> dict[str, Any] | None:
    """장단기 금리차(T10Y2Y)와 금리인하 기대(DGS2-FEDFUNDS)를 하나의 "미국 금리 커브" 신호로 병합한다.

    두 지표 모두 사실상 "Fed 정책금리 경로 기대"라는 동일한 정보를 반영해 위기 국면에서 동시에
    악화되는 경향이 있다 — 복합점수에 각각 더하면 같은 리스크를 이중 계상하게 된다. sub_score는
    두 원신호 sub_score의 worst-case(max)만 반영해 이중계상을 없애되, 둘 중 하나만 위험 신호를
    보내는 경우도 놓치지 않는다.
    """
    import asyncio

    yc, rate = await asyncio.gather(fetch_yield_curve_signal(), fetch_rate_cut_expectation_signal())
    if yc is None and rate is None:
        return None

    yc_sub = yc["sub_score"] if yc else 0
    rate_sub = rate["sub_score"] if rate else 0
    reference = yc or rate
    assert reference is not None  # nosec B101 - 위에서 둘 다 None인 경우는 이미 반환됨

    return {
        "yield_curve_value": yc["value"] if yc else None,
        "yield_curve_state": yc["state"] if yc else None,
        "rate_cut_value": rate["value"] if rate else None,
        "rate_cut_level": rate["level"] if rate else None,
        "sub_score": max(yc_sub, rate_sub),
        "date": reference["date"],
    }


async def fetch_exchange_rate_signal(cache: CacheStore | None = None) -> dict[str, Any] | None:
    """실시간 원/달러 환율의 FRED DEXKOUS 20일 이동평균 대비 이격도로 원화 약세 방향성을 판단한다.

    실시간 "예측치"가 아닌 참고 지표 — 원/달러 급등(20일선 상향 이탈)은 원화 약세 심화·
    자금 이탈 우려 방향으로 해석하며, 달러 인덱스 신호와 동일한 산출 로직을 재사용한다.

    FRED DEXKOUS는 연준 H.10 발표 특성상 최신 관측치가 실제로 1주일 이상 지연되는 경우가
    있어 그대로 "현재 환율"로 노출하면 실제 시세와 크게 어긋난다. 따라서 표시용 현재값
    (value)과 이격도 계산의 기준값은 앱 전역에서 쓰는 실시간 캐시(get_usd_krw_rate)를 쓰고,
    FRED 시계열은 원래 목적대로 ma20(20일 이동평균) 산출에만 사용한다 — 이동평균은 개별
    관측치가 며칠 지연되어 섞여도 방향성 판단에 미치는 영향이 작다.
    """
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal="exchange_rate")
        return None
    from app.services.economic_indicator_service import _fred_get_observations, _parse_fred_obs

    try:
        obs = await fred_circuit.call(_fred_get_observations, "DEXKOUS", limit=30)
    except (CircuitOpenError, Exception) as exc:
        logger.warning("exchange_rate_fetch_failed", error=str(exc))
        return None

    points = _parse_fred_obs(obs)
    if len(points) < 20:
        return None

    recent = points[-20:]
    ma20 = sum(p["value"] for p in recent) / len(recent)
    if ma20 == 0:
        return None

    from app.utils.currency import get_usd_krw_rate

    live_rate = await get_usd_krw_rate(cache)
    deviation_pct = (live_rate - ma20) / ma20 * 100

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
        "value": round(live_rate, 2),
        "ma20": round(ma20, 2),
        "deviation_pct": round(deviation_pct, 2),
        "level": level,
        "date": recent[-1]["date"],  # ma20 산출 기준 FRED 최신 관측일 (value의 기준일 아님)
        "sub_score": sub_score,
    }


async def fetch_oil_price_signal() -> dict[str, Any] | None:
    """FRED DCOILWTICO(WTI 현물유가) 20일 이동평균 대비 이격도로 유가 급변동 위험을 판단한다.

    달러 인덱스·환율 신호와 달리 방향(급등/급락) 상관없이 절대 이격도를 기준으로 삼는다 —
    유가 급등(인플레이션·지정학 리스크)과 급락(수요 위축·경기침체 우려) 모두 위험자산에
    부정적 신호로 해석하기 때문이다.
    """
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal="oil_price")
        return None
    from app.services.economic_indicator_service import _fred_get_observations, _parse_fred_obs

    try:
        obs = await fred_circuit.call(_fred_get_observations, "DCOILWTICO", limit=30)
    except (CircuitOpenError, Exception) as exc:
        logger.warning("oil_price_fetch_failed", error=str(exc))
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
    abs_deviation_pct = abs(deviation_pct)

    if abs_deviation_pct <= 5:
        level = "NORMAL"
        sub_score = 0
    elif abs_deviation_pct <= 10:
        level = "ELEVATED"
        sub_score = 1
    elif abs_deviation_pct <= 15:
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


def _inflation_bucket(yoy_pct: float) -> tuple[str, int]:
    """CPI/PCE YoY %를 Fed 목표(2%) 대비 이격도로 버킷 — 상승 이격만 리스크로 취급한다.

    디플레이션 방향(저인플레·마이너스 YoY)은 이번 스코프에서 다루지 않는다 — 통화정책이
    금리 인상으로 즉각 대응하는 상방 리스크만 우선 반영(향후 절대 이격도 방식 확장 여지 있음).
    """
    deviation = yoy_pct - 2.0
    if deviation <= 1.0:
        return "NORMAL", 0
    if deviation <= 2.0:
        return "ELEVATED", 1
    if deviation <= 3.5:
        return "HIGH", 2
    return "BREAKOUT", 3


async def fetch_cpi_inflation_signal() -> dict[str, Any] | None:
    """FRED CPIAUCSL(미국 CPI) YoY %를 Fed 목표 2% 대비 이격도로 판단한다.

    `economic_indicator_service.fetch_indicator_history`를 재사용해 `fetch_inflation_summary`와
    동일한 13개월 윈도우 YoY 산식을 그대로 적용한다(중복 구현 방지).
    """
    from app.services.economic_indicator_service import fetch_indicator_history

    points = await fetch_indicator_history("CPI_US", months=13)
    if len(points) < 13:
        return None

    yoy_pct = (points[-1]["value"] - points[-13]["value"]) / points[-13]["value"] * 100
    level, sub_score = _inflation_bucket(yoy_pct)

    return {
        "yoy_change_pct": round(yoy_pct, 2),
        "level": level,
        "date": points[-1]["date"],
        "sub_score": sub_score,
    }


async def fetch_pce_inflation_signal() -> dict[str, Any] | None:
    """FRED PCEPI(미국 PCE 물가지수) YoY %를 Fed 목표 2% 대비 이격도로 판단한다.

    CPI 신호와 동일한 산식·버킷을 사용 — `fetch_inflation_signal()`이 둘을 worst-case로 병합한다.
    """
    from app.services.economic_indicator_service import fetch_indicator_history

    points = await fetch_indicator_history("PCE_US", months=13)
    if len(points) < 13:
        return None

    yoy_pct = (points[-1]["value"] - points[-13]["value"]) / points[-13]["value"] * 100
    level, sub_score = _inflation_bucket(yoy_pct)

    return {
        "yoy_change_pct": round(yoy_pct, 2),
        "level": level,
        "date": points[-1]["date"],
        "sub_score": sub_score,
    }


async def fetch_inflation_signal() -> dict[str, Any] | None:
    """CPI(CPIAUCSL)와 PCE(PCEPI) YoY 인플레이션 신호를 하나의 신호로 병합한다.

    둘 다 "미국 인플레이션 추세"라는 동일한 정보를 반영해 함께 오르내리는 경향이 있다 —
    복합점수에 각각 더하면 같은 리스크를 이중 계상하게 된다. `fetch_us_rate_curve_signal`과
    동일한 패턴으로 sub_score는 worst-case(max)만 반영한다.
    """
    import asyncio

    cpi, pce = await asyncio.gather(fetch_cpi_inflation_signal(), fetch_pce_inflation_signal())
    if cpi is None and pce is None:
        return None

    cpi_sub = cpi["sub_score"] if cpi else 0
    pce_sub = pce["sub_score"] if pce else 0
    reference = cpi or pce
    assert reference is not None  # nosec B101 - 위에서 둘 다 None인 경우는 이미 반환됨

    return {
        "cpi_yoy_pct": cpi["yoy_change_pct"] if cpi else None,
        "cpi_level": cpi["level"] if cpi else None,
        "pce_yoy_pct": pce["yoy_change_pct"] if pce else None,
        "pce_level": pce["level"] if pce else None,
        "sub_score": max(cpi_sub, pce_sub),
        "date": reference["date"],
    }


async def fetch_employment_signal() -> dict[str, Any] | None:
    """FRED UNRATE(미국 실업률)로 Sahm Rule의 단순화 버전을 계산한다.

    Sahm Rule: 3개월 평균 실업률이 과거 12개월 최저치 대비 0.5%p 이상 상승하면 경기침체 신호로
    본다 — 실증적으로 가장 신뢰도 높은 경기침체 선행지표 중 하나로 꼽혀 VIX·하이일드 스프레드와
    같은 Tier A(상한 4)로 분류한다. 여기서는 3개월 평균 대신 최신 관측치를 그대로 사용하는
    단순화 버전을 적용한다(월간 지표라 3개월 평균과의 차이가 크지 않음).
    """
    if not fred_circuit.is_available():
        logger.warning("fred_circuit_open", signal="employment")
        return None
    from app.services.economic_indicator_service import _fred_get_observations, _parse_fred_obs

    try:
        obs = await fred_circuit.call(_fred_get_observations, "UNRATE", limit=13)
    except (CircuitOpenError, Exception) as exc:
        logger.warning("employment_fetch_failed", error=str(exc))
        return None

    points = _parse_fred_obs(obs)
    if len(points) < 13:
        return None

    latest = points[-1]
    trailing_12mo_low = min(p["value"] for p in points[-13:-1])
    rise_from_low_pp = latest["value"] - trailing_12mo_low

    if rise_from_low_pp < 0.3:
        level = "NORMAL"
        sub_score = 0
    elif rise_from_low_pp < 0.5:
        level = "WATCH"
        sub_score = 1
    elif rise_from_low_pp < 1.0:
        level = "SAHM_TRIGGERED"
        sub_score = 2
    else:
        level = "HIGH"
        sub_score = 4

    return {
        "value": latest["value"],
        "trailing_12mo_low": round(trailing_12mo_low, 2),
        "rise_from_low_pp": round(rise_from_low_pp, 2),
        "level": level,
        "date": latest["date"],
        "sub_score": sub_score,
    }


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
