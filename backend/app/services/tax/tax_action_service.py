"""절세 액션 플랜 — "언제·얼마를·어느 계좌에 하면 얼마 아낀다"를 실행 가능한 액션 목록으로 조합한다.

계산은 기존 도메인 서비스(pension_contribution_service/isa_service/tax_service)에 위임하고 이 모듈은
조합·우선순위화만 한다. 연말 절세 리마인더(alerts/tax_reminder_service)도 같은 액션 목록을 재사용한다.

- 세법 수치·우선순위·액션 빌더(순수 계산)는 `tax_action_builders.py`.
- 이익실현(A4)·손실수확(A5)은 정보 제공형 문구만 쓰고 자동 주문과 연결하지 않는다(AUTO 파이프라인과 분리).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount
from app.models.user import UserSettings
from app.services.tax.isa_service import (
    calc_isa_contribution_status,
    get_isa_status_summary,
)
from app.services.tax.overseas_realized_service import get_overseas_realized_summary
from app.services.tax.pension_contribution_service import calc_pension_contribution_status
from app.services.tax.tax_action_builders import (
    _ACTION_PLAN_NOTE,
    TaxAction,
    TaxActionPlan,
    _get_rules,
    _sort_actions,
    build_financial_income_action,
    build_isa_contribution_actions,
    build_isa_transfer_actions,
    build_loss_harvest_actions,
    build_overseas_gain_harvest_action,
    build_pension_action,
    pension_credit_rate,
)
from app.services.tax.tax_service import get_tax_summary, load_tax_stock_rows
from app.utils.kst import today_kst


async def _get_account_tax_types(user_id: uuid.UUID, db: AsyncSession) -> set[str]:
    result = await db.execute(
        select(AssetAccount.tax_type)
        .where(AssetAccount.user_id == user_id, AssetAccount.is_active == True, AssetAccount.tax_type.is_not(None))
        .distinct()
    )
    return {row[0] for row in result.all()}


async def _get_income_bracket(user_id: uuid.UUID, db: AsyncSession) -> str | None:
    result = await db.execute(select(UserSettings.income_bracket).where(UserSettings.user_id == user_id))
    return result.scalar()


async def get_tax_action_plan(user_id: uuid.UUID, year: int, db: AsyncSession) -> TaxActionPlan:
    """연도별 절세 액션 플랜. 도메인 서비스를 순차 호출한다(같은 AsyncSession 동시 사용 금지)."""
    plan, _ = await get_tax_action_plan_with_summary(user_id, year, db)
    return plan


async def get_tax_action_plan_with_summary(
    user_id: uuid.UUID, year: int, db: AsyncSession
) -> tuple[TaxActionPlan, dict[str, Any]]:
    """액션 플랜 + 그 계산에 쓴 세금 추정 요약(`get_tax_summary`) — 홈 "지금 할 일"이 세금 경고를 위해
    요약을 다시 계산하지 않도록 함께 돌려준다."""
    today = today_kst()
    rules = _get_rules(year)
    income_bracket = await _get_income_bracket(user_id, db)
    rate = pension_credit_rate(income_bracket, rules)
    tax_types = await _get_account_tax_types(user_id, db)

    actions: list[TaxAction] = []

    # 스냅샷은 한 번만 읽어 ISA 평가액·실현손익(포지션)·세금 요약(행)에 넘긴다
    rows, positions = await load_tax_stock_rows(user_id, db)

    has_ps = "PENSION_SAVINGS" in tax_types
    has_irp = "IRP" in tax_types
    if has_ps or has_irp:
        pension = await calc_pension_contribution_status(user_id, year, db)
        pension_action = build_pension_action(pension, has_ps, has_irp, rate, income_bracket, today)
        if pension_action:
            actions.append(pension_action)

    if "ISA" in tax_types:
        isa = await get_isa_status_summary(user_id, db)
        balances = {str(acc.id): float(snap.amount_krw or 0) for snap, acc in rows}
        actions.extend(build_isa_transfer_actions(isa["accounts"], rules, rate, income_bracket, today, balances))
        isa_contrib = await calc_isa_contribution_status(user_id, year, db)
        actions.extend(build_isa_contribution_actions(isa_contrib, today))

    realized = await get_overseas_realized_summary(user_id, year, db, overseas_positions=positions)
    tax_summary = await get_tax_summary(
        user_id, year, db, overseas_realized_krw=realized["realized_gain_krw"], stock_rows=rows
    )
    deduction_krw = float(tax_summary["overseas_gain_deduction_krw"])
    gain_tax_rate = float(tax_summary["rates"]["overseas_tax_rate_pct"]) / 100
    # 캐시된 예전 응답에는 lookup_failed가 없다(실패 결과는 캐시하지 않으므로 없으면 성공)
    lookup_failed = bool(realized.get("lookup_failed", False))
    gain_action = build_overseas_gain_harvest_action(
        positions,
        deduction_krw,
        gain_tax_rate,
        today,
        realized_krw=realized["realized_gain_krw"],
        realized_partial=realized["source"] == "PARTIAL",
        # 캐시된 예전 응답에는 method/estimated가 없다
        realized_from_records=any(a.get("method") == "TRADE_RECORD" for a in realized["covered_accounts"]),
        realized_estimated=any(a.get("estimated", False) for a in realized["covered_accounts"]),
        realized_lookup_failed=lookup_failed,
    )
    if gain_action:
        actions.append(gain_action)
    actions.extend(
        build_loss_harvest_actions(
            tax_summary.get("harvesting_recommendations", []),
            today,
            realized_krw=None if lookup_failed else realized["realized_gain_krw"],
            deduction_krw=deduction_krw,
            gain_tax_rate=gain_tax_rate,
        )
    )
    financial_action = build_financial_income_action(tax_summary, today)
    if financial_action:
        actions.append(financial_action)

    plan: TaxActionPlan = {
        "year": year,
        "income_bracket": income_bracket,
        "actions": _sort_actions(actions),
        "note": _ACTION_PLAN_NOTE,
    }
    return plan, tax_summary
