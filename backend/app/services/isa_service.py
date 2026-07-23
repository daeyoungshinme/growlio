from __future__ import annotations

import uuid
from datetime import date
from typing import Any, TypedDict

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import AssetAccount, AssetSnapshot, Transaction
from app.services._account_queries import active_accounts_stmt
from app.services._snapshot_queries import latest_snapshot_subquery

ISA_MATURITY_YEARS = 3
_ISA_TAX_FREE_LIMIT: dict[str, int] = {"GENERAL": 2_000_000, "PREFERENTIAL": 4_000_000}
_ISA_EXCESS_TAX_RATE = 0.099  # 비과세 한도 초과분 9.9% 분리과세 (지방소득세 포함)

_ISA_STATUS_NOTE = (
    "ISA 손익은 최신 스냅샷 기준 미실현손익과 배당/이자 내역(수기 입력분 포함) 합산 추정치입니다. "
    "계좌 내 실현 매매차익(매도 이력)은 반영되지 않으므로, 정확한 손익은 직접 입력으로 보정할 수 있습니다."
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
    tax_free_limit_krw: int
    taxable_excess_krw: float
    estimated_tax_krw: float


class IsaStatusSummary(TypedDict):
    accounts: list[IsaAccountStatus]
    note: str


async def get_isa_status_summary(user_id: uuid.UUID, db: AsyncSession) -> dict[str, Any]:
    """사용자의 ISA 계좌별 의무가입(3년) 진행 상황과 비과세 한도 대비 세금 추정치를 반환한다."""
    accounts_result = await db.execute(active_accounts_stmt(user_id).where(AssetAccount.tax_type == "ISA"))
    accounts = accounts_result.scalars().all()
    if not accounts:
        return {"accounts": [], "note": _ISA_STATUS_NOTE}

    account_ids = [acc.id for acc in accounts]
    unrealized_by_account = await _calc_unrealized_by_account(account_ids, db)
    dividend_by_account = await _calc_dividend_total_by_account(user_id, account_ids, db)

    today = date.today()
    statuses: list[IsaAccountStatus] = []
    for acc in accounts:
        auto_pnl = unrealized_by_account.get(acc.id, 0.0) + dividend_by_account.get(acc.id, 0.0)
        manual_pnl = acc.isa_manual_cumulative_pnl_krw
        is_override = manual_pnl is not None
        effective_pnl = float(manual_pnl) if manual_pnl is not None else auto_pnl

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
                "tax_free_limit_krw": limit,
                "taxable_excess_krw": round(excess, 0),
                "estimated_tax_krw": round(estimated_tax, 0),
            }
        )

    return {"accounts": statuses, "note": _ISA_STATUS_NOTE}


async def _calc_unrealized_by_account(account_ids: list[uuid.UUID], db: AsyncSession) -> dict[uuid.UUID, float]:
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

    unrealized_by_account: dict[uuid.UUID, float] = {}
    for snap in snapshots:
        if snap.account_id is None:
            continue
        total = 0.0
        for pos in snap.position_items:
            qty = float(pos.qty or 0)
            avg = float(pos.avg_price or 0)
            cur = float(pos.current_price or avg)
            total += (cur - avg) * qty
        unrealized_by_account[snap.account_id] = total
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
