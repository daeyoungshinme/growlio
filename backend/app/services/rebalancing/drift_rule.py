"""비중 이탈 판정 규칙(순수) — 알림·자동 실행·진단·이메일 강조가 모두 이 한 곳을 따른다.

프론트 `utils/portfolio.ts`의 `isDriftingItem`과 같은 규칙이다 — 바꿀 땐 양쪽을 함께 고친다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

DEFAULT_DRIFT_THRESHOLD_PCT = 5.0
"""알림이 없는 포트폴리오의 이탈 기준(%p) — 진단·인사이트·지금 할 일이 같은 값을 쓴다."""


def is_drifting(
    weight_diff_pct: float,
    target_weight_pct: float,
    threshold_pct: float,
    relative_threshold_pct: float | None = None,
) -> bool:
    """절대 %p 기준을 **초과**하거나, 상대 기준이 켜져 있으면 목표 대비 상대 이탈이 그 기준을 **초과**하면 이탈.

    상대 기준(plans/136, "5/25 규칙")은 목표 비중이 작은 종목을 위한 것 — 목표 5% 종목은 0%가 돼도 절대 5%p를
    넘지 못한다. 목표가 0인 항목(목표 밖 보유·암묵 예수금)은 상대 이탈이 정의되지 않아 절대 기준만 본다.
    """
    diff = abs(weight_diff_pct)
    if diff > threshold_pct:
        return True
    if relative_threshold_pct is None or target_weight_pct <= 0:
        return False
    return diff / target_weight_pct * 100 > relative_threshold_pct


def relative_drift_ratio(weight_diff_pct: float, target_weight_pct: float) -> float | None:
    """목표 대비 상대 이탈(%) — 목표가 0이면 None."""
    if target_weight_pct <= 0:
        return None
    return abs(weight_diff_pct) / target_weight_pct * 100


def drift_progress(
    items: list[Any],
    threshold_pct: float,
    relative_threshold_pct: float | None = None,
) -> float:
    """기준 대비 가장 많이 다가간 항목의 비율(1.0 = 기준선) — "주의"(절반 이상) 판정용.

    절대 기준(`|diff|/threshold`)과 상대 기준(`상대이탈/relative`) 중 큰 쪽.
    """
    best = 0.0
    for item in items:
        diff = abs(float(item.weight_diff_pct))
        if threshold_pct > 0:
            best = max(best, diff / threshold_pct)
        if relative_threshold_pct:
            ratio = relative_drift_ratio(diff, float(item.target_weight_pct))
            if ratio is not None:
                best = max(best, ratio / relative_threshold_pct)
    return best


def alert_relative_threshold(alert: Any) -> float | None:
    """알림 행의 상대 이탈 기준(없으면 None). Numeric(Decimal)만 숫자로 인정한다 — 테스트 MagicMock 속성이
    `float()`로 1.0이 되어 모든 항목을 이탈로 만드는 일을 막는다."""
    value = getattr(alert, "relative_threshold_pct", None)
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
        return None
    return float(value)
