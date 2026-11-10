"""AUTO 리밸런싱 플랜 leg 잠금/실행/취소/만료 — 앱 액션 및 스케줄러 job 진입점.

매수는 대기시간 경과 후 자동 실행(취소 가능), 매도는 이메일 승인 필요(당일 장마감 미응답 시 자동 만료)라는
leg별 독립 생명주기를 관리한다.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.job_runner import report_handled_failure
from app.core.logging import public_error_message
from app.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanItem, RebalancingPlanLeg
from app.services.alerts.alert_service import save_alert_history
from app.services.rebalancing.order_builder import market_group
from app.services.rebalancing.plan_notifications import (
    _notify_buy_leg_expired,
    _notify_leg_execution_failed,
    _send_leg_execution_email,
)
from app.services.rebalancing.usd_buying_power import USD_UNKNOWN, UsdCheck, UsdShortfall, UsdUnknown
from app.utils.numbers import opt_float

logger = structlog.get_logger()

_OPEN_BUY_STATUSES: tuple[str, ...] = ("PENDING", "WAITING_FX")
FX_WAIT_WEEKDAYS = 5
"""환전 대기 leg를 자동 재확인하는 기간(평일 수) — 지나면 이번 회차 해외 매수를 만료로 마감한다."""
FX_WAIT_EXPIRED_MESSAGE = "fx_wait_expired"

AUTOMATION_OFF_DECIDED_BY = "USER_AUTOMATION_OFF"
NO_ORDER_SUCCEEDED_MESSAGE = "체결된 주문이 없습니다."
HISTORY_MISSING_MESSAGE = "주문은 실행됐지만 실행 기록 저장에 실패했습니다. 증권사 앱에서 체결 내역을 확인하세요."


def leg_executed_message(label: str, execution_id: uuid.UUID | None) -> str:
    """승인 즉시 실행 응답 문구 — 기록 저장 실패(execution_id 없음)면 체결 확인을 안내한다."""
    if execution_id is None:
        return f"{label} 주문이 실행되었지만 실행 기록 저장에 실패했습니다. 증권사 앱에서 체결 내역을 확인하세요."
    return f"{label} 주문이 실행되었습니다"


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


def is_leg_past_deadline(leg: RebalancingPlanLeg) -> bool:
    """deadline_at(naive면 UTC로 간주)이 지났는지."""
    deadline = leg.deadline_at if leg.deadline_at.tzinfo else leg.deadline_at.replace(tzinfo=UTC)
    return datetime.now(tz=UTC) >= deadline


async def _lock_leg(leg_id: uuid.UUID, db: AsyncSession) -> RebalancingPlanLeg | None:
    # 호출자가 같은 세션에서 leg를 먼저 읽었을 수 있다 — populate_existing 없이는 락을 기다린 뒤에도 세션에 남은
    # 옛 값(token_consumed_at=None)으로 판정해 동시 승인이 둘 다 통과하고 주문이 두 번 나간다
    return await db.scalar(
        select(RebalancingPlanLeg)
        .where(RebalancingPlanLeg.id == leg_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _decide_leg(leg: RebalancingPlanLeg, status: str, decided_by: str, at: datetime | None = None) -> None:
    """leg를 종료 상태로 바꾼다(결정 시각·주체 기록). commit은 호출자가 한다."""
    leg.status = status
    leg.decided_at = at or datetime.now(tz=UTC)
    leg.decided_by = decided_by


async def _lock_and_claim(
    leg_id: uuid.UUID, db: AsyncSession, allowed_statuses: tuple[str, ...] = ("PENDING",)
) -> RebalancingPlanLeg:
    """leg를 FOR UPDATE로 잠그고 PENDING/미소비 상태를 확인한 뒤 토큰을 즉시 소비 처리한다.

    상태(status)는 아직 바꾸지 않고 token_consumed_at만 먼저 커밋해, 이후 실제 실행(수 초 소요될
    수 있는 브로커 API 호출) 도중 들어오는 중복 요청도 이 시점 이후로는 확실히 차단한다.
    """
    locked = await _lock_leg(leg_id, db)
    if locked is None:
        raise NotFoundError(detail="계획을 찾을 수 없습니다")
    if locked.status not in allowed_statuses or locked.token_consumed_at is not None:
        raise ConflictError(detail="이미 처리되었거나 만료된 계획입니다")
    locked.token_consumed_at = datetime.now(tz=UTC)
    await db.commit()
    await db.refresh(locked)
    return locked


async def _decline_leg(
    leg: RebalancingPlanLeg,
    db: AsyncSession,
    decided_by: str,
    new_status: str,
    history_message: str,
    allowed_statuses: tuple[str, ...] = ("PENDING",),
) -> None:
    locked = await _lock_and_claim(leg.id, db, allowed_statuses)
    _decide_leg(locked, new_status, decided_by)
    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan:
        await save_alert_history(db, plan.user_id, "REBALANCING", history_message)
    await db.commit()


async def cancel_buy_leg(leg: RebalancingPlanLeg, db: AsyncSession, decided_by: str) -> None:
    # 환전 대기(WAITING_FX) 매수도 사용자가 이번 회차를 건너뛸 수 있다
    await _decline_leg(
        leg, db, decided_by, "CANCELED", "리밸런싱 자동화 매수 대기 취소", allowed_statuses=_OPEN_BUY_STATUSES
    )


async def reject_sell_leg(leg: RebalancingPlanLeg, db: AsyncSession, decided_by: str) -> None:
    await _decline_leg(leg, db, decided_by, "REJECTED", "리밸런싱 자동화 매도 계획 거부")


async def cancel_pending_buy_legs(
    db: AsyncSession,
    *,
    alert_id: uuid.UUID | None = None,
    portfolio_id: uuid.UUID | None = None,
) -> int:
    """자동화를 끈(알림 삭제·AUTO 해제·포트폴리오 삭제) 쪽의 대기 매수 leg를 취소한다. commit은 호출자가 한다.

    매수 leg는 승인 없이 대기시간 뒤 실행되고, 알림이 지워지면 FK가 SET NULL이 되어 시장 게이트까지 DISABLED로
    풀린 채 주문이 나간다 — 그래서 알림을 지우기 전에 같은 트랜잭션에서 취소한다. 실행이 시작된(토큰 소비) leg는
    이미 주문이 나갔을 수 있어 건드리지 않고, 매도 leg는 어차피 사용자 승인이 있어야 실행되므로 그대로 둔다.
    """
    condition = (
        RebalancingPlan.alert_id == alert_id if alert_id is not None else RebalancingPlan.portfolio_id == portfolio_id
    )
    result = await db.execute(
        select(RebalancingPlanLeg.id, RebalancingPlan.user_id)
        .join(RebalancingPlan, RebalancingPlan.id == RebalancingPlanLeg.plan_id)
        .where(
            condition,
            RebalancingPlanLeg.side == "BUY",
            RebalancingPlanLeg.status.in_(_OPEN_BUY_STATUSES),
            RebalancingPlanLeg.token_consumed_at.is_(None),
        )
    )
    canceled = 0
    for leg_id, user_id in result.all():
        locked = await _lock_leg(leg_id, db)
        if locked is None or locked.status not in _OPEN_BUY_STATUSES or locked.token_consumed_at is not None:
            continue
        _decide_leg(locked, "CANCELED", AUTOMATION_OFF_DECIDED_BY)
        await save_alert_history(db, user_id, "REBALANCING", "리밸런싱 자동화 해제로 대기 중이던 매수 취소")
        canceled += 1
    return canceled


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
    from app.services.market_data.price_service import fetch_prices_batch

    limit_tickers = [(item.ticker, item.market or "") for item in items if item.order_type == "LIMIT" and item.ticker]
    price_map: dict[str, float] = {}
    if limit_tickers:
        try:
            price_map = await fetch_prices_batch(user_id, limit_tickers, db, cache)
        except Exception as exc:
            logger.warning("rebalancing_plan_limit_price_refresh_failed", error=str(exc))

    orders: list[ExecutionOrderItem] = []
    for item in items:
        limit_price = opt_float(item.limit_price)
        if item.order_type == "LIMIT":
            fresh = price_map.get(item.ticker or "")
            if fresh and fresh > 0:
                limit_price = float(fresh)
            elif market_group(item.market or "") == "US":
                # 저장된 limit_price는 원화(확인 페이지·이메일 표시용)라 해외 주문(USD)에 그대로 쓸 수 없다 —
                # 현지통화 시세를 못 받으면 지정가를 정할 수 없으므로 주문하지 않는다(leg FAILED + 알림).
                raise ValueError(f"{item.ticker} 해외 현재가 조회에 실패해 지정가를 정할 수 없어 주문하지 않았습니다.")
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
                reference_price=opt_float(item.reference_price),
            )
        )
    return orders


def _no_order_succeeded(results: list) -> bool:
    """주문을 시도했지만 한 건도 접수되지 않았는지 — 부분 체결은 자금이 움직였으므로 해당 없음."""
    orders = [order for result in results for order in result.orders]
    return bool(orders) and not any(order.status == "SUCCESS" for order in orders)


async def _fail_leg_without_fills(
    locked: RebalancingPlanLeg,
    plan: RebalancingPlan,
    results: list,
    execution_id: uuid.UUID | None,
    db: AsyncSession,
    decided_by: str,
) -> None:
    """전 주문 실패 leg를 FAILED로 마감한다 — EXECUTED로 두면 일일 거래한도에 합산돼 이후 플랜까지 막힌다."""
    if execution_id is None:
        await db.refresh(plan)
    reason = next(
        (order.error_msg for result in results for order in result.orders if order.error_msg),
        NO_ORDER_SUCCEEDED_MESSAGE,
    )
    _decide_leg(locked, "FAILED", decided_by)
    locked.execution_id = execution_id
    locked.error_message = reason
    await save_alert_history(
        db, plan.user_id, "REBALANCING", f"리밸런싱 자동화 {'매수' if locked.side == 'BUY' else '매도'} 실행 실패"
    )
    await db.commit()
    await _notify_leg_execution_failed(plan, locked.side, reason, db)


async def _execute_leg(
    locked: RebalancingPlanLeg, plan: RebalancingPlan, db: AsyncSession, cache, decided_by: str
) -> uuid.UUID | None:
    """잠긴(claim된) leg의 아이템으로 실제 주문을 실행하고 상태를 최종 반영한다."""
    from app.services.rebalancing.execution_service import execute_rebalancing

    await db.refresh(locked, attribute_names=["items"])

    try:
        orders = await _rebuild_orders_from_items(locked.items, locked.side, plan.user_id, db, cache)
        results, execution_id = await execute_rebalancing(
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
        report_handled_failure("rebalancing_plan_leg_execute_failed", exc, leg_id=str(locked.id))
        reason = public_error_message(exc)
        # 원인이 DB 오류면 세션이 실패 상태라 rollback 없이는 FAILED 커밋도 PendingRollbackError로 깨지고, leg는
        # token_consumed_at만 찍힌 PENDING으로 영구히 남는다(어떤 경로도 다시 집지 않음). 주문 그룹 예외는
        # execute_rebalancing 안에서 잡히므로 여기 오는 건 주문 재구성·이력 저장 실패라 버릴 미커밋 변경도 없다.
        await db.rollback()
        await db.refresh(locked)
        await db.refresh(plan)
        _decide_leg(locked, "FAILED", decided_by)
        locked.error_message = reason
        await save_alert_history(
            db, plan.user_id, "REBALANCING", f"리밸런싱 자동화 {'매수' if locked.side == 'BUY' else '매도'} 실행 실패"
        )
        await db.commit()
        await _notify_leg_execution_failed(plan, locked.side, reason, db)
        return None

    if execution_id is None:
        # 주문은 나갔지만 실행 기록 저장이 실패해 세션이 rollback됐다(만료된 객체 재조회) — FAILED로 두면
        # 실제 체결과 어긋나므로 EXECUTED로 기록하되 확인 안내를 남긴다(plans/62 A7)
        await db.refresh(locked)
        locked.error_message = HISTORY_MISSING_MESSAGE
    if _no_order_succeeded(results):
        await _fail_leg_without_fills(locked, plan, results, execution_id, db, decided_by)
        return None
    _decide_leg(locked, "EXECUTED", decided_by)
    locked.execution_id = execution_id
    await db.commit()
    return execution_id


async def _approve_leg_now(
    leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str, expected_side: Literal["BUY", "SELL"]
) -> uuid.UUID | None:
    """PENDING leg를 잠그고 즉시 실행한다 — BUY/SELL 공용 (앱에서 대기시간을 건너뛰고 즉시 체결할 때 사용)."""
    locked = await _lock_and_claim(leg.id, db)
    if locked.side != expected_side:
        label = "매도" if expected_side == "SELL" else "매수"
        raise BadRequestError(detail=f"{label} 계획이 아닙니다")
    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan is None:
        raise NotFoundError(detail="계획을 찾을 수 없습니다")

    # 매도 deadline_at은 당일 장마감 승인 기한이다 — 만료 job(15분 주기)이 돌기 전에 들어온 승인도
    # 기한이 지났으면 실행하지 않고 만료로 마감한다(plans/62 A4). 매수 deadline_at은 실행 예정 시각이라 해당 없음.
    if locked.side == "SELL" and is_leg_past_deadline(locked):
        _decide_leg(locked, "EXPIRED", "SYSTEM_EXPIRY")
        await save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매도 승인 만료 (장마감 미응답)")
        await db.commit()
        raise ConflictError(detail="승인 기한(장마감)이 지나 만료된 계획입니다")

    execution_id = await _execute_leg(locked, plan, db, cache, decided_by)
    if execution_id:
        await _send_leg_execution_email(plan, execution_id, db)
    return execution_id


async def approve_sell_leg(leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str) -> uuid.UUID | None:
    return await _approve_leg_now(leg, db, cache, decided_by, expected_side="SELL")


async def approve_buy_leg(leg: RebalancingPlanLeg, db: AsyncSession, cache, decided_by: str) -> uuid.UUID | None:
    """대기중인 매수 leg를 앱에서 즉시 실행한다 — 대기시간(buy_wait_minutes) 경과를 기다리지 않고 바로 체결.

    그 시장이 닫혀 있으면 거부한다 — 닫힌 장에 낸 지정가는 증권사가 거부해 leg가 FAILED로 끝나고, 개장 시
    자동 매수될 기회까지 잃는다(정액 적립 해외 leg는 다음 미국장 개장까지 하루 종일 승인 버튼이 보인다, plans/122 B2).
    """
    from app.utils.market_hours import is_korean_market_open, is_us_market_open

    if leg.side == "BUY":
        if leg.market == "US" and not is_us_market_open():
            raise ConflictError(detail="미국장이 닫혀 있어 지금 매수할 수 없습니다. 개장하면 예정대로 매수합니다")
        if leg.market == "KR" and not is_korean_market_open():
            raise ConflictError(detail="국내장이 닫혀 있어 지금 매수할 수 없습니다")
    return await _approve_leg_now(leg, db, cache, decided_by, expected_side="BUY")


async def execute_due_buy_legs(db: AsyncSession, cache) -> int:
    """대기시간이 지난 PENDING BUY leg를 실행한다. 대기 중 장마감을 넘겼으면 EXPIRED 처리(익일 이월 안 함).

    실행 직전 시장 신호 게이트를 다시 확인한다 — 계획 생성 시점엔 안전했더라도 대기시간(수 분~수십 분)
    동안 시장 상황이 악화될 수 있어서다(계획 생성 시점 1회만 확인하던 기존 동작의 공백). 차단되면
    leg는 PENDING으로 남아 다음 tick(1분 간격)에 재시도되고, 장마감까지 계속 막히면 위 EXPIRED 처리로
    자연 정리된다 — 별도 알림 없이 조용히 보류(계획 생성 자체를 건너뛰는 시장신호 게이트와 동일한 정책).
    """
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

    from app.services.market_signal.market_signal_service import get_confirmed_composite_level

    composite_level, data_freshness = await get_confirmed_composite_level(cache, db)

    processed = 0
    for leg_id in due_leg_ids:
        # leg마다 격리 — 한 건의 예외(DB 오류 등)가 같은 tick의 나머지 leg를 막지 않게
        try:
            if await _run_due_buy_leg(leg_id, now, composite_level, data_freshness, db, cache):
                processed += 1
        except Exception as e:
            report_handled_failure("rebalancing_plan_buy_leg_tick_failed", e, leg_id=str(leg_id))
            await db.rollback()

    return processed


async def _run_due_buy_leg(
    leg_id: uuid.UUID, now: datetime, composite_level, data_freshness, db: AsyncSession, cache
) -> bool:
    """대기시간이 지난 BUY leg 1건을 만료·보류·실행한다. 처리(만료 또는 실행)했으면 True."""
    from app.models.alert import RebalancingAlert
    from app.services.rebalancing.order_builder import is_alert_blocked_by_market_gate
    from app.utils.market_hours import is_korean_market_open, is_us_market_open

    locked = await _lock_leg(leg_id, db)
    if locked is None or locked.status != "PENDING" or locked.token_consumed_at is not None:
        return False

    market_open = is_korean_market_open() if locked.market == "KR" else is_us_market_open()
    if not market_open and locked.fx_retry_until is not None and not _fx_wait_past_deadline(locked):
        # 환전 대기에서 재개된 leg — 서버 슬립·장마감 경계·시장 게이트로 장 안에 못 샀어도 기한이 남았으면
        # 만료하지 않고 대기로 되돌린다. 다음 미국장 재확인(30분 잡)이 다시 재개한다(plans/122 A3)
        locked.status = "WAITING_FX"
        await db.commit()
        return True
    if not market_open:
        _decide_leg(locked, "EXPIRED", "SYSTEM_AUTO", at=now)
        locked.error_message = "market_closed_before_execution"
        expired_plan = await db.get(RebalancingPlan, locked.plan_id)
        if expired_plan is not None:
            await save_alert_history(
                db, expired_plan.user_id, "REBALANCING", "리밸런싱 자동화 매수 만료 (실행 시점에 장이 닫혀 있음)"
            )
        await db.commit()
        # 조용히 사라지면 "매월 적립"이 빠진 줄도 모른다 — 만료를 알린다(이월은 하지 않는다)
        if expired_plan is not None:
            await _notify_buy_leg_expired(expired_plan, locked.market, db)
        return True

    plan = await db.get(RebalancingPlan, locked.plan_id)
    if plan is None:
        return False

    plan_alert_id = getattr(plan, "alert_id", None)
    alert = await db.get(RebalancingAlert, plan_alert_id) if plan_alert_id else None
    if await is_alert_blocked_by_market_gate(alert, db, composite_level, data_freshness):
        logger.info(
            "rebalancing_plan_buy_execution_skipped_market_signal",
            leg_id=str(locked.id),
            composite_level=composite_level,
            data_freshness=data_freshness,
        )
        return False

    if _needs_usd_check(locked, alert):
        # 잔고 조회의 토큰 발급이 DB commit을 해 FOR UPDATE 락이 풀린다 — 조회 뒤 다시 잠그고 상태를 재확인한다
        shortfall = await _usd_shortfall_for_leg(locked, plan, db, cache)
        relocked = await _lock_leg(leg_id, db)
        if relocked is None or relocked.status != "PENDING" or relocked.token_consumed_at is not None:
            return False
        locked = relocked
        if isinstance(shortfall, UsdShortfall):
            if _fx_wait_past_deadline(locked):
                # 대기 기한이 지난 뒤 예약 매수가 돌아왔는데 또 부족 — 지난 기한을 알리지 말고 마감한다
                await _expire_fx_waiting_leg(locked, plan, db)
                return True
            await _enter_fx_wait(locked, plan, shortfall, db)
            return True

    locked.token_consumed_at = now
    await db.commit()

    execution_id = await _execute_leg(locked, plan, db, cache, "SYSTEM_AUTO")
    if execution_id:
        await _send_leg_execution_email(plan, execution_id, db)
    return True


# ── 정액 적립 해외 매수 환전 대기(plans/120) ─────────────────────────────


def _alert_is_dca(alert) -> bool:
    from app.services.rebalancing.plan_generation import is_dca_amount_mode

    return alert is not None and is_dca_amount_mode(alert)


def _needs_usd_check(leg: RebalancingPlanLeg, alert) -> bool:
    """실행 전 달러 예수금을 확인할 leg인지 — 정액 적립 알림의 해외 매수 leg만(일반 리밸런싱 AUTO는 기존 동작)."""
    return leg.side == "BUY" and leg.market == "US" and _alert_is_dca(alert)


async def _usd_shortfall_for_leg(leg: RebalancingPlanLeg, plan: RebalancingPlan, db: AsyncSession, cache) -> UsdCheck:
    """leg 매수에 달러가 모자라면 UsdShortfall, 확인 불가면 USD_UNKNOWN, 충분하면 None."""
    from app.services.rebalancing.usd_buying_power import check_usd_shortfall

    if plan.account_id is None:
        return USD_UNKNOWN
    await db.refresh(leg, attribute_names=["items"])
    return await check_usd_shortfall(list(leg.items), plan.account_id, plan.user_id, db, cache)


async def _enter_fx_wait(
    locked: RebalancingPlanLeg, plan: RebalancingPlan, shortfall: UsdShortfall, db: AsyncSession
) -> None:
    """잠긴 PENDING 매수 leg를 환전 대기로 바꾸고, 처음 대기에 들어갈 때만 메일·푸시로 알린다."""
    from app.services.rebalancing.plan_notifications import notify_dca_fx_required
    from app.utils.market_hours import us_market_close_after_weekdays

    first_wait = locked.fx_retry_until is None
    locked.status = "WAITING_FX"
    locked.required_usd = shortfall.required_usd
    locked.available_usd = shortfall.available_usd
    # 재시도로 다시 PENDING이 됐다가 또 부족하면 처음 기한을 유지한다 — 기한이 계속 밀리면 영영 안 끝난다
    if first_wait:
        locked.fx_retry_until = us_market_close_after_weekdays(FX_WAIT_WEEKDAYS).astimezone(UTC)
        await save_alert_history(db, plan.user_id, "REBALANCING", "적립 해외 매수 대기 — 달러 환전 필요")
    retry_until = locked.fx_retry_until
    await db.commit()
    # 재개 → 또 부족은 30분마다 반복될 수 있다 — 이미 받은 환전 안내를 다시 보내지 않는다(plans/122 B1)
    if first_wait and retry_until is not None:
        await notify_dca_fx_required(plan, shortfall.required_usd, shortfall.available_usd, retry_until, db)


def _fx_wait_past_deadline(leg: RebalancingPlanLeg) -> bool:
    until = leg.fx_retry_until
    if until is None:
        return False
    until = until if until.tzinfo else until.replace(tzinfo=UTC)
    return datetime.now(tz=UTC) >= until


def _resume_fx_waiting_leg(leg: RebalancingPlanLeg, deadline_at: datetime) -> None:
    """환전 대기 leg를 매수 대기(PENDING)로 되돌린다 — 1분 매수 잡이 deadline 이후 실행(달러 재확인 포함)."""
    leg.status = "PENDING"
    leg.deadline_at = deadline_at
    leg.error_message = None


async def _expire_fx_waiting_leg(locked: RebalancingPlanLeg, plan: RebalancingPlan | None, db: AsyncSession) -> None:
    from app.services.rebalancing.plan_notifications import notify_dca_fx_wait_expired

    _decide_leg(locked, "EXPIRED", "SYSTEM_EXPIRY")
    locked.error_message = FX_WAIT_EXPIRED_MESSAGE
    if plan is not None:
        await save_alert_history(db, plan.user_id, "REBALANCING", "적립 해외 매수 만료 (환전 대기 기한 경과)")
    await db.commit()
    if plan is not None:
        await notify_dca_fx_wait_expired(plan, db)


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
    shortfall = await _usd_shortfall_for_leg(leg, plan, db, cache)
    locked = await _lock_leg(leg.id, db)
    if locked is None:
        raise NotFoundError(detail="계획을 찾을 수 없습니다")
    if locked.status != "WAITING_FX" or locked.token_consumed_at is not None:
        raise ConflictError(detail="이미 처리되었거나 만료된 계획입니다")
    if _fx_wait_past_deadline(locked):
        await _expire_fx_waiting_leg(locked, plan, db)
        raise ConflictError(detail="환전 대기 기한이 지나 이번 회차 해외 매수는 마감되었습니다")

    # 미확인(USD_UNKNOWN)이면 사용자가 환전했다고 누른 것이라 그대로 진행한다 — 증권사가 최종 판정
    if isinstance(shortfall, UsdShortfall):
        locked.required_usd = shortfall.required_usd
        locked.available_usd = shortfall.available_usd
        await db.commit()
        return "STILL_SHORT", None, locked

    if not is_us_market_open():
        _resume_fx_waiting_leg(locked, next_us_market_open().astimezone(UTC))
        await save_alert_history(db, plan.user_id, "REBALANCING", "적립 해외 매수 재개 — 미국장 개장 시 매수")
        await db.commit()
        return "SCHEDULED", None, locked

    _resume_fx_waiting_leg(locked, datetime.now(tz=UTC))
    # commit하면 락이 풀려 1분 매수 잡이 먼저 선점하고 사용자는 "이미 처리" 409를 받는다 — flush만 하고
    # 같은 트랜잭션의 락을 쥔 채 바로 선점한다(plans/122 B3)
    await db.flush()
    execution_id = await _approve_leg_now(locked, db, cache, decided_by, expected_side="BUY")
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
    for leg_id in leg_ids:
        try:
            leg = await db.get(RebalancingPlanLeg, leg_id)
            if leg is None:
                continue
            plan = await db.get(RebalancingPlan, leg.plan_id)
            if not _fx_wait_past_deadline(leg) and (not market_open or plan is None):
                continue
            shortfall: UsdCheck = None
            if not _fx_wait_past_deadline(leg) and plan is not None:
                alert = await db.get(RebalancingAlert, plan.alert_id) if plan.alert_id else None
                # 알림이 정액 모드가 아니게 바뀌었으면 확인 없이 되돌린다 — 실행 경로가 기존 방식(증권사 판정)으로 처리
                if _alert_is_dca(alert):
                    shortfall = await _usd_shortfall_for_leg(leg, plan, db, cache)
            locked = await _lock_leg(leg_id, db)
            if locked is None or locked.status != "WAITING_FX" or locked.token_consumed_at is not None:
                await db.rollback()  # FOR UPDATE 락을 다음 leg까지 붙잡지 않게 바로 푼다
                continue
            if _fx_wait_past_deadline(locked):
                await _expire_fx_waiting_leg(locked, plan, db)
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
            _resume_fx_waiting_leg(locked, datetime.now(tz=UTC))
            await save_alert_history(db, plan.user_id, "REBALANCING", "적립 해외 매수 재개 — 달러 확인됨")
            await db.commit()
            processed += 1
        except Exception as e:
            report_handled_failure("dca_fx_wait_recheck_failed", e, leg_id=str(leg_id))
            await db.rollback()
    return processed


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
            locked = await _lock_leg(leg_id, db)
            if locked is None or locked.status != "PENDING":
                await db.rollback()  # FOR UPDATE 락을 다음 leg 커밋까지 붙잡지 않게 바로 푼다
                continue
            side = locked.side
            _decide_leg(locked, "FAILED", "SYSTEM_EXPIRY")
            locked.error_message = STUCK_LEG_MESSAGE
            plan = await db.get(RebalancingPlan, locked.plan_id)
            if plan:
                await save_alert_history(db, plan.user_id, "REBALANCING", "리밸런싱 자동화 실행 결과 확인 필요")
            await db.commit()
            if plan:
                await _notify_leg_execution_failed(plan, side, STUCK_LEG_MESSAGE, db)
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
            locked = await _lock_leg(leg_id, db)
            if locked is None or locked.status != "PENDING" or locked.token_consumed_at is not None:
                await db.rollback()  # FOR UPDATE 락을 다음 leg 커밋까지 붙잡지 않게 바로 푼다
                continue
            _decide_leg(locked, "EXPIRED", "SYSTEM_EXPIRY", at=now)
            plan = await db.get(RebalancingPlan, locked.plan_id)
            if plan:
                await save_alert_history(
                    db, plan.user_id, "REBALANCING", "리밸런싱 자동화 매도 승인 만료 (장마감 미응답)"
                )
            await db.commit()
            processed += 1
        except Exception as e:
            report_handled_failure("rebalancing_plan_sell_expiry_leg_failed", e, leg_id=str(leg_id))
            await db.rollback()

    return processed
