"""공용 Pydantic 검증 함수."""

import math
from typing import Any

MAX_AMOUNT_KRW = 100_000_000_000  # 1000억 KRW


def _require_finite(v: float | None) -> None:
    # JSON 본문의 NaN/Infinity는 Pydantic float를 통과하고, NaN은 아래 비교(<=, >)가 모두 False라 그대로 저장된다
    if v is not None and not math.isfinite(v):
        raise ValueError("금액이 올바른 숫자가 아닙니다")


def validate_positive_amount(v: float | None) -> float | None:
    _require_finite(v)
    if v is not None and v <= 0:
        raise ValueError("금액은 0보다 커야 합니다")
    if v is not None and v > MAX_AMOUNT_KRW:
        raise ValueError(f"금액은 {MAX_AMOUNT_KRW:,}원을 초과할 수 없습니다")
    return v


def validate_non_negative_amount(v: float | None) -> float | None:
    _require_finite(v)
    if v is not None and v < 0:
        raise ValueError("금액은 0 이상이어야 합니다")
    if v is not None and v > MAX_AMOUNT_KRW:
        raise ValueError(f"금액은 {MAX_AMOUNT_KRW:,}원을 초과할 수 없습니다")
    return v


def validate_portfolio_weights(items: list[Any]) -> list[Any]:
    """각 비중이 0~100이고 합계가 100인지, 종목 코드가 비어 있지 않은지 검증한다(요청 스키마 전용)."""
    if not items:
        raise ValueError("종목이 최소 1개 이상이어야 합니다.")
    # 합계만 보면 110% + -10%처럼 음수 비중이 통과한다
    if any(i.weight < 0 or i.weight > 100 for i in items):
        raise ValueError("각 종목 비중은 0~100 사이여야 합니다.")
    if any(not i.ticker.strip() for i in items):
        raise ValueError("종목 코드가 비어 있는 항목이 있습니다.")
    total = sum(i.weight for i in items)
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"비중 합계가 100이어야 합니다. (현재: {total:.2f})")
    _validate_group_members(items)
    return items


def _validate_group_members(items: list[Any]) -> None:
    """지수 그룹 항목(plans/74) 검증 — 한 종목은 포트폴리오 안에서 한 항목(단독 또는 그룹 하나)에만 속한다.

    같은 종목이 두 곳에 있으면 그 보유액이 양쪽 현재 비중에 이중으로 잡힌다. 그룹 안에서 대표 종목과 같은
    멤버는 조용히 제거한다(편집기가 대표 종목을 멤버 칩으로도 보여줄 수 있음).
    """
    from app.constants import DOMESTIC_MARKETS

    # 그룹이 없는 포트폴리오는 기존 규칙 그대로(단독 항목끼리의 중복은 예전부터 막지 않았다)
    if not any(getattr(i, "group", None) is not None for i in items):
        return
    owner: dict[tuple[str, str], int] = {}
    groups: set[str] = set()
    for idx, item in enumerate(items):
        primary = (item.ticker, item.market)
        keys = [primary]
        group = getattr(item, "group", None)
        if group is not None:
            if group.key in groups:
                raise ValueError(f"같은 지수 그룹이 두 번 있습니다: {group.label or group.key}")
            groups.add(group.key)
            alt = group.domestic_alt
            if alt is not None and alt.market not in DOMESTIC_MARKETS:
                raise ValueError("국내 대체 종목은 국내 상장 종목이어야 합니다.")
            if alt is not None and alt.leverage != 1:
                raise ValueError("국내 대체 매수 종목은 레버리지 ETF일 수 없습니다.")
            if alt is not None and (alt.ticker, alt.market) == primary:
                group.domestic_alt = alt = None
            excluded = {primary} | ({(alt.ticker, alt.market)} if alt else set())
            group.members = [m for m in group.members if (m.ticker, m.market) not in excluded]
            keys += [(m.ticker, m.market) for m in group.members]
            if alt is not None:
                keys.append((alt.ticker, alt.market))
        for key in keys:
            if key in owner:
                where = "같은 그룹" if owner[key] == idx else "여러 항목(단독 또는 지수 그룹)"
                raise ValueError(f"{key[0]} 종목이 {where}에 중복으로 들어 있습니다.")
            owner[key] = idx


def validate_portfolio_weights_optional(items: list[Any] | None) -> list[Any] | None:
    """Optional 필드용 — None이면 통과, 아니면 validate_portfolio_weights 적용."""
    if items is None:
        return items
    return validate_portfolio_weights(items)
