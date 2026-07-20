"""연금저축/IRP 계좌군 세액공제 한도 납입 현황 — tax_service.py의 양도세/배당세 로직과 무관한 별도 도메인."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, Transaction

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
