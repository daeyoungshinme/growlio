"""낙폭 추매 안내 계산(순수) — 여윳돈을 지수 낙폭 구간별 비율로 나눈다(plans/147).

- 구간은 낙폭 오름차순 `[{"drawdown_pct": 10, "ratio_pct": 20}, …]`. 낙폭이 `-drawdown_pct` 이하면 도달.
- 한 하락 사이클에서 구간마다 한 번만 — 완료한 구간은 다시 안내하지 않는다. 한 번에 여러 구간을 건너뛰면 합산.
- 금액 = 미완료 도달 구간 비율 합 × 기준액. 기준액은 사이클 첫 추매 때 고정한 `cycle_base_krw`(없으면 현재
  여윳돈) — 추매로 잔액이 줄어도 다음 구간 금액이 같은 기준으로 나온다. 남은 여윳돈을 넘지 않는다.
- 지수가 고점 대비 `RESET_DRAWDOWN_PCT` 이내로 회복하면 사이클 종료(완료 기록·기준액 초기화).

plans/147 백테스트: 적립금을 줄여 모은 돈으로 추매하면 매달 전액 적립보다 IRR이 낮았다. 이 안내는 적립과
별개인 여윳돈 전제다.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, TypedDict

RESET_DRAWDOWN_PCT = 3.0
DIP_BUY_INDEX_TICKERS: tuple[str, ...] = ("QQQ", "SPY")
DEFAULT_TIERS: list[dict[str, float]] = [
    {"drawdown_pct": 10.0, "ratio_pct": 20.0},
    {"drawdown_pct": 20.0, "ratio_pct": 30.0},
    {"drawdown_pct": 30.0, "ratio_pct": 50.0},
]

TierState = Literal["DONE", "DUE", "WAITING"]


class TierStatus(TypedDict):
    tier: int
    drawdown_pct: float
    ratio_pct: float
    amount_krw: float
    state: TierState
    done_amount_krw: float | None


def completed_tiers(completed: Sequence[dict] | None) -> set[int]:
    return {int(c["tier"]) for c in completed or [] if "tier" in c}


def reached(tier: dict, drawdown_pct: float | None) -> bool:
    return drawdown_pct is not None and drawdown_pct <= -float(tier["drawdown_pct"])


def base_amount(reserve_krw: float, cycle_base_krw: float | None) -> float:
    return float(cycle_base_krw) if cycle_base_krw else float(reserve_krw)


def tier_statuses(
    tiers: Sequence[dict],
    completed: Sequence[dict] | None,
    drawdown_pct: float | None,
    reserve_krw: float,
    cycle_base_krw: float | None,
) -> list[TierStatus]:
    done = {int(c["tier"]): float(c.get("amount_krw") or 0) for c in completed or [] if "tier" in c}
    base = base_amount(reserve_krw, cycle_base_krw)
    out: list[TierStatus] = []
    for i, tier in enumerate(tiers):
        state: TierState = "DONE" if i in done else ("DUE" if reached(tier, drawdown_pct) else "WAITING")
        out.append(
            TierStatus(
                tier=i,
                drawdown_pct=float(tier["drawdown_pct"]),
                ratio_pct=float(tier["ratio_pct"]),
                amount_krw=round(base * float(tier["ratio_pct"]) / 100, 0),
                state=state,
                done_amount_krw=done.get(i),
            )
        )
    return out


def due_tiers(statuses: Sequence[TierStatus]) -> list[int]:
    return [s["tier"] for s in statuses if s["state"] == "DUE"]


def due_amount(statuses: Sequence[TierStatus], reserve_krw: float) -> float:
    """미완료 도달 구간 금액 합 — 남은 여윳돈을 넘지 않는다."""
    total = sum(s["amount_krw"] for s in statuses if s["state"] == "DUE")
    return round(max(0.0, min(total, float(reserve_krw))), 0)


def should_reset(drawdown_pct: float | None, completed: Sequence[dict] | None, cycle_base_krw: float | None) -> bool:
    """고점 근처로 회복했고 지울 사이클 기록이 있으면 True. 낙폭을 모르면 건드리지 않는다."""
    if drawdown_pct is None:
        return False
    if not completed and not cycle_base_krw:
        return False
    return drawdown_pct > -RESET_DRAWDOWN_PCT


def validate_tiers(tiers: Sequence[dict]) -> str | None:
    """구간 검증 — 오류 문구(한국어) 또는 None. 스키마 검증과 서비스가 같이 쓴다."""
    if not 1 <= len(tiers) <= 3:
        return "추매 구간은 1~3개로 정해주세요."
    prev_dd = 0.0
    total = 0.0
    for tier in tiers:
        dd = float(tier.get("drawdown_pct", 0))
        ratio = float(tier.get("ratio_pct", 0))
        if not 1 <= dd <= 60:
            return "낙폭은 1~60% 사이로 정해주세요."
        if dd <= prev_dd:
            return "구간 낙폭은 얕은 것부터 깊은 순서로, 서로 다르게 정해주세요."
        if not 1 <= ratio <= 100:
            return "구간 비율은 1~100% 사이로 정해주세요."
        prev_dd = dd
        total += ratio
    if total > 100 + 1e-9:
        return "구간 비율 합계는 100%를 넘을 수 없어요."
    return None
