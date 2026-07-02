"""리밸런싱 AUTO 실행 전용 Job — 장 중 5분 간격, 사용자 지정 시각에 실행."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models.alert import RebalancingAlert
from app.models.asset import RebalancingExecution
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.alert_calculator import already_fired_today
from app.services.alert_service import save_alert_history
from app.services.email_service import send_rebalancing_execution_email
from app.utils.cache_keys import TTL_JOB_LOCK_REBALANCING_AUTO
from app.utils.market_hours import is_alert_execution_time, is_korean_market_open
from app.utils.metrics import alert_trigger_count
from app.utils.redis_lock import redis_lock

logger = structlog.get_logger()


async def run_rebalancing_auto_execution() -> None:
    """장 중 5분 간격 실행 — AUTO 모드 알림의 지정 시각에 리밸런싱을 자동 실행한다."""
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
    for alert, portfolio, _user_email, _notification_email, _fcm_token in rows:
        if not is_alert_execution_time(getattr(alert, "auto_execution_time", None)):
            continue
        if already_fired_today(alert):
            continue

        # 시장 신호 게이트
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

        triggered = await _execute_for_alert(alert, portfolio)
        if not triggered:
            continue

        # 실행 결과 조회 (알림 발송용)
        exec_result: RebalancingExecution | None = None
        async with AsyncSessionLocal() as db_exec:
            exec_result = await db_exec.scalar(
                select(RebalancingExecution)
                .options(selectinload(RebalancingExecution.result_items))
                .where(
                    RebalancingExecution.user_id == alert.user_id,
                    RebalancingExecution.portfolio_id == portfolio.id,
                    RebalancingExecution.triggered_by == "AUTO",
                )
                .order_by(RebalancingExecution.executed_at.desc())
            )

        # 이메일 알림
        _email = _notification_email or _user_email
        if _email and exec_result:
            try:
                await send_rebalancing_execution_email(
                    to_email=_email,
                    portfolio_name=portfolio.name,
                    executed_at=exec_result.executed_at,
                    result_items=exec_result.result_items,
                    total_success=exec_result.total_success,
                    total_fail=exec_result.total_fail,
                    total_skipped=exec_result.total_skipped,
                )
            except Exception as exc:
                logger.error("rebalancing_auto_execution_email_failed", alert_id=str(alert.id), error=str(exc))

        # FCM 푸시 알림
        if exec_result:
            from app.services.push_service import send_push_to_user

            success_n = exec_result.total_success
            fail_n = exec_result.total_fail
            push_body = f"{success_n}건 완료"
            if fail_n:
                push_body += f", {fail_n}건 실패"
            try:
                await send_push_to_user(
                    user_id=alert.user_id,
                    title=f"리밸런싱 자동 실행 완료 — {portfolio.name}",
                    body=push_body,
                    fcm_token=_fcm_token,
                    data={"type": "REBALANCING_EXECUTED", "portfolio_id": str(portfolio.id)},
                )
            except Exception as exc:
                logger.error("rebalancing_auto_execution_push_failed", alert_id=str(alert.id), error=str(exc))

        async with AsyncSessionLocal() as db_save:
            success_n = exec_result.total_success if exec_result else 0
            fail_n = exec_result.total_fail if exec_result else 0
            history_msg = (
                f"리밸런싱 자동 실행: {portfolio.name} — "
                f"성공 {success_n}건, 실패 {fail_n}건 [시장신호: {composite_level}]"
            )
            await save_alert_history(db_save, alert.user_id, "REBALANCING", history_msg)
            # last_triggered_at 갱신
            alert_row = await db_save.scalar(select(RebalancingAlert).where(RebalancingAlert.id == alert.id))
            if alert_row:
                alert_row.last_triggered_at = datetime.now(tz=UTC)
            await db_save.commit()

        triggered_count += 1

    if triggered_count:
        alert_trigger_count.labels(alert_type="rebalancing_auto").inc(triggered_count)
        logger.info("rebalancing_auto_executed", count=triggered_count)


async def _execute_for_alert(
    alert: RebalancingAlert,
    portfolio: Portfolio,
) -> bool:
    """개별 알림에 대해 드리프트 분석 후 자동 실행한다."""
    from app.services.alert_service import execute_auto_rebalancing_for_alert
    from app.services.portfolio_service import build_portfolio_overview
    from app.services.rebalancing_service import analyze_rebalancing

    saved_ids = getattr(portfolio, "account_ids", None)
    effective_account_ids: list[uuid.UUID] | None = [uuid.UUID(aid) for aid in saved_ids] if saved_ids else None

    async with AsyncSessionLocal() as db:
        try:
            overview = await build_portfolio_overview(alert.user_id, db, account_ids=effective_account_ids)
        except Exception as exc:
            logger.error("rebalancing_auto_overview_failed", alert_id=str(alert.id), error=str(exc))
            return False

        try:
            analysis = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
        except Exception as exc:
            logger.error("rebalancing_auto_analysis_failed", alert_id=str(alert.id), error=str(exc))
            return False

        threshold = float(alert.threshold_pct)
        drifting = [item for item in analysis.items if abs(item.weight_diff_pct) > threshold]

        if not drifting:
            logger.info("rebalancing_auto_no_drift", alert_id=str(alert.id))
            return False

        return await execute_auto_rebalancing_for_alert(alert, portfolio, drifting, db)
