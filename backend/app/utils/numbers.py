"""숫자 변환 공통 유틸리티."""

from __future__ import annotations

from decimal import Decimal


def opt_float(value: Decimal | float | int | None) -> float | None:
    """Numeric 컬럼(Decimal) 값을 float로 바꾸고 None은 그대로 둔다."""
    return float(value) if value is not None else None
