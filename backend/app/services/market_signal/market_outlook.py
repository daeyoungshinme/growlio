"""시장 종합 판단 — 매크로 위험 등급 × 3대 지수(나스닥100·S&P500·다우) 추세 (plans/137 B, 순수 함수).

**표시 전용이다.** 자동 실행 게이트(`order_builder.is_market_signal_blocking_auto_mode`)와 전술 국면
(`tactical_regime.classify_regime`)은 이 판단을 쓰지 않는다 — 게이트는 확정 매크로 등급, 전술은 확정 등급과
QQQ·SPY 추세로 따로 판정한다. 여기서는 즉시(raw) 매크로 등급과 DIA까지 포함한 추세 폭을 엮어 "지금 시장을 어떻게
볼지" 한 줄로 요약할 뿐이다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

Verdict = Literal["FAVORABLE", "STEADY", "CAUTION", "DEFENSIVE", "UNKNOWN"]
TrendClass = Literal["UP", "MIXED", "DOWN"]

OUTLOOK_TICKERS: tuple[str, ...] = ("QQQ", "SPY", "DIA")
INDEX_NAMES: dict[str, str] = {"QQQ": "나스닥100", "SPY": "S&P500", "DIA": "다우"}
VERDICT_LABELS: dict[Verdict, str] = {
    "FAVORABLE": "우호",
    "STEADY": "신중",
    "CAUTION": "경계",
    "DEFENSIVE": "방어",
    "UNKNOWN": "판단 보류",
}
_TREND_WORDS = {"UP": "상승", "NEUTRAL": "혼조", "DOWN": "하락", "UNKNOWN": "확인 불가"}
_MACRO_WORDS = {"GREEN": "낮음", "YELLOW": "주의", "RED": "높음"}

# (매크로 등급, 추세 분류) → (판단, 행동 문구)
_MATRIX: dict[tuple[str, TrendClass], tuple[Verdict, str]] = {
    ("GREEN", "UP"): ("FAVORABLE", "계획대로 진행해도 좋은 환경이에요"),
    ("GREEN", "MIXED"): ("STEADY", "계획대로 하되 분할 집행을 고려하세요"),
    ("GREEN", "DOWN"): ("STEADY", "매크로는 안정적이지만 추세가 약해요 — 분할 집행"),
    ("YELLOW", "UP"): ("STEADY", "추세는 살아 있지만 매크로가 흔들려요 — 분할 집행"),
    ("YELLOW", "MIXED"): ("CAUTION", "매수 속도를 늦추고 나눠서 진행하세요"),
    ("YELLOW", "DOWN"): ("CAUTION", "매수 속도를 늦추고 나눠서 진행하세요"),
    ("RED", "UP"): ("CAUTION", "추세는 유지되지만 위험 신호가 커요 — 레버리지 추가는 자제"),
    ("RED", "MIXED"): ("DEFENSIVE", "위험 신호와 약한 추세 — 포지션을 점검하세요"),
    ("RED", "DOWN"): ("DEFENSIVE", "위험 신호와 하락 추세 — 포지션을 점검하세요"),
}
# 매크로를 못 볼 때(STALE) 추세만으로
_TREND_ONLY: dict[TrendClass, tuple[Verdict, str]] = {
    "UP": ("STEADY", "추세는 상승이지만 매크로 데이터가 없어요 — 분할 집행"),
    "MIXED": ("STEADY", "추세가 엇갈리고 매크로 데이터가 없어요 — 분할 집행"),
    "DOWN": ("CAUTION", "추세가 하락이고 매크로 데이터가 없어요 — 매수 속도 조절"),
}
_CORRECTION_PCT = -10.0
_BEAR_PCT = -20.0
_MIN_KNOWN_TRENDS = 2


def classify_breadth(trends: Mapping[str, str]) -> tuple[TrendClass | None, int, int]:
    """판정 가능한 지수 중 과반이 상승이면 UP, 과반이 하락이면 DOWN, 나머지는 MIXED.

    Returns: (분류 — 판정 가능 지수가 2개 미만이면 None, 상승 수, 판정 가능 수)
    """
    known = [t for t in trends.values() if t in ("UP", "NEUTRAL", "DOWN")]
    up = sum(1 for t in known if t == "UP")
    down = sum(1 for t in known if t == "DOWN")
    if len(known) < _MIN_KNOWN_TRENDS:
        return None, up, len(known)
    if up * 2 > len(known):
        return "UP", up, len(known)
    if down * 2 > len(known):
        return "DOWN", up, len(known)
    return "MIXED", up, len(known)


def build_market_outlook(signal: Mapping[str, Any], technicals: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """즉시 매크로 신호(`get_market_signal`)와 차트 지표(`get_technical_signals`)로 종합 판단을 만든다."""
    freshness = signal.get("data_freshness")
    macro_level = signal.get("composite_level") if freshness != "STALE" else None
    trends = {t: str((technicals.get(t) or {}).get("trend") or "UNKNOWN") for t in OUTLOOK_TICKERS}
    breadth, up, known = classify_breadth(trends)

    reasons: list[str] = []
    if macro_level in _MACRO_WORDS:
        score = signal.get("composite_score")
        score_max = signal.get("composite_score_max")
        score_text = f" ({score}/{score_max})" if score is not None and score_max else ""
        reasons.append(f"매크로 위험 {_MACRO_WORDS[macro_level]}{score_text}")
    else:
        reasons.append("매크로 데이터를 받지 못했어요")

    trend_text = " · ".join(f"{INDEX_NAMES[t]} {_TREND_WORDS.get(trends[t], '확인 불가')}" for t in OUTLOOK_TICKERS)
    if breadth is None:
        reasons.append(f"추세 확인 불가 ({trend_text})")
    else:
        reasons.append(f"추세 상승 {up}/{known} ({trend_text})")

    deepest_ticker: str | None = None
    deepest: float | None = None
    for t in OUTLOOK_TICKERS:
        dd = (technicals.get(t) or {}).get("drawdown_pct")
        if dd is not None and (deepest is None or dd < deepest):
            deepest, deepest_ticker = float(dd), t
    if deepest is not None and deepest_ticker is not None:
        if deepest <= _BEAR_PCT:
            reasons.append(f"{INDEX_NAMES[deepest_ticker]} 52주 고점 대비 {deepest:.1f}% — 약세장 수준 조정")
        elif deepest <= _CORRECTION_PCT:
            reasons.append(f"{INDEX_NAMES[deepest_ticker]} 52주 고점 대비 {deepest:.1f}% — 조정 구간")

    verdict: Verdict
    if macro_level in _MACRO_WORDS:
        # 추세를 못 보면 매크로만으로 — 혼조 칸과 같다
        verdict, action = _MATRIX[(macro_level, breadth or "MIXED")]
    elif breadth is not None:
        verdict, action = _TREND_ONLY[breadth]
    else:
        verdict, action = "UNKNOWN", "시장 데이터를 받지 못했어요"

    return {
        "verdict": verdict,
        "label": VERDICT_LABELS[verdict],
        "action": action,
        "macro_level": macro_level,
        "trend_breadth": breadth,
        "trend_up_count": up,
        "trend_known_count": known,
        "trends": trends,
        "deepest_drawdown_pct": round(deepest, 2) if deepest is not None else None,
        "reasons": reasons,
    }
