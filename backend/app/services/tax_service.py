from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import AssetAccount, AssetSnapshot, Transaction
from app.services._snapshot_queries import latest_snapshot_subquery

_OVERSEAS_MARKETS = {"NYSE", "NASDAQ", "AMEX", "TSE", "HKEX", "SSE", "SGX", "LSE"}
_DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ", "KONEX"}
_DOMESTIC_STOCK_TYPES = {"STOCK_KIS", "STOCK_KIWOOM", "STOCK_OTHER"}
# ISA/연금저축/IRP는 계좌 내 매도 시 즉시 양도세가 발생하지 않는 과세이연 계좌
_TAX_DEFERRED_TYPES = {"ISA", "PENSION_SAVINGS", "IRP"}

_DOMESTIC_LARGE_HOLDER_THRESHOLD = 1_000_000_000
_COMPREHENSIVE_TAX_THRESHOLD = 20_000_000
_GEUMT_EXCESS_THRESHOLD = 300_000_000  # 금투세 누진 구간 기준 3억


class _GeuMTRates(TypedDict):
    standard_pct: float
    excess_above_300m_pct: float


class _TaxRates(TypedDict):
    dividend: float  # 배당소득세율
    overseas_gain: float  # 해외 양도세율
    overseas_deduction: int  # 해외 양도소득 공제 (원)
    geumt_domestic_deduction: int  # 금투세 국내 공제 (원)
    geumt_standard: float  # 금투세 기본세율
    geumt_excess: float  # 금투세 3억 초과 세율


_TAX_RATES: dict[int, _TaxRates] = {
    2025: _TaxRates(
        dividend=0.154,
        overseas_gain=0.22,
        overseas_deduction=2_500_000,
        geumt_domestic_deduction=50_000_000,
        geumt_standard=0.20,
        geumt_excess=0.25,
    ),
    2026: _TaxRates(
        dividend=0.154,
        overseas_gain=0.22,
        overseas_deduction=2_500_000,
        geumt_domestic_deduction=50_000_000,
        geumt_standard=0.20,
        geumt_excess=0.25,
    ),
}


def _get_rates(year: int) -> _TaxRates:
    """연도별 세율 반환. 해당 연도가 없으면 가장 가까운 연도 사용."""
    if year in _TAX_RATES:
        return _TAX_RATES[year]
    closest = min(_TAX_RATES.keys(), key=lambda y: abs(y - year))
    return _TAX_RATES[closest]


class OverseasTransferTaxEstimate(TypedDict):
    taxable_gain_krw: float
    estimated_tax_krw: float
    rate_pct: float
    deduction_krw: float


def estimate_overseas_transfer_tax(realized_gain_krw: float, year: int | None = None) -> OverseasTransferTaxEstimate:
    """해외주식 실현손익 추정치의 대략적 양도세(250만원 공제, 22%)를 계산한다.

    리밸런싱 진단의 "세금 영향 미리보기"에서 재사용하는 참고용 근사치 —
    연간 다른 매매손익과 합산되는 정확한 세액은 get_tax_summary()의 연간 집계를 따른다.
    """
    yr = year if year is not None else datetime.now(UTC).year
    rates = _get_rates(yr)
    taxable = max(0.0, realized_gain_krw - rates["overseas_deduction"])
    tax = taxable * rates["overseas_gain"]
    return {
        "taxable_gain_krw": round(taxable, 0),
        "estimated_tax_krw": round(tax, 0),
        "rate_pct": rates["overseas_gain"] * 100,
        "deduction_krw": float(rates["overseas_deduction"]),
    }


class GeuMTSimulationResult(TypedDict):
    overseas_gain_krw: float
    overseas_deduction_krw: int
    overseas_taxable_krw: float
    overseas_tax_krw: float
    domestic_gain_krw: float
    domestic_deduction_krw: int
    domestic_taxable_krw: float
    domestic_tax_krw: float
    total_tax_krw: float
    current_overseas_tax_krw: float
    tax_difference_krw: float
    note: str
    rates: _GeuMTRates


def _calc_geumt_tax(taxable_gain: float, rates: _TaxRates) -> float:
    """금투세 누진 세율 계산. 3억 이하 기본세율, 초과분 높은세율."""
    if taxable_gain <= 0:
        return 0.0
    if taxable_gain <= _GEUMT_EXCESS_THRESHOLD:
        return taxable_gain * rates["geumt_standard"]
    return (
        _GEUMT_EXCESS_THRESHOLD * rates["geumt_standard"]
        + (taxable_gain - _GEUMT_EXCESS_THRESHOLD) * rates["geumt_excess"]
    )


def _simulate_geumt_tax(overseas_gain: float, domestic_gain: float, rates: _TaxRates) -> GeuMTSimulationResult:
    """금융투자소득세 시뮬레이션 (2025년 이후 유예 중).

    미실현 손익 기준 추정치. 실제 과세는 실현 손익 기준.
    """
    overseas_taxable = max(0.0, overseas_gain - rates["overseas_deduction"])
    domestic_taxable = max(0.0, domestic_gain - rates["geumt_domestic_deduction"])

    overseas_tax = _calc_geumt_tax(overseas_taxable, rates)
    domestic_tax = _calc_geumt_tax(domestic_taxable, rates)
    total_tax = overseas_tax + domestic_tax

    current_overseas_tax = max(0.0, overseas_gain - rates["overseas_deduction"]) * rates["overseas_gain"]
    tax_difference = total_tax - current_overseas_tax

    return {
        "overseas_gain_krw": round(overseas_gain, 0),
        "overseas_deduction_krw": rates["overseas_deduction"],
        "overseas_taxable_krw": round(overseas_taxable, 0),
        "overseas_tax_krw": round(overseas_tax, 0),
        "domestic_gain_krw": round(domestic_gain, 0),
        "domestic_deduction_krw": rates["geumt_domestic_deduction"],
        "domestic_taxable_krw": round(domestic_taxable, 0),
        "domestic_tax_krw": round(domestic_tax, 0),
        "total_tax_krw": round(total_tax, 0),
        "current_overseas_tax_krw": round(current_overseas_tax, 0),
        "tax_difference_krw": round(tax_difference, 0),
        "note": "금투세는 2025년 이후 유예 중입니다. 현재 미실현 손익 기준 추정치입니다.",
        "rates": {
            "standard_pct": rates["geumt_standard"] * 100,
            "excess_above_300m_pct": rates["geumt_excess"] * 100,
        },
    }


async def get_tax_summary(user_id: uuid.UUID, year: int, db: AsyncSession) -> dict[str, Any]:
    """연도별 세금 추정 요약.

    - 배당소득세: 실수령 배당금 × 15.4% (정확)
    - 해외 양도세: 미실현 손익 기준 추정치 (250만원 공제 후 22%)
    - 국내 양도세: 대주주 요건(10억) 초과 시 경고
    - 금융소득 종합과세 경계(2000만원) 경고
    - 연간 거래 수수료 합계 (fee 컬럼)
    """
    rates = _get_rates(year)
    dividend_income, total_fees = await asyncio.gather(
        _calc_dividend_income(user_id, year, db),
        _calc_total_fees(user_id, year, db),
    )
    dividend_tax = dividend_income * rates["dividend"]

    overseas_unrealized, domestic_stock_krw, domestic_unrealized, tax_deferred_value_krw = await _calc_stock_unrealized(
        user_id, db
    )
    overseas_gain_taxable = max(0.0, overseas_unrealized - rates["overseas_deduction"])
    overseas_tax_estimated = overseas_gain_taxable * rates["overseas_gain"]

    domestic_large_holder_warning = domestic_stock_krw >= _DOMESTIC_LARGE_HOLDER_THRESHOLD

    total_financial_income = dividend_income + max(0.0, overseas_unrealized)
    comprehensive_tax_warning = total_financial_income >= _COMPREHENSIVE_TAX_THRESHOLD

    positions = await get_overseas_positions_detail(user_id, db)
    harvesting = _build_harvesting_recommendations(positions, overseas_gain_taxable, rates)
    geumt_simulation = _simulate_geumt_tax(overseas_unrealized, domestic_unrealized, rates)

    return {
        "year": year,
        "dividend_income_krw": round(dividend_income, 0),
        "dividend_tax_krw": round(dividend_tax, 0),
        "overseas_unrealized_gain_krw": round(overseas_unrealized, 0),
        "overseas_gain_deduction_krw": rates["overseas_deduction"],
        "overseas_tax_estimated_krw": round(overseas_tax_estimated, 0),
        "domestic_stock_value_krw": round(domestic_stock_krw, 0),
        "domestic_unrealized_gain_krw": round(domestic_unrealized, 0),
        "domestic_large_holder_warning": domestic_large_holder_warning,
        "comprehensive_tax_warning": comprehensive_tax_warning,
        "total_estimated_tax_krw": round(dividend_tax + overseas_tax_estimated, 0),
        "total_fees_krw": round(total_fees, 0),
        "tax_deferred_value_krw": round(tax_deferred_value_krw, 0),
        "harvesting_recommendations": harvesting,
        "financial_investment_tax_simulation": geumt_simulation,
        "note": (
            "해외 주식 양도세는 현재 미실현 손익 기준 추정치입니다. 실제 납부액은 실현 손익 기준으로 계산됩니다. "
            "ISA/연금저축/IRP 계좌 보유분은 과세이연되어 위 추정에서 제외되었습니다."
        ),
        "rates": {
            "dividend_tax_rate_pct": rates["dividend"] * 100,
            "overseas_tax_rate_pct": rates["overseas_gain"] * 100,
        },
    }


async def get_overseas_positions_detail(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """해외 종목별 미실현 손익 목록 반환.

    최신 스냅샷 기준. 수익·손실 종목 모두 포함.
    """
    subq = latest_snapshot_subquery(user_id=user_id)
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .options(selectinload(AssetSnapshot.position_items))
        .join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.asset_type.in_(_DOMESTIC_STOCK_TYPES),
        )
    )
    rows = result.all()

    positions: list[dict] = []
    for snap, acc in rows:
        if acc.tax_type in _TAX_DEFERRED_TYPES:
            continue
        for pos in snap.position_items:
            if pos.market not in _OVERSEAS_MARKETS:
                continue
            qty = float(pos.qty or 0)
            avg = float(pos.avg_price or 0)
            cur = float(pos.current_price or avg)
            invested = avg * qty
            value = cur * qty
            pnl = value - invested
            pnl_pct = (pnl / invested * 100) if invested else 0.0
            positions.append(
                {
                    "ticker": pos.ticker,
                    "name": pos.name or pos.ticker,
                    "market": pos.market,
                    "currency": pos.currency or "USD",
                    "account_id": str(acc.id),
                    "account_name": acc.name,
                    "qty": qty,
                    "avg_price_krw": avg,
                    "current_price_krw": cur,
                    "avg_price_usd": float(pos.avg_price_usd) if pos.avg_price_usd else None,
                    "value_krw": value,
                    "invested_krw": invested,
                    "unrealized_pnl_krw": pnl,
                    "unrealized_pnl_pct": pnl_pct,
                }
            )
    return positions


def _build_harvesting_recommendations(
    positions: list[dict], current_taxable_gain: float, rates: _TaxRates
) -> list[dict]:
    """손실 수확(Tax-Loss Harvesting) 추천 목록.

    현재 과세 대상 이익이 있을 때, 손실 종목 전량 매도로 절세 가능한 금액을 계산.
    """
    if current_taxable_gain <= 0:
        return []

    loss_positions = [p for p in positions if p["unrealized_pnl_krw"] < 0]
    loss_positions.sort(key=lambda p: p["unrealized_pnl_krw"])

    recommendations: list[dict] = []
    remaining_gain = current_taxable_gain
    for pos in loss_positions:
        loss = abs(pos["unrealized_pnl_krw"])
        offset = min(loss, remaining_gain)
        tax_saved = round(offset * rates["overseas_gain"], 0)
        recommendations.append(
            {
                "ticker": pos["ticker"],
                "name": pos["name"],
                "market": pos["market"],
                "unrealized_loss_krw": round(pos["unrealized_pnl_krw"], 0),
                "tax_saved_krw": tax_saved,
                "qty": pos["qty"],
            }
        )
        remaining_gain -= loss
        if remaining_gain <= 0:
            break
    return recommendations


async def _calc_total_fees(user_id: uuid.UUID, year: int, db: AsyncSession) -> float:
    result = await db.execute(
        select(func.sum(Transaction.fee).label("total")).where(
            Transaction.user_id == user_id,
            Transaction.fee.is_not(None),
            func.extract("year", Transaction.transaction_date) == year,
        )
    )
    total = result.scalar()
    return float(total) if total else 0.0


_PENSION_SAVINGS_LIMIT_KRW = 6_000_000
_PENSION_TOTAL_LIMIT_KRW = 9_000_000
_PENSION_TAX_TYPES = ("PENSION_SAVINGS", "IRP")

_PENSION_CONTRIBUTION_NOTE = (
    "연금저축/IRP 납입액은 계좌별 입출금 내역(수기 입력) 기준 합산입니다. "
    "자동 동기화 계좌라도 입출금 내역을 직접 기록해야 정확히 반영됩니다. "
    "세액공제율은 총급여 기준(5,500만원 이하 16.5%, 초과 13.2%)이며 이 화면에서는 계산하지 않습니다."
)


class PensionContributionStatus(TypedDict):
    year: int
    pension_savings_deposit_krw: float
    irp_deposit_krw: float
    total_deposit_krw: float
    pension_savings_limit_krw: int
    total_limit_krw: int
    pension_savings_achievement_pct: float
    total_achievement_pct: float
    pension_savings_remaining_krw: float
    total_remaining_krw: float
    note: str


async def calc_pension_contribution_status(user_id: uuid.UUID, year: int, db: AsyncSession) -> dict[str, Any]:
    """연금저축/IRP 계좌군의 연간 DEPOSIT 합산 대비 세액공제 한도(600만원/900만원) 진행률.

    Transaction(DEPOSIT) 수기 입력에 의존 — KIS/키움 자동 동기화로는 생성되지 않는다.
    """
    result = await db.execute(
        select(AssetAccount.tax_type, func.sum(Transaction.amount))
        .join(Transaction, Transaction.account_id == AssetAccount.id)
        .where(
            AssetAccount.user_id == user_id,
            AssetAccount.tax_type.in_(_PENSION_TAX_TYPES),
            AssetAccount.is_active == True,  # noqa: E712
            Transaction.transaction_type == "DEPOSIT",
            func.extract("year", Transaction.transaction_date) == year,
        )
        .group_by(AssetAccount.tax_type)
    )
    sums = {row[0]: float(row[1] or 0) for row in result.all()}
    pension_savings = sums.get("PENSION_SAVINGS", 0.0)
    irp = sums.get("IRP", 0.0)
    total = pension_savings + irp

    return {
        "year": year,
        "pension_savings_deposit_krw": round(pension_savings, 0),
        "irp_deposit_krw": round(irp, 0),
        "total_deposit_krw": round(total, 0),
        "pension_savings_limit_krw": _PENSION_SAVINGS_LIMIT_KRW,
        "total_limit_krw": _PENSION_TOTAL_LIMIT_KRW,
        "pension_savings_achievement_pct": round(min(pension_savings / _PENSION_SAVINGS_LIMIT_KRW * 100, 999), 1),
        "total_achievement_pct": round(min(total / _PENSION_TOTAL_LIMIT_KRW * 100, 999), 1),
        "pension_savings_remaining_krw": round(max(0.0, _PENSION_SAVINGS_LIMIT_KRW - pension_savings), 0),
        "total_remaining_krw": round(max(0.0, _PENSION_TOTAL_LIMIT_KRW - total), 0),
        "note": _PENSION_CONTRIBUTION_NOTE,
    }


async def _calc_dividend_income(user_id: uuid.UUID, year: int, db: AsyncSession) -> float:
    result = await db.execute(
        select(func.sum(Transaction.amount).label("total")).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type == "DIVIDEND",
            func.extract("year", Transaction.transaction_date) == year,
        )
    )
    total = result.scalar()
    return float(total) if total else 0.0


async def _calc_stock_unrealized(user_id: uuid.UUID, db: AsyncSession) -> tuple[float, float, float, float]:
    """최신 스냅샷 기준 해외/국내 미실현 손익과 국내 평가액 반환.

    ISA/연금저축/IRP(과세이연) 계좌 보유분은 국내/해외 미실현손익 합산에서 제외하고
    tax_deferred_value_krw로 별도 집계한다.

    Returns: (overseas_unrealized_krw, domestic_stock_value_krw, domestic_unrealized_krw, tax_deferred_value_krw)
    """
    subq = latest_snapshot_subquery(user_id=user_id)
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .options(selectinload(AssetSnapshot.position_items))
        .join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date),
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
    domestic_invested = 0.0
    tax_deferred_value = 0.0

    for snap, acc in rows:
        is_tax_deferred = acc.tax_type in _TAX_DEFERRED_TYPES
        for pos in snap.position_items:
            market = pos.market
            qty = float(pos.qty or 0)
            avg = float(pos.avg_price or 0)
            cur = float(pos.current_price or avg)

            if is_tax_deferred:
                tax_deferred_value += cur * qty
                continue

            if market in _OVERSEAS_MARKETS:
                overseas_value += cur * qty
                overseas_invested += avg * qty
            elif market in _DOMESTIC_MARKETS:
                domestic_value += cur * qty
                domestic_invested += avg * qty

    overseas_unrealized = overseas_value - overseas_invested
    domestic_unrealized = domestic_value - domestic_invested
    return overseas_unrealized, domestic_value, domestic_unrealized, tax_deferred_value
