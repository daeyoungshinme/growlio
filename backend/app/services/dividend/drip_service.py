"""배당 현금흐름 최적화 — DRIP 시뮬레이션, 월별 균등화 제안."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# DRIP 시뮬레이션
# ---------------------------------------------------------------------------

@dataclass
class DRIPSimulationPoint:
    year: int
    month: int
    portfolio_value_drip: float
    portfolio_value_cash: float
    cumulative_dividend_krw: float


def simulate_drip(
    *,
    initial_portfolio_value: float,
    monthly_contribution: float,
    annual_return_pct: float,
    annual_dividend_yield_pct: float,
    n_years: int,
    drip: bool,
) -> dict[str, Any]:
    """DRIP(배당 재투자) vs 현금수령 비교 투영.

    간소화 모델:
    - 매월 monthly_return = (1 + annual_return/12)
    - DRIP: 배당금을 포트폴리오에 재투자
    - 현금: 배당금을 별도 현금으로 수령
    """
    if n_years <= 0 or n_years > 50:
        n_years = min(max(n_years, 1), 50)

    monthly_return = (1 + annual_return_pct / 100) ** (1 / 12)
    monthly_div_yield = annual_dividend_yield_pct / 100 / 12

    portfolio_drip = float(initial_portfolio_value)
    portfolio_cash = float(initial_portfolio_value)
    total_dividend_received = 0.0

    points: list[dict] = []
    for i in range(n_years * 12):
        year = i // 12 + 1
        month = i % 12 + 1

        dividend_drip = portfolio_drip * monthly_div_yield
        dividend_cash = portfolio_cash * monthly_div_yield

        total_dividend_received += dividend_cash

        # 월 수익률 적용
        portfolio_drip = (portfolio_drip + monthly_contribution + dividend_drip) * monthly_return
        portfolio_cash = (portfolio_cash + monthly_contribution) * monthly_return

        if month == 12 or i == 0:
            points.append({
                "year": year,
                "portfolio_value_drip": round(portfolio_drip, 0),
                "portfolio_value_cash": round(portfolio_cash, 0),
                "cumulative_dividend_krw": round(total_dividend_received, 0),
            })

    final_drip = points[-1]["portfolio_value_drip"] if points else 0.0
    final_cash = points[-1]["portfolio_value_cash"] if points else 0.0
    drip_advantage_pct = (final_drip / final_cash - 1) * 100 if final_cash > 0 else 0.0

    return {
        "n_years": n_years,
        "annual_return_pct": annual_return_pct,
        "annual_dividend_yield_pct": annual_dividend_yield_pct,
        "initial_portfolio_value": initial_portfolio_value,
        "monthly_contribution": monthly_contribution,
        "final_value_drip": round(final_drip, 0),
        "final_value_cash": round(final_cash, 0),
        "drip_advantage_pct": round(drip_advantage_pct, 2),
        "total_dividend_received_krw": round(total_dividend_received, 0),
        "yearly_points": points,
        "note": "간소화 모델: 배당금을 포지션 비중대로 균등 재투자하는 것으로 가정합니다.",
    }


# ---------------------------------------------------------------------------
# 월별 균등화 제안
# ---------------------------------------------------------------------------

def calc_monthly_optimization(
    ticker_summaries: list[dict],
) -> list[dict]:
    """배당이 약한 달에 수령 가능한 종목 추천.

    Returns:
        월별로 추가 매수하면 배당이 생기는 종목 추천 목록.
        weak_months: 배당 수령이 없거나 적은 달.
        suggestions: [{month, ticker, name, estimated_monthly_krw}]
    """
    # 현재 월별 예상 배당 합계 계산
    monthly_totals: dict[int, float] = {m: 0.0 for m in range(1, 13)}
    for item in ticker_summaries:
        months: list[int] = item.get("dividend_months") or []
        estimated_annual = float(item.get("estimated_annual_krw") or 0)
        if not months or estimated_annual <= 0:
            continue
        per_payment = estimated_annual / len(months)
        for month in months:
            if 1 <= month <= 12:
                monthly_totals[month] += per_payment

    avg_monthly = sum(monthly_totals.values()) / 12 if any(monthly_totals.values()) else 0
    threshold = avg_monthly * 0.5

    weak_months = [m for m, total in monthly_totals.items() if total < threshold]
    if not weak_months:
        return []

    suggestions: list[dict] = []
    for item in ticker_summaries:
        item_months: list[int] = item.get("dividend_months") or []
        estimated_annual = float(item.get("estimated_annual_krw") or 0)
        if not item_months or estimated_annual <= 0:
            continue

        for weak_month in weak_months:
            if weak_month in item_months:
                per_payment = estimated_annual / len(item_months)
                suggestions.append({
                    "month": weak_month,
                    "ticker": item.get("ticker", ""),
                    "name": item.get("name") or item.get("ticker", ""),
                    "market": item.get("market", ""),
                    "estimated_monthly_krw": round(per_payment, 0),
                    "current_monthly_total_krw": round(monthly_totals[weak_month], 0),
                })

    # 약한 달, 추정금액 기준 정렬
    suggestions.sort(key=lambda x: (x["month"], -x["estimated_monthly_krw"]))

    # 동일 달 내 상위 3개만
    filtered: list[dict] = []
    month_counts: dict[int, int] = {}
    for s in suggestions:
        cnt = month_counts.get(s["month"], 0)
        if cnt < 3:
            filtered.append(s)
            month_counts[s["month"]] = cnt + 1

    return filtered
