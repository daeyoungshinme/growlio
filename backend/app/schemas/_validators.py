"""공용 Pydantic 검증 함수."""

from typing import Any

MAX_AMOUNT_KRW = 100_000_000_000  # 1000억 KRW


def validate_positive_amount(v: float | None) -> float | None:
    if v is not None and v <= 0:
        raise ValueError("금액은 0보다 커야 합니다")
    if v is not None and v > MAX_AMOUNT_KRW:
        raise ValueError(f"금액은 {MAX_AMOUNT_KRW:,}원을 초과할 수 없습니다")
    return v


def validate_non_negative_amount(v: float | None) -> float | None:
    if v is not None and v < 0:
        raise ValueError("금액은 0 이상이어야 합니다")
    if v is not None and v > MAX_AMOUNT_KRW:
        raise ValueError(f"금액은 {MAX_AMOUNT_KRW:,}원을 초과할 수 없습니다")
    return v


def validate_portfolio_weights(items: list[Any]) -> list[Any]:
    """비중 합계가 100인지 검증한다. items가 비어 있으면 ValueError를 발생시킨다."""
    if not items:
        raise ValueError("종목이 최소 1개 이상이어야 합니다.")
    total = sum(i.weight for i in items)
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"비중 합계가 100이어야 합니다. (현재: {total:.2f})")
    return items


def validate_portfolio_weights_optional(items: list[Any] | None) -> list[Any] | None:
    """Optional 필드용 — None이면 통과, 아니면 validate_portfolio_weights 적용."""
    if items is None:
        return items
    return validate_portfolio_weights(items)
