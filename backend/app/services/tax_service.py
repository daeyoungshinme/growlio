from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Transaction

_OVERSEAS_MARKETS = {"NYSE", "NASDAQ", "AMEX", "TSE", "HKEX", "SSE", "SGX", "LSE"}
_DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ", "KONEX"}
_DOMESTIC_STOCK_TYPES = {"STOCK_KIS", "STOCK_KIWOOM", "STOCK_OTHER"}

_DIVIDEND_TAX_RATE = 0.154
_OVERSEAS_GAIN_DEDUCTION = 2_500_000
_OVERSEAS_TAX_RATE = 0.22
_DOMESTIC_LARGE_HOLDER_THRESHOLD = 1_000_000_000
_COMPREHENSIVE_TAX_THRESHOLD = 20_000_000


async def get_tax_summary(user_id: uuid.UUID, year: int, db: AsyncSession) -> dict[str, Any]:
    """연도별 세금 추정 요약.

    - 배당소득세: 실수령 배당금 × 15.4% (정확)
    - 해외 양도세: 미실현 손익 기준 추정치 (250만원 공제 후 22%)
    - 국내 양도세: 대주주 요건(10억) 초과 시 경고
    - 금융소득 종합과세 경계(2000만원) 경고
    """
    dividend_income = await _calc_dividend_income(user_id, year, db)
    dividend_tax = dividend_income * _DIVIDEND_TAX_RATE

    overseas_unrealized, domestic_stock_krw = await _calc_stock_unrealized(user_id, db)
    overseas_gain_taxable = max(0.0, overseas_unrealized - _OVERSEAS_GAIN_DEDUCTION)
    overseas_tax_estimated = overseas_gain_taxable * _OVERSEAS_TAX_RATE

    domestic_large_holder_warning = domestic_stock_krw >= _DOMESTIC_LARGE_HOLDER_THRESHOLD

    total_financial_income = dividend_income + max(0.0, overseas_unrealized)
    comprehensive_tax_warning = total_financial_income >= _COMPREHENSIVE_TAX_THRESHOLD

    return {
        "year": year,
        "dividend_income_krw": round(dividend_income, 0),
        "dividend_tax_krw": round(dividend_tax, 0),
        "overseas_unrealized_gain_krw": round(overseas_unrealized, 0),
        "overseas_gain_deduction_krw": _OVERSEAS_GAIN_DEDUCTION,
        "overseas_tax_estimated_krw": round(overseas_tax_estimated, 0),
        "domestic_stock_value_krw": round(domestic_stock_krw, 0),
        "domestic_large_holder_warning": domestic_large_holder_warning,
        "comprehensive_tax_warning": comprehensive_tax_warning,
        "total_estimated_tax_krw": round(dividend_tax + overseas_tax_estimated, 0),
        "note": (
            "해외 주식 양도세는 현재 미실현 손익 기준 추정치입니다. "
            "실제 납부액은 실현 손익 기준으로 계산됩니다."
        ),
        "rates": {
            "dividend_tax_rate_pct": _DIVIDEND_TAX_RATE * 100,
            "overseas_tax_rate_pct": _OVERSEAS_TAX_RATE * 100,
        },
    }


async def _calc_dividend_income(user_id: uuid.UUID, year: int, db: AsyncSession) -> float:
    result = await db.execute(
        select(func.sum(Transaction.amount).label("total"))
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "DIVIDEND",
            func.extract("year", Transaction.transaction_date) == year,
        )
    )
    total = result.scalar()
    return float(total) if total else 0.0


async def _calc_stock_unrealized(
    user_id: uuid.UUID, db: AsyncSession
) -> tuple[float, float]:
    """최신 스냅샷 기준 해외주식 미실현 손익과 국내주식 평가액 반환.

    Returns: (overseas_unrealized_krw, domestic_stock_value_krw)
    """
    subq = (
        select(
            AssetSnapshot.account_id,
            func.max(AssetSnapshot.snapshot_date).label("max_date"),
        )
        .where(AssetSnapshot.user_id == user_id)
        .group_by(AssetSnapshot.account_id)
        .subquery()
    )
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id)
            & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.asset_type.in_(_DOMESTIC_STOCK_TYPES),
        )
    )
    rows = result.all()

    overseas_value = 0.0
    overseas_invested = 0.0
    domestic_value = 0.0

    for snap, _acc in rows:
        positions = snap.positions or []
        for pos in positions:
            market = pos.get("market", "")
            qty = float(pos.get("qty", 0))
            avg = float(pos.get("avg_price", 0))
            cur = float(pos.get("current_price") or avg)

            if market in _OVERSEAS_MARKETS:
                overseas_value += cur * qty
                overseas_invested += avg * qty
            elif market in _DOMESTIC_MARKETS:
                domestic_value += cur * qty

    overseas_unrealized = overseas_value - overseas_invested
    return overseas_unrealized, domestic_value
