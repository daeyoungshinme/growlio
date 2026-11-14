"""리밸런싱 플랜 leg 정리 잡 — 결과 기록이 유실된 실행 중 leg 마감, 장마감 지난 매도 승인 만료.

leg 잠금·결정 헬퍼는 `plan_execution`에 있다. 모듈 속성(`_pe.X`)으로 불러 테스트가 `plan_execution.X`
경로 하나로 patch한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_runner import report_handled_failure
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanLeg
from app.services.rebalancing import plan_execution as _pe

# 실행 중(token_consumed_at만 찍힌 PENDING) 상태가 이보다 오래가면 결과 기록이 유실된 것으로 본다.
# 정상 실행은 수 초~수십 초(브로커 호출 + 이력 저장)라 넉넉히 둔다.
STUCK_LEG_TIMEOUT = timedelta(minutes=30)
STUCK_LEG_MESSAGE = "실행 결과를 확인하지 못했습니다. 증권사 앱에서 체결 내역을 확인하세요."


async def fail_stuck_consumed_legs(db: AsyncSession) -> int:
    """실행을 시작(토큰 소비)했지만 결과 기록이 유실돼 PENDING에 남은 leg를 FAILED로 마감한다.

    실패 경로 자체가 실패하면(프로세스 재시작, 세션 오류) leg는 token_consumed_at만 찍힌 PENDING으로 남고,
    실행·만료 경로가 모두 "이미 소비됨"으로 건너뛰어 영구히 열려 있게 된다. 실주문이 나갔을 수 있으므로
    재실행하지 않고 사용자에게 확인을 요청하는 알림만 보낸다.
    """
    cutoff = datetime.now(tz=UTC) - STUCK_LEG_TIMEOUT
    result = await db.execute(
        select(RebalancingPlanLeg.id).where(
            RebalancingPlanLeg.status == "PENDING",
            RebalancingPlanLeg.token_consumed_at.is_not(None),
            RebalancingPlanLeg.token_consumed_at <= cutoff,
        )
    )
    processed = 0
    for leg_id in [row[0] for row in result.all()]:
        try:
            locked = await _pe._lock_leg(leg_id, db)
            if locked is None or locked.status != "PENDING":
                await db.rollback()  # FOR UPDATE 락을 다음 leg 커밋까지 붙잡지 않게 바로 푼다
                continue
            side = locked.side
            _pe._decide_leg(locked, "FAILED", "SYSTEM_EXPIRY")
            locked.error_message = STUCK_LEG_MESSAGE
            plan = await db.get(RebalancingPlan, locked.plan_id)
            if plan:
                await _pe.save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 실행 결과 확인 필요")
            await db.commit()
            if plan:
                await _pe._notify_leg_execution_failed(plan, side, STUCK_LEG_MESSAGE, db)
            processed += 1
        except Exception as e:
            report_handled_failure("rebalancing_plan_stuck_leg_sweep_failed", e, leg_id=str(leg_id))
            await db.rollback()
    return processed


async def expire_due_sell_legs(db: AsyncSession) -> int:
    """당일 장마감 시각이 지난 PENDING SELL leg를 EXPIRED로 마감한다.

    실행 중(토큰 소비됨)인 leg는 건너뛴다 — 승인 직후 실행 중인 매도를 '미응답 만료'로 덮어쓰지 않게.
    결과 기록이 유실된 leg는 `fail_stuck_consumed_legs`가 마감한다.
    """
    now = datetime.now(tz=UTC)
    result = await db.execute(
        select(RebalancingPlanLeg.id).where(
            RebalancingPlanLeg.side == "SELL",
            RebalancingPlanLeg.status == "PENDING",
            RebalancingPlanLeg.token_consumed_at.is_(None),
            RebalancingPlanLeg.deadline_at <= now,
        )
    )
    due_leg_ids = [row[0] for row in result.all()]

    processed = 0
    for leg_id in due_leg_ids:
        try:
            locked = await _pe._lock_leg(leg_id, db)
            if locked is None or locked.status != "PENDING" or locked.token_consumed_at is not None:
                await db.rollback()  # FOR UPDATE 락을 다음 leg 커밋까지 붙잡지 않게 바로 푼다
                continue
            _pe._decide_leg(locked, "EXPIRED", "SYSTEM_EXPIRY", at=now)
            plan = await db.get(RebalancingPlan, locked.plan_id)
            if plan:
                await _pe.save_alert_history(
                    db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매도 승인 만료 (장마감 미응답)"
                )
            await db.commit()
            processed += 1
        except Exception as e:
            report_handled_failure("rebalancing_plan_sell_expiry_leg_failed", e, leg_id=str(leg_id))
            await db.rollback()

    return processed
