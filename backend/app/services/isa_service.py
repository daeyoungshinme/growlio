from __future__ import annotations

import uuid
from datetime import date
from typing import TypedDict

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import AssetAccount, AssetSnapshot, Transaction
from app.services._account_queries import active_accounts_stmt
from app.services._snapshot_queries import latest_snapshot_subquery
from app.utils.kst import today_kst

ISA_MATURITY_YEARS = 3
_ISA_TAX_FREE_LIMIT: dict[str, int] = {"GENERAL": 2_000_000, "PREFERENTIAL": 4_000_000}
_ISA_EXCESS_TAX_RATE = 0.099  # 비과세 한도 초과분 9.9% 분리과세 (지방소득세 포함)

# 일반계좌 대비 절세액 계산용 — tax_service.py와 동일 해외시장 분류/세율(값 변경 시 두 파일 함께 수정).
# 이 집합에 없는 시장(국내 KOSPI/KOSDAQ/KONEX 포함)은 전부 국내로 취급 — 기존 손익통산 합계(시장 구분 없이 전량 합산)를
# 그대로 보존하기 위함(미분류 시장을 누락시키지 않음).
_OVERSEAS_MARKETS = {"NYSE", "NASDAQ", "AMEX", "TSE", "HKEX", "SSE", "SGX", "LSE"}
_GENERAL_DIVIDEND_TAX_RATE = 0.154  # 일반계좌 배당/이자소득세 원천징수율 (tax_service.py dividend 세율과 동일)
_OVERSEAS_GAIN_TAX_RATE = 0.22  # 일반계좌 해외주식 양도세율 (tax_service.py overseas_gain과 동일)
_OVERSEAS_GAIN_DEDUCTION_KRW = 2_500_000  # 해외주식 양도세 연간 공제 (tax_service.py overseas_deduction과 동일)

_ISA_STATUS_NOTE = (
    "ISA 손익은 최신 스냅샷 기준 미실현손익과 배당/이자 내역(수기 입력분 포함) 합산 추정치입니다. "
    "계좌 내 실현 매매차익(매도 이력)은 반영되지 않으므로, 정확한 손익은 직접 입력으로 보정할 수 있습니다. "
    "절세액은 동일 손익을 일반계좌로 보유했을 경우의 예상세금(배당/이자소득 15.4%, 국내주식 매매손익 비과세, "
    "해외주식 매매손익 22%-250만원 공제)과 ISA 저율과세(9.9%)의 차액입니다. 손익을 직접 입력한 계좌는 구성요소가"
    "분리되지 않아 전체를 배당소득으로 가정한 근사치입니다."
)


class IsaAccountStatus(TypedDict):
    account_id: str
    account_name: str
    isa_type: str
    isa_open_date: str | None
    maturity_date: str | None
    is_mature: bool
    days_remaining: int | None
    needs_open_date: bool
    estimated_cumulative_pnl_krw: float
    is_manual_override: bool
    isa_baseline_captured_at: str | None
    tax_free_limit_krw: int
    taxable_excess_krw: float
    estimated_tax_krw: float
    general_account_tax_krw: float
    tax_saved_krw: float
    tax_calculation_basis: str


class IsaStatusSummary(TypedDict):
    accounts: list[IsaAccountStatus]
    note: str


async def get_isa_status_summary(user_id: uuid.UUID, db: AsyncSession) -> IsaStatusSummary:
    """사용자의 ISA 계좌별 의무가입(3년) 진행 상황과 비과세 한도 대비 세금 추정치를 반환한다."""
    accounts_result = await db.execute(active_accounts_stmt(user_id).where(AssetAccount.tax_type == "ISA"))
    accounts = accounts_result.scalars().all()
    if not accounts:
        return {"accounts": [], "note": _ISA_STATUS_NOTE}

    account_ids = [acc.id for acc in accounts]
    unrealized_by_account = await _calc_unrealized_by_account_and_market(account_ids, db)
    dividend_by_account = await _calc_dividend_total_by_account(user_id, account_ids, db)

    today = today_kst()
    statuses: list[IsaAccountStatus] = []
    for acc in accounts:
        unrealized = unrealized_by_account.get(acc.id, {"domestic": 0.0, "overseas": 0.0})
        dividend = dividend_by_account.get(acc.id, 0.0)
        auto_pnl = unrealized["domestic"] + unrealized["overseas"] + dividend
        manual_pnl = acc.isa_manual_cumulative_pnl_krw
        baseline_auto_pnl = acc.isa_baseline_auto_pnl_krw
        is_override = manual_pnl is not None
        if manual_pnl is None:
            effective_pnl = auto_pnl
        elif baseline_auto_pnl is not None:
            # baseline 저장 시점 이후의 auto_pnl 변화분(가격변동·신규배당)을 기준값에 더한다
            effective_pnl = float(manual_pnl) + (auto_pnl - float(baseline_auto_pnl))
        else:
            # 레거시 계좌: baseline 스냅샷이 없어 델타를 계산할 수 없으므로 완전 대체 유지
            effective_pnl = float(manual_pnl)

        maturity_date: date | None = None
        is_mature = False
        days_remaining: int | None = None
        if acc.isa_open_date is not None:
            maturity_date = acc.isa_open_date + relativedelta(years=ISA_MATURITY_YEARS)
            is_mature = today >= maturity_date
            days_remaining = max(0, (maturity_date - today).days)

        isa_type = acc.isa_type or "GENERAL"
        limit = _ISA_TAX_FREE_LIMIT.get(isa_type, _ISA_TAX_FREE_LIMIT["GENERAL"])
        excess = max(0.0, effective_pnl - limit)
        estimated_tax = excess * _ISA_EXCESS_TAX_RATE

        if is_override:
            # 수기 입력값은 배당/국내/해외 구성요소가 분리되지 않으므로 전체를 배당소득으로 가정한 근사치
            general_account_tax = max(0.0, effective_pnl) * _GENERAL_DIVIDEND_TAX_RATE
            calculation_basis = "MANUAL_OVERRIDE_APPROX"
        else:
            dividend_tax = max(0.0, dividend) * _GENERAL_DIVIDEND_TAX_RATE
            overseas_taxable = max(0.0, unrealized["overseas"] - _OVERSEAS_GAIN_DEDUCTION_KRW)
            overseas_tax = overseas_taxable * _OVERSEAS_GAIN_TAX_RATE
            # 국내주식 매매손익은 일반계좌에서도 비과세이므로 세금 기여분 없음
            general_account_tax = dividend_tax + overseas_tax
            calculation_basis = "AUTO_SPLIT"
        tax_saved = max(0.0, general_account_tax - estimated_tax)

        statuses.append(
            {
                "account_id": str(acc.id),
                "account_name": acc.name,
                "isa_type": isa_type,
                "isa_open_date": acc.isa_open_date.isoformat() if acc.isa_open_date else None,
                "maturity_date": maturity_date.isoformat() if maturity_date else None,
                "is_mature": is_mature,
                "days_remaining": days_remaining,
                "needs_open_date": acc.isa_open_date is None,
                "estimated_cumulative_pnl_krw": round(effective_pnl, 0),
                "is_manual_override": is_override,
                "isa_baseline_captured_at": (
                    acc.isa_baseline_captured_at.isoformat() if acc.isa_baseline_captured_at else None
                ),
                "tax_free_limit_krw": limit,
                "taxable_excess_krw": round(excess, 0),
                "estimated_tax_krw": round(estimated_tax, 0),
                "general_account_tax_krw": round(general_account_tax, 0),
                "tax_saved_krw": round(tax_saved, 0),
                "tax_calculation_basis": calculation_basis,
            }
        )

    return {"accounts": statuses, "note": _ISA_STATUS_NOTE}


async def calc_account_auto_pnl(user_id: uuid.UUID, account_id: uuid.UUID, db: AsyncSession) -> float:
    """계좌 1개의 자동 추정 누적손익(국내+해외 미실현손익+배당)을 계산한다.

    ISA 누적손익 수기 입력(baseline) 저장 시점의 스냅샷을 캡처하는 데 쓰인다.
    """
    unrealized = await _calc_unrealized_by_account_and_market([account_id], db)
    dividend = await _calc_dividend_total_by_account(user_id, [account_id], db)
    u = unrealized.get(account_id, {"domestic": 0.0, "overseas": 0.0})
    return u["domestic"] + u["overseas"] + dividend.get(account_id, 0.0)


async def _calc_unrealized_by_account_and_market(
    account_ids: list[uuid.UUID], db: AsyncSession
) -> dict[uuid.UUID, dict[str, float]]:
    """계좌별 국내/해외 미실현손익을 분리 집계한다 (일반계좌 대비 절세액 비교용)."""
    subq = latest_snapshot_subquery(account_ids=account_ids)
    result = await db.execute(
        select(AssetSnapshot)
        .options(selectinload(AssetSnapshot.position_items))
        .join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
    )
    snapshots = result.scalars().all()

    unrealized_by_account: dict[uuid.UUID, dict[str, float]] = {}
    for snap in snapshots:
        if snap.account_id is None:
            continue
        domestic = 0.0
        overseas = 0.0
        for pos in snap.position_items:
            qty = float(pos.qty or 0)
            avg = float(pos.avg_price or 0)
            cur = float(pos.current_price or avg)
            gain = (cur - avg) * qty
            if pos.market in _OVERSEAS_MARKETS:
                overseas += gain
            else:
                domestic += gain
        unrealized_by_account[snap.account_id] = {"domestic": domestic, "overseas": overseas}
    return unrealized_by_account


async def _calc_dividend_total_by_account(
    user_id: uuid.UUID, account_ids: list[uuid.UUID], db: AsyncSession
) -> dict[uuid.UUID, float]:
    result = await db.execute(
        select(Transaction.account_id, func.sum(Transaction.amount))
        .where(
            Transaction.user_id == user_id,
            Transaction.account_id.in_(account_ids),
            Transaction.transaction_type == "DIVIDEND",
        )
        .group_by(Transaction.account_id)
    )
    return {row[0]: float(row[1] or 0) for row in result.all()}
