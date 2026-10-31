"""포지션 P&L 계산 공통 유틸리티."""

from __future__ import annotations

from collections.abc import Iterable
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


def calc_net_asset_amount(
    manual_amount: float | None,
    asset_type: str,
    real_estate_details: dict | None,
) -> float:
    """manual_amount에서 부동산 모기지를 차감한 순자산 금액을 반환한다."""
    amount = float(manual_amount or 0)
    if asset_type == "REAL_ESTATE":
        mortgage = float((real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
        amount -= mortgage
    return amount


def reprice_positions_krw(positions: Iterable[Any], price_map: dict[str, float], usd_rate: float | None) -> None:
    """수동 포지션의 current_price·value_krw를 시세(price_map: ticker→현지통화 가격)로 원화 갱신한다.

    해외 종목은 usd_rate로 환산한다. 시세가 없으면 기존 현재가 → 평단 순으로 유지한다.
    수동 계좌 동기화와 "현재가 갱신" 엔드포인트가 공유한다.
    """
    from app.kis.constants import OVERSEAS_MARKETS

    for p in positions:
        raw_price = price_map.get(p.ticker)
        if raw_price and p.market in OVERSEAS_MARKETS and usd_rate:
            price_krw = raw_price * usd_rate
        elif raw_price:
            price_krw = raw_price
        else:
            price_krw = float(p.current_price or p.avg_price or 0)
        p.current_price = price_krw
        p.value_krw = price_krw * float(p.qty or 0)
