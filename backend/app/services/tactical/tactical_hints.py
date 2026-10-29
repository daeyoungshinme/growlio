"""전술 배분 국면 전환 조건까지의 거리 — "지금 국면이 무엇 때문에, 얼마나 더 움직이면 바뀌는지" 안내문.

`classify_regime`(매크로 RED·SPY DOWN → 방어, SPY·QQQ UP + 매크로 GREEN → 공격, 공격 국면은 YELLOW까지 유지)과
`classify_trend`(200일선 ±`TREND_BAND_PCT` 완충 + 50/200일선 교차)를 거꾸로 풀어 다음 전환 후보까지 남은 조건을
문장으로 만든다. 오늘 스냅샷의 추세를 직전 상태로 보고 완충을 적용한다. 순수 함수만 둔다(I/O 없음).

확정은 별도 — 조건이 충족돼도 다음 거래일에 한 번 더 관측돼야 국면이 바뀐다(`step_confirmation`).
화면이 이 안내를 덧붙인다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypedDict

from app.services.market_signal.technical_indicators import TREND_BAND_PCT

HintKind = Literal["TO_RISK_OFF", "TO_NEUTRAL", "TO_RISK_ON"]


class TransitionHint(TypedDict):
    kind: HintKind
    text: str
    distance_pct: float | None  # 종가 기준 필요한 가격 변동(%) — 음수면 하락. 가격 조건이 아니면 None


def _num(snap: Mapping[str, Any] | None, key: str) -> float | None:
    v = snap.get(key) if snap else None
    return float(v) if isinstance(v, int | float) else None


def _move_pct(close: float, target: float) -> float:
    """종가에서 `target`까지의 변동률(%) — 소수 1자리."""
    return round((target / close - 1) * 100, 1)


def _exit_up(ticker: str, snap: Mapping[str, Any] | None) -> TransitionHint | None:
    """추세 UP 종목이 UP을 잃는 가격(200일선 −완충) 까지 거리."""
    close, s200 = _num(snap, "close"), _num(snap, "sma200")
    if close is None or s200 is None or close <= 0:
        return None
    move = _move_pct(close, s200 * (1 - TREND_BAND_PCT / 100))
    return {
        "kind": "TO_NEUTRAL",
        "text": f"{ticker}가 {abs(move):g}% 더 내려 200일선 아래(−{TREND_BAND_PCT:g}%)로 가면 중립 전환 후보",
        "distance_pct": move,
    }


def _to_up(ticker: str, snap: Mapping[str, Any] | None) -> str | None:
    """추세가 UP이 아닌 종목이 UP이 되려면 필요한 조건 문장."""
    close, s50, s200 = _num(snap, "close"), _num(snap, "sma50"), _num(snap, "sma200")
    if close is None or s50 is None or s200 is None or close <= 0 or s200 <= 0:
        return None
    if s50 <= s200:
        gap = round((s200 / s50 - 1) * 100, 1)
        return f"{ticker} 50일선이 200일선 위로 올라서야 해요(현재 {gap:g}% 아래)"
    if close <= s200:
        return f"{ticker}가 {_move_pct(close, s200):g}% 올라 200일선 위로 가야 해요"
    return None


def _spy_down_hint(snap: Mapping[str, Any] | None) -> TransitionHint | None:
    """SPY가 아직 DOWN이 아닐 때 방어 후보(SPY DOWN)까지의 조건."""
    close, s50, s200 = _num(snap, "close"), _num(snap, "sma50"), _num(snap, "sma200")
    if close is None or s50 is None or s200 is None or close <= 0 or s200 <= 0:
        return None
    if s50 < s200:  # 교차는 이미 하락 쪽 — 종가만 200일선 아래로 가면 된다
        move = _move_pct(close, s200)
        return {
            "kind": "TO_RISK_OFF",
            "text": f"SPY가 {abs(move):g}% 더 내려 200일선 아래로 가면 방어 전환 후보",
            "distance_pct": move,
        }
    gap = round((s50 / s200 - 1) * 100, 1)
    return {
        "kind": "TO_RISK_OFF",
        "text": f"SPY 50일선이 200일선 아래로 내려가고(현재 {gap:g}% 위) 종가도 200일선 아래면 방어 전환 후보",
        "distance_pct": None,
    }


def _spy_recover_hint(snap: Mapping[str, Any] | None) -> TransitionHint | None:
    """SPY DOWN이 풀리는 가격(200일선 +완충) 까지 거리."""
    close, s200 = _num(snap, "close"), _num(snap, "sma200")
    if close is None or s200 is None or close <= 0:
        return None
    move = _move_pct(close, s200 * (1 + TREND_BAND_PCT / 100))
    return {
        "kind": "TO_NEUTRAL",
        "text": f"SPY가 {move:g}% 올라 200일선 위(+{TREND_BAND_PCT:g}%)로 가면 하락 추세 해제",
        "distance_pct": move,
    }


def transition_hints(
    regime: str | None,
    macro_level: str,
    macro_freshness: str,
    technicals: Mapping[str, Mapping[str, Any]],
    *,
    use_macro: bool = True,
) -> list[TransitionHint]:
    """현재(확정, 없으면 관측) 국면에서 다음 전환 후보까지 남은 조건 — 가까운(중요한) 순. 판정 불가면 빈 목록.

    `use_macro=False`(매크로 반영 끔)면 매크로 조건은 늘 충족된 것으로 보고 매크로 관련 안내를 뺀다.
    """
    if not use_macro:
        macro_level, macro_freshness = "GREEN", "LIVE"
    spy, qqq = technicals.get("SPY"), technicals.get("QQQ")
    spy_trend = spy.get("trend", "UNKNOWN") if spy else "UNKNOWN"
    qqq_trend = qqq.get("trend", "UNKNOWN") if qqq else "UNKNOWN"
    if regime is None or spy_trend == "UNKNOWN":
        return []
    macro_red_now = macro_level == "RED" and macro_freshness != "STALE"
    hints: list[TransitionHint] = []

    if regime == "RISK_OFF":
        if macro_red_now:
            hints.append({"kind": "TO_NEUTRAL", "text": "매크로 '위험' 등급이 풀려야 해요", "distance_pct": None})
        if spy_trend == "DOWN" and (h := _spy_recover_hint(spy)):
            hints.append(h)
        return hints

    macro_red: TransitionHint = {
        "kind": "TO_RISK_OFF",
        "text": "매크로가 '위험' 등급이 되면 바로 방어 전환 후보",
        "distance_pct": None,
    }
    if regime == "RISK_ON":
        # 공격 국면은 SPY·QQQ 중 하나라도 UP을 잃으면 중립 후보 — 더 가까운 쪽만 보여준다
        exits = [
            h
            for t, snap, tr in (("SPY", spy, spy_trend), ("QQQ", qqq, qqq_trend))
            if tr == "UP" and (h := _exit_up(t, snap)) is not None
        ]
        exits.sort(key=lambda h: abs(h["distance_pct"] or 0))
        return [*exits[:1], macro_red] if use_macro else exits[:1]

    # NEUTRAL — 공격 진입에 빠진 조건 + 방어 후보까지
    missing = [
        text
        for t, snap, tr in (("SPY", spy, spy_trend), ("QQQ", qqq, qqq_trend))
        if tr != "UP" and (text := _to_up(t, snap))
    ]
    if macro_level != "GREEN" or macro_freshness == "STALE":
        stale_note = " (지표 데이터 지연 중)" if macro_freshness == "STALE" else ""
        missing.append(f"매크로가 '안정' 등급이어야 해요{stale_note}")
    if missing:
        hints.append({"kind": "TO_RISK_ON", "text": "공격 전환 조건: " + " · ".join(missing), "distance_pct": None})
    if spy_trend != "DOWN" and (h := _spy_down_hint(spy)):
        hints.append(h)
    if use_macro:
        hints.append(macro_red)
    return hints
