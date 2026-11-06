from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    BROKER_API_DATA_SOURCES,
    COMPREHENSIVE_TAX_THRESHOLD_KRW,
    DOMESTIC_MARKETS,
    OVERSEAS_MARKETS,
    POSITION_STOCK_ASSET_TYPES,
    TAX_DEFERRED_TAX_TYPES,
)
from app.models.asset import AssetAccount, Transaction
from app.services.accounts._snapshot_queries import latest_snapshot_rows
from app.utils.kst import today_kst

_DOMESTIC_LARGE_HOLDER_THRESHOLD = 5_000_000_000  # 대주주 시가총액 기준 — 종목당 50억원(2025년 말 기준 판정부터)

_HEALTH_INSURANCE_DEPENDENT_THRESHOLD_KRW = 20_000_000  # 건강보험 피부양자 자격유지 금융소득 기준
_HEALTH_INSURANCE_REGIONAL_DEDUCTION_KRW = 3_360_000  # 지역가입자 전환 시 소득 기본공제
# 연도별 (건강보험료율, 장기요양보험료율[건강보험료 대비]) — 매년 갱신. 2026년 값은 2차 출처 기준(공단 고시 원문 미확인)
_HEALTH_INSURANCE_RATES: dict[int, tuple[float, float]] = {
    2025: (0.0709, 0.1295),
    2026: (0.0719, 0.1314),
}
_MOCK_CAPABLE_ASSET_TYPES = frozenset({"STOCK_KIS", "STOCK_KIWOOM"})


class _TaxRates(TypedDict):
    dividend: float  # 배당소득세율
    interest: float  # 이자소득세율(원천징수, 지방세 포함)
    overseas_gain: float  # 해외 양도세율
    overseas_deduction: int  # 해외 양도소득 공제 (원)


_TAX_RATES: dict[int, _TaxRates] = {
    2025: _TaxRates(
        dividend=0.154,
        interest=0.154,
        overseas_gain=0.22,
        overseas_deduction=2_500_000,
    ),
    2026: _TaxRates(
        dividend=0.154,
        interest=0.154,
        overseas_gain=0.22,
        overseas_deduction=2_500_000,
    ),
}


def pick_year_rule[T](table: dict[int, T], year: int) -> T:
    """연도별 세법 테이블에서 해당 연도 값을, 없으면 가장 가까운 연도 값을 반환한다."""
    if year in table:
        return table[year]
    return table[min(table, key=lambda y: abs(y - year))]


def get_tax_rates(year: int) -> _TaxRates:
    """연도별 세율 반환. 해당 연도가 없으면 가장 가까운 연도 사용."""
    return pick_year_rule(_TAX_RATES, year)


# 취득가에 매수일이 아닌 현재 환율을 쓴다 — 세법은 취득일 환율 기준이라 달러가 오른 만큼 실제 과세 이익이 더 크다
OVERSEAS_FX_BASIS_NOTE = "매수 시점 환율을 반영하지 않은 추정이라 환차익만큼 실제 과세 이익과 다를 수 있어요."


def is_paper_account(acc: Any) -> bool:
    """KIS·키움 모의투자 계좌인지. 수기·토스 계좌도 컬럼 기본값이 True라 브로커 연동 계좌로 한정한다."""
    return (
        getattr(acc, "is_mock_mode", False) is True
        and acc.asset_type in _MOCK_CAPABLE_ASSET_TYPES
        and acc.data_source in BROKER_API_DATA_SOURCES
    )


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
    yr = year if year is not None else today_kst().year
    rates = get_tax_rates(yr)
    taxable = max(0.0, realized_gain_krw - rates["overseas_deduction"])
    tax = taxable * rates["overseas_gain"]
    return {
        "taxable_gain_krw": round(taxable, 0),
        "estimated_tax_krw": round(tax, 0),
        "rate_pct": rates["overseas_gain"] * 100,
        "deduction_krw": float(rates["overseas_deduction"]),
    }


class HealthInsuranceEstimate(TypedDict):
    financial_income_for_health_insurance_krw: float
    threshold_krw: float
    dependent_risk_warning: bool
    income_remaining_until_risk_krw: float
    estimated_monthly_premium_krw: float | None
    note: str


def _calc_health_insurance_estimate(financial_income: float, year: int | None = None) -> HealthInsuranceEstimate:
    """건강보험 피부양자 자격상실 위험 추정 (금융소득 = 과세계좌 배당 + 기록된 이자 기준 근사치).

    실제 부과액에 필요한 근로/사업/기타소득·재산은 반영하지 않는다 — 참고용 추정치.
    """
    # 기준은 "초과" — 정확히 2,000만원이면 아직 해당하지 않는다
    warning = financial_income > _HEALTH_INSURANCE_DEPENDENT_THRESHOLD_KRW
    premium_rate, long_term_care_rate = pick_year_rule(
        _HEALTH_INSURANCE_RATES, year if year is not None else today_kst().year
    )
    remaining = max(0.0, _HEALTH_INSURANCE_DEPENDENT_THRESHOLD_KRW - financial_income)

    estimated_monthly_premium: float | None = None
    if warning:
        taxable_income = max(0.0, financial_income - _HEALTH_INSURANCE_REGIONAL_DEDUCTION_KRW)
        monthly_premium = (taxable_income / 12) * premium_rate * (1 + long_term_care_rate)
        estimated_monthly_premium = round(monthly_premium, 0)

    return {
        "financial_income_for_health_insurance_krw": round(financial_income, 0),
        "threshold_krw": float(_HEALTH_INSURANCE_DEPENDENT_THRESHOLD_KRW),
        "dependent_risk_warning": warning,
        "income_remaining_until_risk_krw": round(remaining, 0),
        "estimated_monthly_premium_krw": estimated_monthly_premium,
        "note": (
            "기록된 배당·이자 기준 참고 추정치로, 근로/사업소득·재산은 반영되지 않았습니다. "
            "실제 부과액과 다를 수 있습니다."
        ),
    }


async def get_tax_summary(
    user_id: uuid.UUID,
    year: int,
    db: AsyncSession,
    account_id: uuid.UUID | None = None,
    *,
    overseas_realized_krw: float | None = None,
    stock_rows: list[Any] | None = None,
) -> dict[str, Any]:
    """연도별 세금 추정 요약. account_id 지정 시 해당 계좌만 집계(미지정 시 전체 계좌 통합).

    - 배당·이자소득세: 과세계좌 배당금·이자 × 15.4% — ISA·연금저축·IRP 계좌분은 비과세/과세이연이라 제외
    - 해외 양도세: 올해 실현손익(`overseas_realized_krw`, 증권사 체결 기준 — 모르면 0) + 미실현 손익을
      연내 전부 실현한다고 가정한 추정치 (250만원 공제 후 22%). 실현손익은 브로커 API 호출이 필요해
      이 함수가 직접 조회하지 않고 호출부(api/v1/tax.py, tax_action_service)가 넘긴다.
    - `stock_rows`: 호출부가 `load_tax_stock_rows`로 이미 읽은 최신 스냅샷 행(같은 account_id 기준).
      실현손익·절세 액션과 한 요청에서 스냅샷·포지션을 여러 번 읽지 않도록 넘겨받는다 — None이면 직접 1회 조회.
    - 국내 양도세: 한 종목 보유액이 대주주 기준(50억) 이상이면 경고. 판정은 종목별이라 계좌를 합쳐 종목 단위로 본다
    - 금융소득 종합과세 경계(2000만원) 경고 — 이자·배당 기준. 해외주식 양도차익은 양도소득(분류과세)이라
      금융소득에 합산하지 않는다(이전 구현은 해외 미실현 이익을 더해 경고를 과대 발생시켰음)
    - 건강보험 피부양자 자격상실 위험(이자+배당 금융소득 2000만원 기준) + 예상 월 보험료 참고 추정치
    """
    rates = get_tax_rates(year)
    # 같은 AsyncSession을 asyncio.gather로 동시 사용하면 안 된다(세션은 동시 실행 불가) — 순차 호출
    dividend_income = await _calc_dividend_income(user_id, year, db, account_id)
    interest_income = await _calc_interest_income(user_id, year, db, account_id)
    dividend_tax = dividend_income * rates["dividend"]
    interest_tax = interest_income * rates["interest"]

    rows = stock_rows if stock_rows is not None else await _latest_stock_rows(user_id, db, account_id)
    overseas_unrealized = _stock_unrealized_from_rows(rows)[0]
    realized = overseas_realized_krw or 0.0
    overseas_gain_taxable = max(0.0, realized + overseas_unrealized - rates["overseas_deduction"])
    overseas_tax_estimated = overseas_gain_taxable * rates["overseas_gain"]

    largest_domestic_name, largest_domestic_krw = _largest_domestic_holding(rows)
    domestic_large_holder_warning = largest_domestic_krw >= _DOMESTIC_LARGE_HOLDER_THRESHOLD

    # 이자소득은 사용자가 기록한 INTEREST 내역 기준(예금·CMA 등) — 기록이 없으면 배당만으로 근사된다
    total_financial_income = dividend_income + interest_income
    # 기준은 "초과" — 정확히 2,000만원이면 종합과세 대상이 아니다
    comprehensive_tax_warning = total_financial_income > COMPREHENSIVE_TAX_THRESHOLD_KRW
    comprehensive_tax_remaining_krw = max(0.0, COMPREHENSIVE_TAX_THRESHOLD_KRW - total_financial_income)

    positions = _overseas_positions_from_rows(rows)
    harvesting = _build_harvesting_recommendations(positions, overseas_gain_taxable, rates)
    health_insurance_estimate = _calc_health_insurance_estimate(total_financial_income, year)

    return {
        "year": year,
        "dividend_income_krw": round(dividend_income, 0),
        "dividend_tax_krw": round(dividend_tax, 0),
        "interest_income_krw": round(interest_income, 0),
        "interest_tax_krw": round(interest_tax, 0),
        "financial_income_krw": round(total_financial_income, 0),
        "overseas_unrealized_gain_krw": round(overseas_unrealized, 0),
        "overseas_realized_gain_krw": round(overseas_realized_krw, 0) if overseas_realized_krw is not None else None,
        "overseas_gain_deduction_krw": rates["overseas_deduction"],
        "overseas_tax_estimated_krw": round(overseas_tax_estimated, 0),
        "domestic_large_holder_warning": domestic_large_holder_warning,
        "domestic_large_holder_name": largest_domestic_name if domestic_large_holder_warning else None,
        "domestic_large_holder_threshold_krw": _DOMESTIC_LARGE_HOLDER_THRESHOLD,
        "comprehensive_tax_warning": comprehensive_tax_warning,
        "comprehensive_tax_remaining_krw": round(comprehensive_tax_remaining_krw, 0),
        "total_estimated_tax_krw": round(dividend_tax + interest_tax + overseas_tax_estimated, 0),
        "harvesting_recommendations": harvesting,
        "health_insurance_estimate": health_insurance_estimate,
        "note": (
            "해외 주식 양도세는 올해 실현손익(증권사 조회 가능분)과 미실현 손익을 연내 모두 실현한다고 가정한 "
            "추정치입니다. 실제 납부액은 실현 손익 기준으로 계산됩니다. "
            f"{OVERSEAS_FX_BASIS_NOTE} "
            "ISA/연금저축/IRP 계좌 보유분은 과세이연되어 위 추정에서 제외되었습니다."
        ),
        "rates": {
            "dividend_tax_rate_pct": rates["dividend"] * 100,
            "interest_tax_rate_pct": rates["interest"] * 100,
            "overseas_tax_rate_pct": rates["overseas_gain"] * 100,
        },
    }


async def _latest_stock_rows(user_id: uuid.UUID, db: AsyncSession, account_id: uuid.UUID | None) -> list[Any]:
    """활성 주식 계좌의 최신 스냅샷 행(포지션 포함). account_id 지정 시 그 계좌만."""
    rows = await latest_snapshot_rows(
        db,
        user_id,
        account_ids=[account_id] if account_id is not None else None,
        asset_types=POSITION_STOCK_ASSET_TYPES,
        with_positions=True,
    )
    # 모의투자 손익은 실제 소득이 아니다
    return [row for row in rows if not is_paper_account(row[1])]


async def get_overseas_positions_detail(
    user_id: uuid.UUID, db: AsyncSession, account_id: uuid.UUID | None = None
) -> list[dict]:
    """해외 종목별 미실현 손익 목록 반환.

    최신 스냅샷 기준. 수익·손실 종목 모두 포함. account_id 지정 시 해당 계좌만 집계.
    """
    return _overseas_positions_from_rows(await _latest_stock_rows(user_id, db, account_id))


async def load_tax_stock_rows(
    user_id: uuid.UUID, db: AsyncSession, account_id: uuid.UUID | None = None
) -> tuple[list[Any], list[dict]]:
    """최신 스냅샷 행과 그 행에서 만든 해외 포지션 목록 — 세금 요약(`stock_rows=`)과 실현손익
    (`overseas_positions=`)에 함께 넘겨 한 요청에서 스냅샷을 한 번만 읽는다."""
    rows = await _latest_stock_rows(user_id, db, account_id)
    return rows, _overseas_positions_from_rows(rows)


def _overseas_positions_from_rows(rows: list[Any]) -> list[dict]:
    positions: list[dict] = []
    for snap, acc in rows:
        if acc.tax_type in TAX_DEFERRED_TAX_TYPES:
            continue
        for pos in snap.position_items:
            if pos.market not in OVERSEAS_MARKETS:
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
    `current_taxable_gain`은 미실현 이익까지 연내 전부 실현한다는 가정의 값이다 — 올해 실제로 줄어드는 세금은
    실현 이익 기준으로 `tax_action_service.build_loss_harvest_actions`가 다시 계산한다.
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
                "account_id": pos.get("account_id"),
                "unrealized_loss_krw": round(pos["unrealized_pnl_krw"], 0),
                "tax_saved_krw": tax_saved,
                "qty": pos["qty"],
            }
        )
        remaining_gain -= loss
        if remaining_gain <= 0:
            break
    return recommendations


async def _calc_dividend_income(
    user_id: uuid.UUID, year: int, db: AsyncSession, account_id: uuid.UUID | None = None
) -> float:
    """과세 대상 배당소득 합계. 세제혜택 계좌(ISA·연금저축·IRP) 배당은 원천징수·금융소득 합산 대상이
    아니므로 제외한다. 계좌 미지정(account_id NULL) 배당은 과세로 간주."""
    return await _calc_taxable_income_by_type("DIVIDEND", user_id, year, db, account_id)


async def _calc_interest_income(
    user_id: uuid.UUID, year: int, db: AsyncSession, account_id: uuid.UUID | None = None
) -> float:
    """과세 대상 이자소득 합계(예금·적금·CMA·발행어음 등 INTEREST 내역). 제외 규칙은 배당과 동일."""
    return await _calc_taxable_income_by_type("INTEREST", user_id, year, db, account_id)


async def _calc_taxable_income_by_type(
    transaction_type: str, user_id: uuid.UUID, year: int, db: AsyncSession, account_id: uuid.UUID | None
) -> float:
    conditions = [
        Transaction.user_id == user_id,
        Transaction.transaction_type == transaction_type,
        func.extract("year", Transaction.transaction_date) == year,
        or_(AssetAccount.tax_type.is_(None), AssetAccount.tax_type.not_in(TAX_DEFERRED_TAX_TYPES)),
    ]
    if account_id is not None:
        conditions.append(Transaction.account_id == account_id)
    result = await db.execute(
        select(func.sum(Transaction.amount).label("total"))
        .select_from(Transaction)
        .outerjoin(AssetAccount, AssetAccount.id == Transaction.account_id)
        .where(*conditions)
    )
    total = result.scalar()
    return float(total) if total else 0.0


def _largest_domestic_holding(rows: list[Any]) -> tuple[str | None, float]:
    """국내 종목별(계좌 합산) 평가액 중 가장 큰 종목 — 대주주 판정은 종목 단위다.

    ISA·연금 계좌 보유분도 지분이라 합산한다.
    """
    by_ticker: dict[str, float] = {}
    names: dict[str, str] = {}
    for snap, _acc in rows:
        for pos in snap.position_items:
            if pos.market not in DOMESTIC_MARKETS:
                continue
            value = float(pos.current_price or pos.avg_price or 0) * float(pos.qty or 0)
            by_ticker[pos.ticker] = by_ticker.get(pos.ticker, 0.0) + value
            names[pos.ticker] = pos.name or pos.ticker
    if not by_ticker:
        return None, 0.0
    ticker = max(by_ticker, key=lambda t: by_ticker[t])
    return names[ticker], by_ticker[ticker]


def _stock_unrealized_from_rows(rows: list[Any]) -> tuple[float, float, float, float]:
    """최신 스냅샷 기준 해외/국내 미실현 손익과 국내 평가액 반환.

    ISA/연금저축/IRP(과세이연) 계좌 보유분은 국내/해외 미실현손익 합산에서 제외하고
    tax_deferred_value_krw로 별도 집계한다. `rows`는 `_latest_stock_rows()`의 (스냅샷, 계좌) 행.
    OTHER 시장은 국내·해외 어디에도 넣지 않는다(실현손익 `overseas_realized_service`는 해외로 본다 — 세무 판단 보류).

    Returns: (overseas_unrealized_krw, domestic_stock_value_krw, domestic_unrealized_krw, tax_deferred_value_krw)
    """
    overseas_value = 0.0
    overseas_invested = 0.0
    domestic_value = 0.0
    domestic_invested = 0.0
    tax_deferred_value = 0.0

    for snap, acc in rows:
        is_tax_deferred = acc.tax_type in TAX_DEFERRED_TAX_TYPES
        for pos in snap.position_items:
            market = pos.market
            qty = float(pos.qty or 0)
            avg = float(pos.avg_price or 0)
            cur = float(pos.current_price or avg)

            if is_tax_deferred:
                tax_deferred_value += cur * qty
                continue

            if market in OVERSEAS_MARKETS:
                overseas_value += cur * qty
                overseas_invested += avg * qty
            elif market in DOMESTIC_MARKETS:
                domestic_value += cur * qty
                domestic_invested += avg * qty

    overseas_unrealized = overseas_value - overseas_invested
    domestic_unrealized = domestic_value - domestic_invested
    return overseas_unrealized, domestic_value, domestic_unrealized, tax_deferred_value
