"""리밸런싱 AUTO 플랜 생성 전용 Job — 장 중 5분 간격, 사용자 지정 시각에 계획을 생성한다.

실제 주문 실행은 여기서 하지 않는다 — 매수는 rebalancing_plan_buy_execution.py(1분 간격)가
대기시간 경과 후 실행하고, 매도는 사용자가 이메일 링크로 승인해야 실행된다.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal
from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alerts.calculator import already_fired_today
from app.services.rebalancing.order_builder import is_market_signal_blocking_auto_mode
from app.services.rebalancing.plan_service import (
    MarketSignalGateBlocked,
    TaxGateBlocked,
    build_pending_plan_for_alert,
    has_pending_plan_for_alert,
    notify_market_signal_gate_blocked,
    notify_plan_generated,
    notify_tax_gate_blocked,
)
from app.utils.cache_keys import TTL_JOB_LOCK_REBALANCING_AUTO
from app.utils.inproc_lock import inproc_lock
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


async def _run_auto_execution() -> None:
    from app.services.market_signal_service import get_market_signal_for_auto_gate

    cache = await get_cache_store()
    composite_level, data_freshness = await get_market_signal_for_auto_gate(cache)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RebalancingAlert, Portfolio, User.email, UserSettings.notification_email, UserSettings.fcm_token)
            .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
            .join(User, User.id == RebalancingAlert.user_id)
            .outerjoin(UserSettings, UserSettings.user_id == User.id)
            .options(selectinload(Portfolio.linked_accounts), selectinload(Portfolio.items))
            .where(
                RebalancingAlert.is_active == True,  # noqa: E712
                RebalancingAlert.mode == "AUTO",
            )
        )
        rows = result.all()

        triggered_count = 0
        for alert, portfolio, user_email, notification_email, fcm_token in rows:
            if not is_alert_execution_time(getattr(alert, "auto_execution_time", None)):
                continue
            if already_fired_today(alert):
                continue

            email = notification_email or user_email

            # 시장 신호 게이트 — 계획 생성 시점에 확인한다. 매수 실행 직전(1분 간격 job)에도
            # 재확인한다(rebalancing_plan_buy_execution.py) — 대기시간 동안 상황이 바뀔 수 있어서다.
            market_mode = getattr(alert, "market_condition_mode", "DISABLED")
            if is_market_signal_blocking_auto_mode(market_mode, composite_level, data_freshness):
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
                )
                await notify_market_signal_gate_blocked(alert, portfolio, blocked_by_signal, email, fcm_token, db)
                continue

            # 이미 대기 중인 플랜이 있으면(취소/승인 대기) 중복 생성하지 않는다.
            if await has_pending_plan_for_alert(alert.id, db):
                continue

            try:
                generated = await build_pending_plan_for_alert(alert, portfolio, db, composite_level, cache=cache)
            except Exception as exc:
                logger.error("rebalancing_auto_plan_generation_failed", alert_id=str(alert.id), error=str(exc))
                continue

            if isinstance(generated, TaxGateBlocked):
                await notify_tax_gate_blocked(alert, portfolio, generated, email, fcm_token, db)
                continue
            if generated is None:
                continue
            plan_obj, buy_tokens, sell_tokens = generated
            await notify_plan_generated(
                plan_obj, alert, portfolio, buy_tokens, sell_tokens, email, fcm_token, composite_level, db
            )
            triggered_count += 1

        if triggered_count:
            await db.commit()
            alert_trigger_count.labels(alert_type="rebalancing_auto").inc(triggered_count)
            logger.info("rebalancing_auto_plan_generated", count=triggered_count)
