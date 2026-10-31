"""AUTO 리밸런싱 2단계 플랜(계획 생성 → 매수 대기/매도 승인 → 실행) 서비스 — API 진입점.

책임별 서브모듈로 분리되어 있다(이 파일에는 조회·응답 요약 함수만 있다):
- `plan_generation.py` — 드리프트 분석 → 게이트 판정 → BUY/SELL leg 생성
- `plan_execution.py` — leg 잠금/실행/취소/만료 (앱 액션 + 스케줄러 job 진입점)
- `plan_notifications.py` — 플랜 생성/게이트 차단/leg 실행 결과 이메일·푸시·이력 알림

이 파일은 하위 호환을 위해 전체 심볼을 이름으로 재노출한다 — 라우터/job/테스트의
`from app.services.rebalancing.plan_service import X` 호출부는 변경 없이 그대로 유효하다.
단, 서브모듈 내부에서 발생하는 함수 간 호출(예: `plan_execution._execute_leg`가
`plan_notifications._notify_leg_execution_failed`를 호출하는 것)은 각 서브모듈의 import
바인딩을 통해 이뤄지므로, 이런 내부 호출을 가로채는 테스트 patch는 `plan_service.X`가 아닌
실제 호출부 서브모듈(`plan_execution.X`/`plan_notifications.X`) 경로를 사용해야 한다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanLeg
from app.schemas.rebalancing import RebalancingPlanItemOut, RebalancingPlanLegSummary
from app.services.rebalancing.plan_execution import (
    approve_buy_leg,
    approve_sell_leg,
    cancel_buy_leg,
    execute_due_buy_legs,
    expire_due_sell_legs,
    fail_stuck_consumed_legs,
    get_plan_leg_by_token,
    is_leg_past_deadline,
    reject_sell_leg,
)
from app.services.rebalancing.plan_generation import (
    DailyValueCapBlocked,
    MarketSignalGateBlocked,
    PlanGenerationInProgress,
    TaxGateBlocked,
    build_pending_plan_for_alert,
    generate_pending_plan_for_alert,
    get_alert_ids_with_pending_plan,
    has_pending_plan_for_alert,
    sum_today_auto_plan_value_krw,
)
from app.services.rebalancing.plan_notifications import (
    notify_daily_value_cap_blocked,
    notify_market_signal_gate_blocked,
    notify_plan_generated,
    notify_tax_gate_blocked,
)

__all__ = [
    "DailyValueCapBlocked",
    "MarketSignalGateBlocked",
    "PlanGenerationInProgress",
    "TaxGateBlocked",
    "approve_buy_leg",
    "approve_sell_leg",
    "build_leg_summary",
    "build_pending_plan_for_alert",
    "cancel_buy_leg",
    "execute_due_buy_legs",
    "expire_due_sell_legs",
    "fail_stuck_consumed_legs",
    "generate_pending_plan_for_alert",
    "get_alert_ids_with_pending_plan",
    "get_plan_leg_by_token",
    "has_pending_plan_for_alert",
    "is_leg_past_deadline",
    "executed_plan_ids",
    "list_recent_plan_legs",
    "notify_daily_value_cap_blocked",
    "notify_market_signal_gate_blocked",
    "notify_plan_generated",
    "notify_tax_gate_blocked",
    "reject_sell_leg",
    "sum_today_auto_plan_value_krw",
]

# 실행되지 않고 종료된 leg 상태 — 형제 leg가 체결됐다면 "반쪽 실행"이다(PENDING은 아직 진행 중이라 제외)
_TERMINAL_UNEXECUTED_STATUSES = {"FAILED", "EXPIRED", "REJECTED", "CANCELED"}


def build_leg_summary(
    leg: RebalancingPlanLeg,
    plan: RebalancingPlan,
    portfolio_name: str | None,
    account_name: str | None,
    sibling_executed: bool = False,
) -> RebalancingPlanLegSummary:
    """앱 플랜 목록과 이메일 토큰 미리보기가 같은 leg 요약을 쓴다."""
    return RebalancingPlanLegSummary(
        plan_id=plan.id,
        leg_id=leg.id,
        portfolio_id=plan.portfolio_id,
        portfolio_name=portfolio_name,
        account_id=plan.account_id,
        account_name=account_name,
        side=leg.side,
        status=leg.status,
        deadline_at=leg.deadline_at,
        decided_at=leg.decided_at,
        execution_id=leg.execution_id,
        error_message=leg.error_message,
        actionable=(leg.status == "PENDING" and not is_leg_past_deadline(leg)),
        partially_executed=sibling_executed and leg.status in _TERMINAL_UNEXECUTED_STATUSES,
        items=[RebalancingPlanItemOut.model_validate(item) for item in leg.items],
    )


async def list_recent_plan_legs(user_id: uuid.UUID, db: AsyncSession, limit: int = 30):
    """EXECUTED 제외(이미 실행 이력에 노출됨) 최근 leg 목록을 (leg, plan, portfolio_name, account_name) 튜플로 반환."""
    result = await db.execute(
        select(RebalancingPlanLeg, RebalancingPlan, Portfolio.name, AssetAccount.name)
        .join(RebalancingPlan, RebalancingPlan.id == RebalancingPlanLeg.plan_id)
        .outerjoin(Portfolio, Portfolio.id == RebalancingPlan.portfolio_id)
        .outerjoin(AssetAccount, AssetAccount.id == RebalancingPlan.account_id)
        .options(selectinload(RebalancingPlanLeg.items))
        .where(RebalancingPlan.user_id == user_id, RebalancingPlanLeg.status != "EXECUTED")
        .order_by(RebalancingPlanLeg.created_at.desc())
        .limit(limit)
    )
    return result.all()


async def executed_plan_ids(plan_ids: set[uuid.UUID], db: AsyncSession) -> set[uuid.UUID]:
    """주어진 플랜 중 EXECUTED leg가 하나라도 있는 플랜 id 집합.

    `list_recent_plan_legs`는 EXECUTED leg를 빼고 돌려주므로, 매도는 체결됐는데 매수가 실패/만료된
    "반쪽 실행" 플랜을 목록만으로는 알 수 없다 — 이 집합으로 형제 leg 체결 여부를 표시한다.
    """
    if not plan_ids:
        return set()
    result = await db.execute(
        select(RebalancingPlanLeg.plan_id)
        .where(RebalancingPlanLeg.plan_id.in_(plan_ids), RebalancingPlanLeg.status == "EXECUTED")
        .distinct()
    )
    return set(result.scalars().all())
