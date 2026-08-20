"""AUTO 리밸런싱 플랜 leg 잠금/실행/취소/만료 — 앱 액션 및 스케줄러 job 진입점.

`plan_service.py`(구 단일 파일, 1025줄)에서 분리된 서브모듈. 매수는 대기시간 경과 후
자동 실행(취소 가능), 매도는 이메일 승인 필요(당일 장마감 미응답 시 자동 만료)라는
leg별 독립 생명주기를 관리한다.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanItem, RebalancingPlanLeg
from app.services.alerts.alert_service import save_alert_history
from app.services.rebalancing.plan_notifications import _notify_leg_execution_failed, _send_leg_execution_email

logger = structlog.get_logger()


async def get_plan_leg_by_token(
    raw_token: str, expected_side: Literal["BUY", "SELL"] | None, db: AsyncSession
) -> RebalancingPlanLeg | None:
    """토큰 해시 매치로 leg를 조회한다. 읽기 전용 — DB를 변경하지 않는다."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    leg = await db.scalar(
        select(RebalancingPlanLeg)
        .options(selectinload(RebalancingPlanLeg.items), selectinload(RebalancingPlanLeg.plan))
        .where(RebalancingPlanLeg.action_token_hash == token_hash)
    )
    if leg is None:
        return None
    if expected_side is not None and leg.side != expected_side:
        return None
    return leg


async def _lock_and_claim(leg_id: uuid.UUID, db: AsyncSession) -> RebalancingPlanLeg:
    """leg를 FOR UPDATE로 잠그고 PENDING/미소비 상태를 확인한 뒤 토큰을 즉시 소비 처리한다.

    상태(status)는 아직 바꾸지 않고 token_consumed_at만 먼저 커밋해, 이후 실제 실행(수 초 소요될
    수 있는 브로커 API 호출) 도중 들어오는 중복 요청도 이 시점 이후로는 확실히 차단한다.
    """
    locked = await db.scalar(select(RebalancingPlanLeg).where(RebalancingPlanLeg.id == leg_id).with_for_update())
    if locked is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다")
    if locked.status != "PENDING" or locked.token_consumed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 처리되었거나 만료된 계획입니다")
    locked.token_consumed_at = datetime.now(tz=UTC)
    await db.commit()
    await db.refresh(locked)
    return locked


async def cancel_buy_leg(leg: RebalancingPlanLeg, db: AsyncSession, decided_by: str) -> None:
    locked = await _lock_and_claim(leg.id, db)
    locked.status = "CANCELED"
    locked.decided_at = datetime.now(tz=UTC)
    locked.decided_by = decided_by
    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan:
        await save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매수 대기 취소")
    await db.commit()


async def reject_sell_leg(leg: RebalancingPlanLeg, db: AsyncSession, decided_by: str) -> None:
    locked = await _lock_and_claim(leg.id, db)
    locked.status = "REJECTED"
    locked.decided_at = datetime.now(tz=UTC)
    locked.decided_by = decided_by
    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan:
        await save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매도 계획 거부")
    await db.commit()


async def _rebuild_orders_from_items(
    items: list[RebalancingPlanItem],
    side: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    cache,
) -> list:
    """플랜 아이템으로부터 실행 주문을 재구성한다.

    수량은 계획 생성 시점 값을 그대로 사용(재계산 안 함). LIMIT 주문만 실행 직전 가격을 다시
    조회해 limit_price를 갱신한다 — 그 사이 대기시간 동안 벌어진 가격 변동을 반영하기 위함.
    """
    from app.schemas.rebalancing import ExecutionOrderItem
    from app.services.price_service import fetch_prices_batch

    limit_tickers = [(item.ticker, item.market or "") for item in items if item.order_type == "LIMIT" and item.ticker]
    price_map: dict[str, float] = {}
    if limit_tickers:
        try:
            price_map = await fetch_prices_batch(user_id, limit_tickers, db, cache)
        except Exception as exc:
            logger.warning("rebalancing_plan_limit_price_refresh_failed", error=str(exc))

    orders: list[ExecutionOrderItem] = []
    for item in items:
        limit_price = float(item.limit_price) if item.limit_price is not None else None
        if item.order_type == "LIMIT":
            fresh = price_map.get(item.ticker or "")
            if fresh and fresh > 0:
                limit_price = float(fresh)
        orders.append(
            ExecutionOrderItem(
                ticker=item.ticker or "",
                name=item.name or item.ticker or "",
                market=item.market or "",
                side=side,
                quantity=item.quantity,
                account_id=item.account_id,
                order_type=item.order_type,
                limit_price=limit_price,
                reference_price=float(item.reference_price) if item.reference_price is not None else None,
            )
        )
    return orders


async def _execute_leg(
    locked: RebalancingPlanLeg, plan: RebalancingPlan, db: AsyncSession, cache, decided_by: str
) -> uuid.UUID | None:
    """잠긴(claim된) leg의 아이템으로 실제 주문을 실행하고 상태를 최종 반영한다."""
    from app.services.rebalancing.execution_service import execute_rebalancing

    await db.refresh(locked, attribute_names=["items"])
    orders = await _rebuild_orders_from_items(locked.items, locked.side, plan.user_id, db, cache)

    try:
        _results, execution_id = await execute_rebalancing(
            user_id=plan.user_id,
            account_id=plan.account_id,
            orders=orders,
            db=db,
            cache=cache,
            portfolio_id=plan.portfolio_id,
            triggered_by="AUTO",
            strategy=plan.strategy,
        )
    except Exception as exc:
        logger.error("rebalancing_plan_leg_execute_failed", leg_id=str(locked.id), error=str(exc))
        locked.status = "FAILED"
        locked.error_message = str(exc)
        locked.decided_at = datetime.now(tz=UTC)
        locked.decided_by = decided_by
        await save_alert_history(
            db, plan.user_id, "REBALANCING", f"리밸런싱 자동화 {'매수' if locked.side == 'BUY' else '매도'} 실행 실패"
        )
        await db.commit()
        await _notify_leg_execution_failed(plan, locked.side, str(exc), db)
        return None

    locked.status = "EXECUTED"
    locked.execution_id = execution_id
    locked.decided_at = datetime.now(tz=UTC)
    locked.decided_by = decided_by
    await db.commit()
    return execution_id


async def _approve_leg_now(
    leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str, expected_side: Literal["BUY", "SELL"]
) -> uuid.UUID | None:
    """PENDING leg를 잠그고 즉시 실행한다 — BUY/SELL 공용 (앱에서 대기시간을 건너뛰고 즉시 체결할 때 사용)."""
    locked = await _lock_and_claim(leg.id, db)
    if locked.side != expected_side:
        label = "매도" if expected_side == "SELL" else "매수"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} 계획이 아닙니다")
    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다")

    execution_id = await _execute_leg(locked, plan, db, cache, decided_by)
    if execution_id:
        await _send_leg_execution_email(plan, execution_id, db)
    return execution_id


async def approve_sell_leg(leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str) -> uuid.UUID | None:
    return await _approve_leg_now(leg, db, cache, decided_by, expected_side="SELL")


async def approve_buy_leg(leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str) -> uuid.UUID | None:
    """대기중인 매수 leg를 앱에서 즉시 실행한다 — 대기시간(buy_wait_minutes) 경과를 기다리지 않고 바로 체결."""
    return await _approve_leg_now(leg, db, cache, decided_by, expected_side="BUY")


async def execute_due_buy_legs(db: AsyncSession, cache) -> int:
    """대기시간이 지난 PENDING BUY leg를 실행한다. 대기 중 장마감을 넘겼으면 EXPIRED 처리(익일 이월 안 함).

    실행 직전 시장 신호 게이트를 다시 확인한다 — 계획 생성 시점엔 안전했더라도 대기시간(수 분~수십 분)
    동안 시장 상황이 악화될 수 있어서다(계획 생성 시점 1회만 확인하던 기존 동작의 공백). 차단되면
    leg는 PENDING으로 남아 다음 tick(1분 간격)에 재시도되고, 장마감까지 계속 막히면 위 EXPIRED 처리로
    자연 정리된다 — 별도 알림 없이 조용히 보류(계획 생성 자체를 건너뛰는 시장신호 게이트와 동일한 정책).
    """
    from app.models.alert import RebalancingAlert
    from app.services.rebalancing.order_builder import is_market_signal_blocking_auto_mode
    from app.utils.market_hours import is_korean_market_open, is_us_market_open

    now = datetime.now(tz=UTC)
    result = await db.execute(
        select(RebalancingPlanLeg.id).where(
            RebalancingPlanLeg.side == "BUY",
            RebalancingPlanLeg.status == "PENDING",
            RebalancingPlanLeg.deadline_at <= now,
        )
    )
    due_leg_ids = [row[0] for row in result.all()]
    if not due_leg_ids:
        return 0

    from app.services.market_signal_service import get_confirmed_composite_level

    composite_level, data_freshness = await get_confirmed_composite_level(cache, db)

    processed = 0
    for leg_id in due_leg_ids:
        locked = await db.scalar(select(RebalancingPlanLeg).where(RebalancingPlanLeg.id == leg_id).with_for_update())
        if locked is None or locked.status != "PENDING" or locked.token_consumed_at is not None:
            continue

        market_open = is_korean_market_open() if locked.market == "KR" else is_us_market_open()
        if not market_open:
            locked.status = "EXPIRED"
            locked.error_message = "market_closed_before_execution"
            locked.decided_at = now
            locked.decided_by = "SYSTEM_AUTO"
            await db.commit()
            processed += 1
            continue

        plan = await db.get(RebalancingPlan, locked.plan_id)
        if plan is None:
            continue

        plan_alert_id = getattr(plan, "alert_id", None)
        alert = await db.get(RebalancingAlert, plan_alert_id) if plan_alert_id else None
        market_mode = getattr(alert, "market_condition_mode", "DISABLED")
        if is_market_signal_blocking_auto_mode(market_mode, composite_level, data_freshness):
            logger.info(
                "rebalancing_plan_buy_execution_skipped_market_signal",
                leg_id=str(locked.id),
                composite_level=composite_level,
                data_freshness=data_freshness,
            )
            continue

        locked.token_consumed_at = now
        await db.commit()

        execution_id = await _execute_leg(locked, plan, db, cache, "SYSTEM_AUTO")
        if execution_id:
            await _send_leg_execution_email(plan, execution_id, db)
        processed += 1

    return processed


async def expire_due_sell_legs(db: AsyncSession) -> int:
    """당일 장마감 시각이 지난 PENDING SELL leg를 EXPIRED로 마감한다."""
    now = datetime.now(tz=UTC)
    result = await db.execute(
        select(RebalancingPlanLeg.id).where(
            RebalancingPlanLeg.side == "SELL",
            RebalancingPlanLeg.status == "PENDING",
            RebalancingPlanLeg.deadline_at <= now,
        )
    )
    due_leg_ids = [row[0] for row in result.all()]

    processed = 0
    for leg_id in due_leg_ids:
        locked = await db.scalar(select(RebalancingPlanLeg).where(RebalancingPlanLeg.id == leg_id).with_for_update())
        if locked is None or locked.status != "PENDING":
            continue
        locked.status = "EXPIRED"
        locked.decided_at = now
        locked.decided_by = "SYSTEM_EXPIRY"
        plan = await db.get(RebalancingPlan, locked.plan_id)
        if plan:
            await save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매도 승인 만료 (장마감 미응답)")
        await db.commit()
        processed += 1

    return processed
