"""배당금 계산 순수 함수 모듈.

DB 등 외부 의존 없음 — 입력값만으로 배당 수익률 및 예상 배당금을 계산한다.
"""

from __future__ import annotations

import structlog

from app.constants import DOMESTIC_MARKETS
from app.services.dividend.constants import is_korean_etf

logger = structlog.get_logger()


def calculate_position_dividend(
    *,
    ticker: str,
    market: str,
    yield_decimal: float,
    dps: float,
    months: list[int],
    value_krw: float,
    invested_krw: float,
    qty: float,
    override_months: list[int] | None,
    usd_krw_rate: float = 0.0,
    ex_dividend_date: str | None = None,
) -> dict:
    """보유 종목 하나의 배당 수익률·예상 배당금을 계산한다.

    국내 일반주식: 연간 합산 DPS × 수량 기반
    국내 ETF·해외 주식/ETF: 배당수익률(yield) × 평가금액 기반

    usd_krw_rate가 0이면 estimated_monthly_usd는 None으로 반환된다.
    """
    is_korean = market.upper() in DOMESTIC_MARKETS
    is_etf = is_korean_etf(ticker, market)

    if is_korean and not is_etf and dps > 0 and qty > 0:
        annual = dps * qty
        cost_per_share = (invested_krw / qty) if invested_krw > 0 else (value_krw / qty)
        investment_yield = round(dps / cost_per_share * 100, 2) if cost_per_share > 0 else 0.0
        if investment_yield > 50.0:
            logger.warning(
                "investment_yield_abnormal",
                ticker=ticker,
                market=market,
                investment_yield=investment_yield,
                dps=dps,
                cost_per_share=cost_per_share,
                yield_decimal=yield_decimal,
            )
            investment_yield = round(yield_decimal * 100, 2) if yield_decimal > 0 else 0.0
    else:
        annual = value_krw * yield_decimal
        investment_yield = (
            round(annual / invested_krw * 100, 2)
            if (invested_krw > 0 and yield_decimal > 0)
            else round(yield_decimal * 100, 2)
        )

    is_usd = not is_korean
    estimated_monthly_usd = None
    if is_usd and annual > 0 and usd_krw_rate > 0:
        estimated_monthly_usd = round(annual / 12 / usd_krw_rate, 2)

    return {
        "ticker": ticker,
        "market": market,
        "yield_decimal": yield_decimal,
        "dividend_yield": round(yield_decimal * 100, 2),
        "dps": round(dps, 2),
        "ex_dividend_date": ex_dividend_date,
        "estimated_annual_krw": round(annual),
        "estimated_monthly_krw": round(annual / 12),
        "dividend_months": months,
        "dividend_months_is_manual": override_months is not None,
        "investment_yield": investment_yield,
        "currency": "USD" if is_usd else "KRW",
        "estimated_monthly_usd": estimated_monthly_usd,
    }
