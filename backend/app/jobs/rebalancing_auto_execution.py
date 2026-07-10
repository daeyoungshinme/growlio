"""리밸런싱 AUTO 플랜 생성 전용 Job — 장 중 5분 간격, 사용자 지정 시각에 계획을 생성한다.

실제 주문 실행은 여기서 하지 않는다 — 매수는 rebalancing_plan_buy_execution.py(1분 간격)가
대기시간 경과 후 실행하고, 매도는 사용자가 이메일 링크로 승인해야 실행된다.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.alert_calculator import already_fired_today
from app.services.rebalancing_plan_service import (
    build_pending_plan_for_alert,
    has_pending_plan_for_alert,
    notify_plan_generated,
)
from app.utils.cache_keys import TTL_JOB_LOCK_REBALANCING_AUTO
from app.utils.market_hours import is_alert_execution_time, is_korean_market_open
from app.utils.metrics import alert_trigger_count
from app.utils.redis_lock import redis_lock

logger = structlog.get_logger()


async def run_rebalancing_auto_execution() -> None:
    """장 중 5분 간격 실행 — AUTO 모드 알림의 지정 시각에 리밸런싱 대기 플랜을 생성한다."""
    if not is_korean_market_open():
        return

    redis = await get_redis()
    async with redis_lock(redis, "rebalancing_auto_execution_lock", ttl=TTL_JOB_LOCK_REBALANCING_AUTO) as acquired:
        if not acquired:
            logger.info("rebalancing_auto_execution_skipped_lock_held")
            return
        await _run_auto_execution()


async def _run_auto_execution() -> None:
    from app.services.market_signal_service import get_market_signal

    redis = await get_redis()

    try:
        _market_signal = await get_market_signal(redis)
        composite_level: str = _market_signal.get("composite_level", "GREEN")
    except Exception as exc:
        logger.warning("market_signal_fetch_failed_in_auto_execution", error=str(exc))
        composite_level = "GREEN"

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

            # 시장 신호 게이트 — 계획 생성 시점에만 확인한다(실행/승인 시점 재확인 안 함).
            market_mode = getattr(alert, "market_condition_mode", "DISABLED")
            blocked = (market_mode == "CAUTIOUS" and composite_level == "RED") or (
                market_mode == "STRICT" and composite_level in ("YELLOW", "RED")
            )
            if blocked:
                logger.info(
                    "rebalancing_auto_skipped_market_signal",
                    alert_id=str(alert.id),
                    composite_level=composite_level,
                )
                continue

            # 이미 대기 중인 플랜이 있으면(취소/승인 대기) 중복 생성하지 않는다.
            if await has_pending_plan_for_alert(alert.id, db):
                continue

            try:
                generated = await build_pending_plan_for_alert(alert, portfolio, db, composite_level)
            except Exception as exc:
                logger.error("rebalancing_auto_plan_generation_failed", alert_id=str(alert.id), error=str(exc))
                continue
            if generated is None:
                continue
            plan_obj, buy_token, sell_token = generated

            email = notification_email or user_email
            await notify_plan_generated(
                plan_obj, alert, portfolio, buy_token, sell_token, email, fcm_token, composite_level, db
            )
            triggered_count += 1

        if triggered_count:
            await db.commit()
            alert_trigger_count.labels(alert_type="rebalancing_auto").inc(triggered_count)
            logger.info("rebalancing_auto_plan_generated", count=triggered_count)
