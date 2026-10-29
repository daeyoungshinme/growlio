"""눌림목(웅덩이) 현금 투입 — 상승 추세가 살아 있는 동안 QQQ가 60·120일선까지 눌리면 현금 일부를 주식으로 옮긴다.

웅덩이매매법(20→60→120일선 터치·RSI 과매도에서 단계적으로 더 크게 분할매수)을 국면 규칙 위에 얹은 것이다.
국면 규칙은 추세추종(200일선 이탈 시 현금 확대)이라 방향이 반대이므로 다음으로 조화시킨다:
- 확정 국면이 **공격(RISK_ON)일 때만** 투입하고, 중립·방어·미확정이면 단계를 0으로 되돌린다 — 추세 방어가 항상 우선.
  백테스트(2026-10-25, 기본 비중표·틸트 10%p, 이동폭 20%p): 공격 국면 한정 10년 CAGR 13.56→13.86·샤프 1.019→1.017·
  MDD 19.3→19.9, 20년 CAGR 10.48→10.79·샤프 .837→.843·MDD 28.3→28.2. 중립 국면까지 투입하면 샤프가 10년 .99·20년 .83으로
  나빠졌다(중립 국면의 눌림은 더 깊어지는 경우가 많음). 효과가 작아 기본은 끔(이동폭 0).
- 투입 단계는 60일선=1, 120일선=2, 120일선+RSI<35=3(20일선 눌림은 너무 잦아 표시만). 한 웅덩이 안에서는 단계가
  올라가기만 한다(래칫) — 매일 이평선 위아래를 오가며 매매가 반복되는 것을 막는다.
- 웅덩이 종료: `DIP_EXIT_STAGES`(종가가 이평선 위로 회복)면 0으로 돌아가 투입분을 현금으로 되돌린다.

투입량 = `dip_shift_pct × 단계/3`(%p), 현금을 넘지 않으며 주식 자산들에 기존 비율대로 나눈다. 순수 함수만 둔다 —
상태 갱신은 tactical_allocation_service, 과거 재현은 tactical_backtest.
"""

from __future__ import annotations

from app.services.market_signal.technical_indicators import PullbackStage

DIP_MAX_LEVEL = 3
MAX_DIP_SHIFT_PCT = 30.0
DEFAULT_DIP_SHIFT_PCT = 0.0

_STAGE_LEVEL: dict[str, int] = {"SMA60": 1, "SMA120": 2, "SMA120_RSI": 3}
# 이 단계로 회복하면 웅덩이 종료(투입분 회수)
DIP_EXIT_STAGES: frozenset[str] = frozenset({"NONE"})
ACTIVE_REGIMES = frozenset({"RISK_ON"})

DIP_LEVEL_LABELS: dict[int, str] = {0: "투입 없음", 1: "60일선 웅덩이", 2: "120일선 웅덩이", 3: "120일선+RSI 과매도"}
PULLBACK_LABELS: dict[str, str] = {
    "NONE": "웅덩이 없음",
    "SMA20": "20일선 눌림",
    "SMA60": "60일선 웅덩이",
    "SMA120": "120일선 웅덩이",
    "SMA120_RSI": "120일선+RSI 과매도",
    "UNKNOWN": "확인 불가",
}


def level_of(stage: str | None) -> int:
    return _STAGE_LEVEL.get(stage or "", 0)


def advance_dip_level(
    prev: int,
    stage: PullbackStage | str | None,
    regime: str | None,
    exit_stages: frozenset[str] = DIP_EXIT_STAGES,
) -> int:
    """다음 투입 단계. 공격 국면이 아니면 0, 시세 확인 불가면 유지, 회복이면 0, 그 외는 더 깊은 쪽으로만."""
    if regime not in ACTIVE_REGIMES:
        return 0
    if stage is None or stage == "UNKNOWN":
        return prev
    if stage in exit_stages:
        return 0
    return max(prev, level_of(stage))


def dip_amount(level: int, shift_pct: float) -> float:
    if shift_pct <= 0 or level <= 0:
        return 0.0
    return shift_pct * min(level, DIP_MAX_LEVEL) / DIP_MAX_LEVEL


def apply_dip(weights: dict[str, float], level: int, shift_pct: float) -> dict[str, float]:
    """현금에서 투입량만큼 빼 주식 자산(비중>0)에 기존 비율대로 더한다(0.1%p 단위, 합계 100 유지)."""
    out = dict(weights)
    cash = out.get("CASH", 0.0)
    equity = {a: w for a, w in out.items() if a != "CASH" and w > 0}
    total_equity = sum(equity.values())
    moved = min(dip_amount(level, shift_pct), cash)
    if moved <= 0 or total_equity <= 0:
        return out
    for asset, w in equity.items():
        out[asset] = round(w + moved * w / total_equity, 1)
    out["CASH"] = round(100.0 - sum(v for a, v in out.items() if a != "CASH"), 1)
    if out["CASH"] < 0:  # 반올림으로 현금을 넘겨 뺀 몫은 가장 큰 주식 자산에서 덜어낸다
        top = max(equity, key=lambda a: out[a])
        out[top] = round(out[top] + out["CASH"], 1)
        out["CASH"] = 0.0
    return out


def dip_reasons(
    stage: str, level: int, shift_pct: float, regime: str | None, *, deployed: float | None = None
) -> list[str]:
    """`deployed`는 제안 비중에 실제로 들어간 투입량(현금 한도 반영) — 없으면 명목 투입량."""
    reasons = [f"QQQ 웅덩이 단계: {PULLBACK_LABELS.get(stage, stage)}"]
    if shift_pct <= 0:
        return reasons
    if regime not in ACTIVE_REGIMES:
        reasons.append("웅덩이 투입은 공격 국면에서만 해요(중립·방어 국면의 눌림은 더 깊어지는 경우가 많아요).")
    elif level > 0:
        amount = dip_amount(level, shift_pct) if deployed is None else deployed
        capped = deployed is not None and deployed < dip_amount(level, shift_pct)
        reasons.append(
            f"현금 {amount:g}%p를 주식으로 옮겨요({DIP_LEVEL_LABELS[level]}"
            + (", 현금 비중 한도까지" if capped else "")
            + ")."
        )
    else:
        reasons.append("60일선까지 눌리면 현금 일부를 주식으로 옮겨요.")
    return reasons
