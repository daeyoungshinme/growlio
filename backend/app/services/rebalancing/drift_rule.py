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


def band_width_pct(target_weight_pct: float, threshold_pct: float, relative_threshold_pct: float | None) -> float:
    """이탈 기준선까지의 폭(%p) — `is_drifting`이 먼저 걸리는 쪽(절대·상대 중 좁은 것)."""
    if relative_threshold_pct and target_weight_pct > 0:
        return min(threshold_pct, target_weight_pct * relative_threshold_pct / 100)
    return threshold_pct


def shrink_to_band(item: Any, threshold_pct: float, relative_threshold_pct: float | None = None) -> None:
    """이탈 항목의 목표 금액을 목표 비중이 아니라 **허용 범위 경계**까지로 줄인다(plans/145 B3, 제자리 수정).

    경계는 `목표 ± band_width_pct` — 모자라면 하단, 넘치면 상단까지만 사고판다. 수량·차이는 모두 `target_value_krw`에서
    파생되므로(`refresh_live_prices`·`expand_group_items`가 이 값으로 다시 계산) 그 값을 기준으로 맞춘다.
    지수 그룹 행은 수량이 없어 목표 금액만 바꾼다. 경계 안쪽 항목은 바꾸지 않는다.
    """
    target_w = float(item.target_weight_pct or 0)
    diff_w = float(item.weight_diff_pct or 0)
    band = band_width_pct(target_w, threshold_pct, relative_threshold_pct)
    if abs(diff_w) <= band:
        return
    if target_w > 0:
        base = float(item.target_value_krw) * 100 / target_w
    elif float(item.current_weight_pct or 0) > 0:
        base = float(item.current_value_krw) * 100 / float(item.current_weight_pct)
    else:
        return
    edge_w = target_w - band if diff_w > 0 else target_w + band
    edge_value = round(base * edge_w / 100, 0)
    item.target_value_krw = edge_value
    item.diff_krw = round(edge_value - float(item.current_value_krw), 0)
    price = getattr(item, "current_price_krw", None)
    if getattr(item, "shares_to_trade", None) is not None and price and price > 0:
        from app.services.rebalancing._order_quantity_guard import floor_shares

        current_qty = float(item.current_qty or 0)
        item.target_qty = float(floor_shares(edge_value / float(price)))
        item.shares_to_trade = item.target_qty - current_qty
