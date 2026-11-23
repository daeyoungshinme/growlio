"""낙폭 추매 안내 계산(순수) — 여윳돈을 지수별 규칙 몫으로 나누고, 그 몫을 낙폭 구간별 비율로 나눈다(plans/147·148).

- 여윳돈은 사용자당 하나. 규칙(지수)마다 배분 비율(`allocation_pct`, 합 ≤100)을 갖는다.
- 규칙 몫 = 여윳돈 풀 × 배분%. 풀 = 남은 여윳돈 + 진행 중 사이클들에서 이미 추매한 금액 — 한 규칙의 추매로
  다른 규칙의 몫이 줄지 않는다. 사이클 첫 추매 때 그 규칙 몫을 `cycle_base_krw`로 고정한다.
- 구간은 낙폭 오름차순 `[{"drawdown_pct": 10, "ratio_pct": 20}, …]`. 낙폭이 `-drawdown_pct` 이하면 도달.
  한 하락 사이클에서 구간마다 한 번만 — 한 번에 여러 구간을 건너뛰면 합산.
- 안내 금액은 규칙 남은 몫과 남은 여윳돈을 넘지 않는다(동시 발동이면 규칙 순서대로 여윳돈을 차감).
- 지수가 고점 대비 `RESET_DRAWDOWN_PCT` 이내로 회복하면 그 규칙의 사이클 종료(완료 기록·기준액·알림 기록 초기화).

plans/147 백테스트: 적립금을 줄여 모은 돈으로 추매하면 매달 전액 적립보다 IRR이 낮았다. 이 안내는 적립과
별개인 여윳돈 전제다.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Iterable, Sequence
from datetime import date, timedelta
from typing import Literal, TypedDict

RESET_DRAWDOWN_PCT = 3.0
DIP_BUY_INDEX_TICKERS: tuple[str, ...] = ("QQQ", "SPY")
# 규칙 지수 → 추천 후보 ETF의 추종 지수 키(`etf_index_classifier`·`recommendation_universe`와 같은 키)
INDEX_KEY_BY_TICKER: dict[str, str] = {"QQQ": "US_NASDAQ100", "SPY": "US_SP500"}
INDEX_LABEL: dict[str, str] = {"QQQ": "나스닥100", "SPY": "S&P500"}
NOTIFY_MODES: tuple[str, ...] = ("ON_REACH", "MONTHLY_DAY")
NOTIFY_DAY_RANGE = (1, 28)
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


def cycle_spent(completed: Sequence[dict] | None) -> float:
    """이번 사이클에 이미 추매한 금액."""
    return sum(float(c.get("amount_krw") or 0) for c in completed or [])


def reached(tier: dict, drawdown_pct: float | None) -> bool:
    return drawdown_pct is not None and drawdown_pct <= -float(tier["drawdown_pct"])


def reserve_pool(reserve_krw: float, completed_lists: Iterable[Sequence[dict] | None]) -> float:
    """배분 기준 풀 = 남은 여윳돈 + 진행 중 사이클들의 추매액(추매로 줄어든 만큼 되돌려 본다)."""
    return float(reserve_krw) + sum(cycle_spent(c) for c in completed_lists)


def rule_base(pool_krw: float, allocation_pct: float, cycle_base_krw: float | None) -> float:
    """규칙 몫 — 사이클 중이면 고정한 기준액, 아니면 풀 × 배분%."""
    if cycle_base_krw:
        return float(cycle_base_krw)
    return round(float(pool_krw) * float(allocation_pct) / 100, 0)


def tier_statuses(
    tiers: Sequence[dict],
    completed: Sequence[dict] | None,
    drawdown_pct: float | None,
    base_krw: float,
) -> list[TierStatus]:
    done = {int(c["tier"]): float(c.get("amount_krw") or 0) for c in completed or [] if "tier" in c}
    out: list[TierStatus] = []
    for i, tier in enumerate(tiers):
        state: TierState = "DONE" if i in done else ("DUE" if reached(tier, drawdown_pct) else "WAITING")
        out.append(
            TierStatus(
                tier=i,
                drawdown_pct=float(tier["drawdown_pct"]),
                ratio_pct=float(tier["ratio_pct"]),
                amount_krw=round(base_krw * float(tier["ratio_pct"]) / 100, 0),
                state=state,
                done_amount_krw=done.get(i),
            )
        )
    return out


def due_tiers(statuses: Sequence[TierStatus]) -> list[int]:
    return [s["tier"] for s in statuses if s["state"] == "DUE"]


def due_amount(statuses: Sequence[TierStatus], cap_krw: float) -> float:
    """미완료 도달 구간 금액 합 — `cap_krw`(규칙 남은 몫·남은 여윳돈 중 작은 값)를 넘지 않는다."""
    total = sum(s["amount_krw"] for s in statuses if s["state"] == "DUE")
    return round(max(0.0, min(total, float(cap_krw))), 0)


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


def validate_allocations(allocations: Sequence[float]) -> str | None:
    """규칙 배분 합계 검증(켜고 끈 것과 무관하게 전부) — 오류 문구 또는 None."""
    if any(not 1 <= float(a) <= 100 for a in allocations):
        return "여윳돈 배분은 1~100% 사이로 정해주세요."
    if sum(float(a) for a in allocations) > 100 + 1e-9:
        return "지수별 여윳돈 배분 합계는 100%를 넘을 수 없어요."
    return None


def next_notify_date(day: int, today: date, is_trading_day: Callable[[date], bool]) -> date:
    """오늘 이후(오늘 포함) 첫 알림일 — 매달 `day`일, 휴장이면 다음 거래일.

    지난달 알림일이 휴장으로 이번 달로 밀렸을 수 있어 지난달부터 본다.
    """
    year, month = today.year, today.month
    for offset in (-1, 0, 1, 2):
        m = month + offset
        y = year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        d = date(y, m, min(day, calendar.monthrange(y, m)[1]))
        while not is_trading_day(d):
            d += timedelta(days=1)
        if d >= today:
            return d
    raise ValueError("notify date not found")  # pragma: no cover — 두 달 안에 거래일이 없을 수 없다
