"""리밸런싱 시점 판정(순수, plans/136) — 진단 탭 포트폴리오 행의 "지금 실행 / 분할 / 보류 / 지켜보기 / 안정".

판정은 이탈 여부(`filter_drifting_items`와 같은 기준)를 먼저 보고, 이탈이면 시장 상황을 겹친다.
- 보류(HOLD): 이 포트폴리오의 AUTO 알림 시장 게이트가 지금 막는 상태(`is_market_signal_blocking_auto_mode`
  결과를 호출부가 넘긴다 — 자동 실행과 화면 문구가 어긋나지 않게), 게이트가 없으면 **확정** 등급 RED.
- 분할(SPLIT): 확정 등급 YELLOW. 지금(NOW): 그 외.
- 이탈이 아니면 기준선의 절반 이상 다가간 경우 지켜보기(WATCH), 아니면 안정(OK).

비용(해외 양도세 추정)은 판정을 바꾸지 않고 사유에만 덧붙인다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Timing = Literal["NOW", "SPLIT", "HOLD", "WATCH", "OK"]

WATCH_PROGRESS = 0.5
"""기준선의 이 비율 이상 다가가면 지켜보기 — 프론트 `getDriftStatus`의 "주의"(절반 이상)와 같다."""

_GATE_LABEL: dict[str, str] = {
    "CAUTIOUS": "시장 위험(RED) 시 보류",
    "STRICT": "시장 주의(YELLOW) 이상 시 보류",
    "TACTICAL": "전술 방어 국면 시 매수 보류",
}


@dataclass(frozen=True)
class TimingVerdict:
    timing: Timing
    reason: str


def _rule_text(threshold_pct: float, relative_threshold_pct: float | None) -> str:
    text = f"기준 ±{threshold_pct:g}%p"
    if relative_threshold_pct:
        text += f"·목표 대비 {relative_threshold_pct:g}%"
    return text


def decide_timing(
    *,
    needs_rebalancing: bool,
    drift_progress: float,
    max_drift_pct: float,
    threshold_pct: float,
    relative_threshold_pct: float | None,
    confirmed_level: str | None,
    market_stale: bool,
    gate_blocked_mode: str | None,
    estimated_overseas_tax_krw: float = 0.0,
) -> TimingVerdict:
    """`gate_blocked_mode`는 지금 게이트에 막힌 AUTO 알림의 `market_condition_mode`(막힌 게 없으면 None)."""
    drift_text = f"최대 {max_drift_pct:.1f}%p 이탈({_rule_text(threshold_pct, relative_threshold_pct)})"

    if not needs_rebalancing:
        if drift_progress >= WATCH_PROGRESS:
            return TimingVerdict("WATCH", f"{drift_text} — 기준의 절반을 넘어 지켜볼 단계예요")
        return TimingVerdict("OK", "목표 비중 근처예요 — 지금은 할 일이 없어요")

    tax_suffix = (
        f" 해외 매도로 양도세 약 {estimated_overseas_tax_krw:,.0f}원이 예상돼요."
        if estimated_overseas_tax_krw > 0
        else ""
    )

    if gate_blocked_mode is not None:
        gate = _GATE_LABEL.get(gate_blocked_mode, "시장 조건")
        if market_stale and gate_blocked_mode != "TACTICAL":
            reason = f"{drift_text} — 시장 신호를 확인할 수 없어 자동 실행이 보류 중이에요({gate})."
        else:
            reason = f"{drift_text} — 자동 실행 시장 조건({gate})에 걸려 보류 중이에요."
        return TimingVerdict("HOLD", reason + tax_suffix)

    if confirmed_level == "RED":
        return TimingVerdict(
            "HOLD",
            f"{drift_text} — 시장 위험(RED) 단계라 급하지 않다면 기다리는 편이 좋아요." + tax_suffix,
        )
    if confirmed_level == "YELLOW":
        return TimingVerdict(
            "SPLIT",
            f"{drift_text} — 시장 주의(YELLOW) 단계라 나눠서 실행하길 권해요." + tax_suffix,
        )
    stale_note = " 시장 신호는 확인하지 못했어요." if market_stale else ""
    return TimingVerdict("NOW", f"{drift_text} — 지금 리밸런싱하기 좋은 때예요.{stale_note}" + tax_suffix)
