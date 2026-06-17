"""포지션 P&L 계산 공통 유틸리티."""

from __future__ import annotations

from typing import Any


def eval_value(positions: list[Any]) -> float:
    """현재가 기준 평가금액 합계. 현재가 없으면 매수가 사용."""
    return sum(float(p.current_price or p.avg_price or 0) * float(p.qty or 0) for p in positions)


def invested_value(positions: list[Any]) -> float:
    """매수가 기준 투자금액 합계."""
    return sum(float(p.avg_price or 0) * float(p.qty or 0) for p in positions)


def pnl_pct(eval_val: float, invested_val: float) -> float:
    """수익률(%). 투자금 없으면 0."""
    return (eval_val / invested_val - 1) * 100 if invested_val > 0 else 0.0


def calc_position_pnl(qty: float, avg_price: float, current_price: float) -> tuple[float, float, float, float]:
    """단일 포지션의 (투자금, 평가금, 손익, 수익률%) 반환."""
    invested = qty * avg_price
    value = qty * current_price
    pnl = value - invested
    rate = (pnl / invested * 100) if invested else 0.0
    return invested, value, pnl, rate
