"""정액 적립 해외 매수 환전 대기(WAITING_FX) leg 재매수 — 앱의 '다시 매수'와 30분 자동 재확인 잡(plans/120).

leg 잠금·실행·대기 진입/만료 헬퍼는 `plan_execution`에 있다. 그 헬퍼는 모듈 속성(`_pe.X`)으로 불러
테스트가 `plan_execution.X` 경로 하나로 patch한다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_runner import report_handled_failure
from app.exceptions import ConflictError, NotFoundError
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanLeg
from app.services.rebalancing import plan_execution as _pe
from app.services.rebalancing.usd_buying_power import UsdCheck, UsdLedger, UsdShortfall, UsdUnknown

FxRetryOutcome = Literal["EXECUTED", "FAILED", "SCHEDULED", "STILL_SHORT"]


async def retry_fx_waiting_leg(
    leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str
) -> tuple[FxRetryOutcome, uuid.UUID | None, RebalancingPlanLeg]:
    """앱의 '다시 매수' — 달러를 다시 확인해 충분하면 바로 사고(미국장 중), 장이 닫혀 있으면 다음 개장에 예약한다.

    반환: (결과, execution_id, 최신 leg). STILL_SHORT면 leg의 required/available_usd가 최신 값으로 갱신돼 있다.
    """
    from app.utils.market_hours import is_us_market_open, next_us_market_open

    if leg.status != "WAITING_FX":
        raise ConflictError(detail="환전 대기 중인 매수가 아닙니다")
    plan = await db.get(RebalancingPlan, leg.plan_id)
    if plan is None:
        raise NotFoundError(detail="계획을 찾을 수 없습니다")

    # 잔고 조회(토큰 발급 commit)는 잠그기 전에 — 잠근 뒤 상태를 다시 확인한다
    shortfall = await _pe._usd_shortfall_for_leg(leg, plan, db, cache)
    locked = await _pe._lock_leg(leg.id, db)
    if locked is None:
        raise NotFoundError(detail="계획을 찾을 수 없습니다")
    if locked.status != "WAITING_FX" or locked.token_consumed_at is not None:
        raise ConflictError(detail="이미 처리되었거나 만료된 계획입니다")
    if _pe._fx_wait_past_deadline(locked):
        await _pe._expire_fx_waiting_leg(locked, plan, db)
        raise ConflictError(detail="환전 대기 기한이 지나 이번 회차 해외 매수는 마감되었습니다")

    # 미확인(USD_UNKNOWN)이면 사용자가 환전했다고 누른 것이라 그대로 진행한다 — 증권사가 최종 판정
    if isinstance(shortfall, UsdShortfall):
        locked.required_usd = shortfall.required_usd
        locked.available_usd = shortfall.available_usd
        await db.commit()
        return "STILL_SHORT", None, locked

    if not is_us_market_open():
        _pe._resume_fx_waiting_leg(locked, next_us_market_open().astimezone(UTC))
        await _pe.save_alert_history(db, plan.user_id, "REBALANCING", "적립 해외 매수 재개 — 미국장 개장 시 매수")
        await db.commit()
        return "SCHEDULED", None, locked

    _pe._resume_fx_waiting_leg(locked, datetime.now(tz=UTC))
    # commit하면 락이 풀려 1분 매수 잡이 먼저 선점하고 사용자는 "이미 처리" 409를 받는다 — flush만 하고
    # 같은 트랜잭션의 락을 쥔 채 바로 선점한다(plans/122 B3)
    await db.flush()
    execution_id = await _pe._approve_leg_now(locked, db, cache, decided_by, expected_side="BUY")
    outcome: FxRetryOutcome = "EXECUTED" if locked.status == "EXECUTED" else "FAILED"
    return outcome, execution_id, locked


async def recheck_fx_waiting_legs(db: AsyncSession, cache) -> int:
    """환전 대기 leg 자동 재확인 — 기한이 지났으면 만료, 미국장 중이고 달러가 충분해졌으면 매수 대기로 되돌린다.

    되돌린 leg는 1분 매수 잡이 달러를 한 번 더 확인하고 실행한다. leg마다 실패를 격리한다.
    반환: 처리(만료 또는 재개)한 leg 수.
    """
    from app.models.alert import RebalancingAlert
    from app.utils.market_hours import is_us_market_open

    result = await db.execute(
        select(RebalancingPlanLeg.id).where(
            RebalancingPlanLeg.status == "WAITING_FX",
            RebalancingPlanLeg.token_consumed_at.is_(None),
        )
    )
    leg_ids = [row[0] for row in result.all()]
    market_open = is_us_market_open()
    processed = 0
    # 같은 계좌에서 기다리던 leg 둘을 같은 달러로 둘 다 재개하지 않는다(plans/129 B1)
    usd_ledger: UsdLedger = {}
    for leg_id in leg_ids:
        try:
            leg = await db.get(RebalancingPlanLeg, leg_id)
            if leg is None:
                continue
            plan = await db.get(RebalancingPlan, leg.plan_id)
            if not _pe._fx_wait_past_deadline(leg) and (not market_open or plan is None):
                continue
            shortfall: UsdCheck = None
            if not _pe._fx_wait_past_deadline(leg) and plan is not None:
                alert = await db.get(RebalancingAlert, plan.alert_id) if plan.alert_id else None
                # 알림이 정액 모드가 아니게 바뀌었으면 확인 없이 되돌린다 — 실행 경로가 기존 방식(증권사 판정)으로 처리
                if _pe._alert_is_dca(alert):
                    shortfall = await _pe._usd_shortfall_for_leg(leg, plan, db, cache, usd_ledger)
            locked = await _pe._lock_leg(leg_id, db)
            if locked is None or locked.status != "WAITING_FX" or locked.token_consumed_at is not None:
                await db.rollback()  # FOR UPDATE 락을 다음 leg까지 붙잡지 않게 바로 푼다
                continue
            if _pe._fx_wait_past_deadline(locked):
                await _pe._expire_fx_waiting_leg(locked, plan, db)
                processed += 1
                continue
            if plan is None:
                await db.rollback()
                continue
            if isinstance(shortfall, UsdUnknown):
                # 조회 실패를 "충분"으로 보고 재개하면 달러 없이 발주돼 FAILED로 끝난다 — 다음 주기에 다시 본다
                await db.rollback()
                continue
            if isinstance(shortfall, UsdShortfall):
                locked.required_usd = shortfall.required_usd
                locked.available_usd = shortfall.available_usd
                await db.commit()
                continue
            _pe._resume_fx_waiting_leg(locked, datetime.now(tz=UTC))
            await _pe.save_alert_history(db, plan.user_id, "REBALANCING", "적립 해외 매수 재개 — 달러 확인됨")
            await db.commit()
            processed += 1
        except Exception as e:
            report_handled_failure("dca_fx_wait_recheck_failed", e, leg_id=str(leg_id))
            await db.rollback()
    return processed
