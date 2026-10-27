"""QQQ/SPY 틸트 — 국면(주식↔현금 총량)과 별개로, 주식 몫 안에서 나스닥(QQQ)·S&P500(SPY) 비중만 옮긴다.

매크로 복합신호는 미국 시장 전체 위험을 보므로 나스닥과 S&P를 구분하지 못한다. 나스닥 쪽에 특히 민감한 두 입력을
더 본다:
- 10년 실질금리(FRED DFII10) 20거래일 변화 — 이익이 먼 미래에 몰린 성장주(장기 듀레이션)가 할인율 상승에 가장 약하다.
- QQQ/SPY 상대강도 — 비율이 50일 평균보다 위면 나스닥이 앞서는 중.

판정(`classify_tilt`): 실질금리 +0.25%p 이상 상승 & 상대강도 50일 평균 아래 → SPY 우위, 실질금리 하락(≤0) &
상대강도 +1% 초과 → QQQ 우위, 그 외·데이터 결측 → 균형. 판정은 **월 1회**(그 달 첫 점검일)만 갱신한다 —
매일 갱신하면 백테스트 10년 틸트 변경이 130회를 넘어(매번 매매 발생) 국면 완충 효과를 상쇄했다.
백테스트 실측(10년): CAGR +0.3%p·샤프 +0.02, 20년은 MDD가 약 2.7%p 악화 — 약한 신호라 이동폭은 사용자가
0(끔)~20%p로 조절한다. 현금 이자·거래비용 반영 후(plans/70)에도 20년 MDD 24.7→27.7 악화·회전율의 약 1/3을 차지해
**기본값은 끔(0)**이다(기존 전략에 저장된 값은 유지).

순수 함수 + 입력 조회(캐시). 국면 상태 갱신은 tactical_allocation_service.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal, TypedDict

import structlog

from app.utils.cache_keys import (
    TTL_MARKET_SIGNAL_DEGRADED,
    TTL_TECHNICAL_SIGNAL,
    get_cached_json,
    set_cached_json,
    tactical_tilt_key,
)

if TYPE_CHECKING:
    import pandas as pd

    from app.core.cache_store import CacheStore

logger = structlog.get_logger()

Tilt = Literal["FAVOR_QQQ", "BALANCED", "FAVOR_SPY"]
TILTS: tuple[Tilt, ...] = ("FAVOR_QQQ", "BALANCED", "FAVOR_SPY")
TILT_LABELS: dict[str, str] = {"FAVOR_QQQ": "나스닥 우위", "BALANCED": "균형", "FAVOR_SPY": "S&P500 우위"}

DEFAULT_TILT_SHIFT_PCT = 0.0
MAX_TILT_SHIFT_PCT = 20.0

REAL_YIELD_LOOKBACK = 20  # 거래일
REAL_YIELD_RISE_PP = 0.25  # 이 이상 상승하면 성장주 역풍
RS_SMA = 50
RS_LEAD_PCT = 1.0  # 상대강도가 50일 평균 대비 이만큼 앞서야 나스닥 우위
_CLOSE_HISTORY_DAYS = 120  # RS 50일선 계산용 달력일


class TiltInputs(TypedDict):
    real_yield: float | None  # 최신 10년 실질금리(%)
    real_yield_change_pp: float | None  # 20거래일 변화(%p)
    relative_strength_pct: float | None  # QQQ/SPY 비율의 50일 평균 대비 이격(%)


def classify_tilt(real_yield_change_pp: float | None, relative_strength_pct: float | None) -> Tilt:
    if real_yield_change_pp is None or relative_strength_pct is None:
        return "BALANCED"
    if real_yield_change_pp >= REAL_YIELD_RISE_PP and relative_strength_pct < 0:
        return "FAVOR_SPY"
    if real_yield_change_pp <= 0 and relative_strength_pct > RS_LEAD_PCT:
        return "FAVOR_QQQ"
    return "BALANCED"


def tilt_reasons(inputs: TiltInputs, tilt: Tilt) -> list[str]:
    ry, chg, rs = inputs["real_yield"], inputs["real_yield_change_pp"], inputs["relative_strength_pct"]
    ry_text = "확인 불가" if ry is None or chg is None else f"{ry:.2f}% (20거래일 {chg:+.2f}%p)"
    rs_text = "확인 불가" if rs is None else f"50일 평균 대비 {rs:+.1f}%"
    return [
        f"미국 10년 실질금리: {ry_text}",
        f"QQQ/SPY 상대강도: {rs_text}",
        f"나스닥·S&P 비중 판단: {TILT_LABELS[tilt]} (매월 첫 점검일에 갱신)",
    ]


def apply_tilt(weights: dict[str, float], tilt: str | None, shift_pct: float) -> dict[str, float]:
    """주식 몫 안에서 QQQ↔SPY로 `shift_pct`%p를 옮긴다. 줄어드는 쪽은 0 아래로 내려가지 않고 현금·합계는 그대로."""
    out = dict(weights)
    if shift_pct <= 0 or tilt not in ("FAVOR_QQQ", "FAVOR_SPY"):
        return out
    src, dst = ("SPY", "QQQ") if tilt == "FAVOR_QQQ" else ("QQQ", "SPY")
    moved = min(shift_pct, out.get(src, 0.0))
    out[src] = out.get(src, 0.0) - moved
    out[dst] = out.get(dst, 0.0) + moved
    return out


def is_new_month(last_evaluated: date | None, today: date) -> bool:
    return last_evaluated is None or (last_evaluated.year, last_evaluated.month) != (today.year, today.month)


def relative_strength_pct(qqq: pd.Series, spy: pd.Series) -> float | None:
    ratio = (qqq / spy).dropna()
    if len(ratio) < RS_SMA:
        return None
    avg = float(ratio.iloc[-RS_SMA:].mean())
    if avg <= 0:
        return None
    return float((ratio.iloc[-1] / avg - 1) * 100)


def real_yield_change(values: list[float]) -> float | None:
    if len(values) <= REAL_YIELD_LOOKBACK:
        return None
    return values[-1] - values[-1 - REAL_YIELD_LOOKBACK]


async def _fetch_real_yields() -> list[float]:
    from app.services.economic_indicator_service import fred_get_observations, parse_fred_obs
    from app.utils.circuit_breaker import fred_circuit

    if not fred_circuit.is_available():
        return []
    raw = await fred_circuit.call(fred_get_observations, "DFII10", limit=REAL_YIELD_LOOKBACK + 15)
    return [p["value"] for p in parse_fred_obs(raw)]


async def get_tilt_inputs(cache: CacheStore | None) -> TiltInputs:
    key = tactical_tilt_key()
    if cached := await get_cached_json(cache, key):
        return cached

    from app.services.technical_signal_service import fetch_close_history

    try:
        yields = await _fetch_real_yields()
    except Exception as exc:
        logger.warning("tactical_tilt_real_yield_failed", error=str(exc))
        yields = []
    try:
        closes = await fetch_close_history(["QQQ", "SPY"], _CLOSE_HISTORY_DAYS)
        rs = relative_strength_pct(closes["QQQ"], closes["SPY"]) if {"QQQ", "SPY"} <= set(closes) else None
    except Exception as exc:
        logger.warning("tactical_tilt_closes_failed", error=str(exc))
        rs = None

    result = TiltInputs(
        real_yield=yields[-1] if yields else None,
        real_yield_change_pp=real_yield_change(yields),
        relative_strength_pct=rs,
    )
    # 부분 실패는 짧게만 캐시해 곧 재시도한다 — 아예 캐시하지 않으면 FRED 장애·키 미설정 동안 전술 탭 조회마다
    # FRED·Yahoo를 다시 호출해 응답이 매번 외부 타임아웃만큼 늘어졌다
    complete = all(v is not None for v in result.values())
    await set_cached_json(cache, key, result, TTL_TECHNICAL_SIGNAL if complete else TTL_MARKET_SIGNAL_DEGRADED)
    return result
