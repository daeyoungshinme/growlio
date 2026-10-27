"""리밸런싱 AUTO 플랜 생성 전용 Job — 장 중 5분 간격, 사용자 지정 시각에 계획을 생성한다.

실제 주문 실행은 여기서 하지 않는다 — 매수는 rebalancing_plan_buy_execution.py(1분 간격)가
대기시간 경과 후 실행하고, 매도는 사용자가 이메일 링크로 승인해야 실행된다.
"""

from __future__ import annotations

import uuid

import sentry_sdk
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal
from app.core.logging import redact_secrets
from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alerts.calculator import already_fired_today, is_auto_schedule_day
from app.services.rebalancing.order_builder import is_market_signal_blocking_auto_mode, tactical_regime_for_gate
from app.services.rebalancing.plan_service import (
    DailyValueCapBlocked,
    MarketSignalGateBlocked,
    TaxGateBlocked,
    build_pending_plan_for_alert,
    get_alert_ids_with_pending_plan,
    notify_daily_value_cap_blocked,
    notify_market_signal_gate_blocked,
    notify_plan_generated,
    notify_tax_gate_blocked,
)
from app.utils.cache_keys import (
    TTL_JOB_LOCK_REBALANCING_AUTO,
    TTL_REBALANCING_AUTO_CLAIM,
    rebalancing_auto_claim_key,
)
from app.utils.durable_state import claim_durable, delete_durable
from app.utils.inproc_lock import inproc_lock
from app.utils.kst import today_kst
from app.utils.market_hours import is_alert_execution_time, is_korean_market_open, is_us_market_open
from app.utils.metrics import alert_trigger_count

logger = structlog.get_logger()


async def run_rebalancing_auto_execution() -> None:
    """5분 간격 실행 — AUTO 모드 알림의 지정 시각에 리밸런싱 대기 플랜을 생성한다.

    국내(KRX)/해외(NYSE) 중 최소 한 시장이 열려 있는 거래일에만 진행하는 저비용 조기 종료 —
    실제 알림별 시각 매칭은 `is_alert_execution_time()`이, leg 단위 시장 개장 여부는 매수
    실행(execute_due_buy_legs)·매도 만료(expire_due_sell_legs) 시점에 각각 판단한다. 두 시장이
    모두 닫힌 주말 등에만 여기서 걸러진다 — 해외 전용 알림이 KRX 휴장일에 막히는 일은 없다.
    """
    if not (is_korean_market_open() or is_us_market_open()):
        return

    cache = await get_cache_store()
    async with inproc_lock(cache, "rebalancing_auto_execution_lock", ttl=TTL_JOB_LOCK_REBALANCING_AUTO) as acquired:
        if not acquired:
            logger.info("rebalancing_auto_execution_skipped_lock_held")
            return
        await _run_auto_execution()


async def _load_auto_alert_rows(db: AsyncSession, alert_ids: list[uuid.UUID] | None = None) -> list:
    stmt = (
        select(RebalancingAlert, Portfolio, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .options(selectinload(Portfolio.linked_accounts), selectinload(Portfolio.items))
        .where(
            RebalancingAlert.is_active == True,
            RebalancingAlert.mode == "AUTO",
        )
    )
    if alert_ids is not None:
        stmt = stmt.where(RebalancingAlert.id.in_(alert_ids))
    return list((await db.execute(stmt)).all())


async def _run_auto_execution() -> None:
    from app.services.market_signal_service import get_confirmed_composite_level

    cache = await get_cache_store()

    async with AsyncSessionLocal() as db:
        # confirmed level(hysteresis 적용)은 durable_state 조회가 필요해 db 세션 안에서 구한다.
        composite_level, data_freshness = await get_confirmed_composite_level(cache, db)

        rows = await _load_auto_alert_rows(db)
        pending_alert_ids = await get_alert_ids_with_pending_plan([alert.id for alert, *_ in rows], db)
        alert_ids = [row[0].id for row in rows]

        triggered_count = 0
        index = 0
        while index < len(rows):
            alert_id = alert_ids[index]
            try:
                if await _process_one_alert(rows[index], db, cache, composite_level, data_freshness, pending_alert_ids):
                    triggered_count += 1
                index += 1
            except Exception as e:
                # 알림 하나의 실패(내부 commit 실패·알림 발송 오류)가 같은 세션의 남은 알림 전부를
                # PendingRollbackError로 막지 않게 격리한다 — alert_check와 같은 패턴(rollback 후 남은 row 재조회).
                # 스택 지역변수를 보내는 capture_exception 대신 타입명만(AUTO 경로는 자격증명을 지역변수로 다룬다).
                logger.error(
                    "rebalancing_auto_item_failed",
                    alert_id=str(alert_id),
                    error=redact_secrets(str(e)),
                    error_type=type(e).__name__,
                )
                sentry_sdk.capture_message(f"rebalancing_auto_item_failed: {type(e).__name__}", level="error")
                await db.rollback()
                remaining_ids = alert_ids[index + 1 :]
                rows = await _load_auto_alert_rows(db, remaining_ids) if remaining_ids else []
                alert_ids = [row[0].id for row in rows]
                index = 0

        if triggered_count:
            alert_trigger_count.labels(alert_type="rebalancing_auto").inc(triggered_count)
            logger.info("rebalancing_auto_plan_generated", count=triggered_count)


async def _process_one_alert(
    row,
    db: AsyncSession,
    cache,
    composite_level: str,
    data_freshness: str,
    pending_alert_ids: set[uuid.UUID],
) -> bool:
    """AUTO 알림 1건 — 플랜을 생성해 알렸으면 True."""
    alert, portfolio, user_email, notification_email, fcm_token = row
    if not is_alert_execution_time(getattr(alert, "auto_execution_time", None)):
        return False
    if already_fired_today(alert):
        return False
    # 스케줄 준수 — BOTH는 매일 드리프트 체크, DRIFT_ONLY/SCHEDULE_ONLY는 스케줄일에만(NOTIFY 경로
    # alert_check._should_skip_by_schedule와 동일 규칙). 도입 시점부터 이 체크가 빠져 있어 "매월 25일"
    # 정기 적립식 자동매수(임계값 0.5%)가 사실상 매 거래일 실행될 수 있었다(2026-09-26 수정).
    trigger_condition = getattr(alert, "trigger_condition", None) or "DRIFT_ONLY"
    if trigger_condition != "BOTH" and not is_auto_schedule_day(alert):
        return False

    email = notification_email or user_email

    # 시장 신호 게이트 — 계획 생성 시점에 확인한다. 매수 실행 직전(1분 간격 job)에도
    # 재확인한다(rebalancing_plan_buy_execution.py) — 대기시간 동안 상황이 바뀔 수 있어서다.
    market_mode = getattr(alert, "market_condition_mode", "DISABLED")
    tactical_regime = await tactical_regime_for_gate(alert, db)
    if is_market_signal_blocking_auto_mode(market_mode, composite_level, data_freshness, tactical_regime):
        logger.info(
            "rebalancing_auto_skipped_market_signal",
            alert_id=str(alert.id),
            composite_level=composite_level,
            data_freshness=data_freshness,
        )
        blocked_by_signal = MarketSignalGateBlocked(
            composite_level=composite_level,
            market_condition_mode=market_mode,
            data_freshness=data_freshness,
            tactical_regime=tactical_regime,
        )
        await notify_market_signal_gate_blocked(alert, portfolio, blocked_by_signal, email, fcm_token, db)
        return False

    # 이미 대기 중인 플랜이 있으면(취소/승인 대기) 중복 생성하지 않는다.
    if alert.id in pending_alert_ids:
        return False

    # 메모리의 last_triggered_at·pending 확인은 같은 프로세스 안에서만 유효하다 — 배포가 겹친 다른 인스턴스와
    # 같은 tick에 둘 다 통과할 수 있어 DB에서 원자적으로 선점한다. 플랜을 만든 경우에만 claim을 남긴다.
    claim_key = rebalancing_auto_claim_key(alert.id, today_kst().isoformat())
    if not await claim_durable(db, claim_key, TTL_REBALANCING_AUTO_CLAIM):
        logger.info("rebalancing_auto_claim_held", alert_id=str(alert.id))
        return False

    try:
        generated = await build_pending_plan_for_alert(alert, portfolio, db, composite_level, cache=cache)
    except Exception:
        # 생성 중 실패 — 다음 tick에 재시도할 수 있게 claim을 푼다. 플랜이 commit된 뒤의 실패라면
        # last_triggered_at이 같은 트랜잭션으로 저장돼 already_fired_today가 막는다.
        await db.rollback()
        await delete_durable(db, claim_key)
        raise

    if not isinstance(generated, tuple):
        # 게이트 차단·생성할 주문 없음·수동 실행과 락 경합 — 이전과 같이 다음 tick에 다시 평가한다
        await delete_durable(db, claim_key)
        if isinstance(generated, TaxGateBlocked):
            await notify_tax_gate_blocked(alert, portfolio, generated, email, fcm_token, db)
        elif isinstance(generated, DailyValueCapBlocked):
            await notify_daily_value_cap_blocked(alert, portfolio, generated, email, fcm_token, db)
        # PlanGenerationInProgress: 수동 "지금 실행"과 거의 동시에 겹친 드문 경합 — 조용히 스킵
        return False

    plan_obj, buy_tokens, sell_tokens = generated
    await notify_plan_generated(
        plan_obj, alert, portfolio, buy_tokens, sell_tokens, email, fcm_token, composite_level, db
    )
    # 항목마다 커밋한다 — 다음 알림이 실패해 rollback되면 이번 알림의 이력·상태까지 사라진다
    await db.commit()
    return True
