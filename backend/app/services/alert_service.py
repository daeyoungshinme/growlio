"""리밸런싱 알림 체크 서비스.

환율 알림 → exchange_rate_alert_service.py
주가 알림 → stock_price_alert_service.py
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertHistory, RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alert_calculator import (
    already_fired_today,
    should_fire_today,
)
from app.utils.metrics import alert_trigger_count

logger = structlog.get_logger()


async def save_alert_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    alert_type: str,
    message: str,
) -> None:
    db.add(AlertHistory(user_id=user_id, alert_type=alert_type, message=message))


async def apply_alert_trigger(
    db: AsyncSession,
    alert: Any,
    alert_type: str,
    history_message: str,
) -> None:
    """알림 발동 후 상태 갱신(trigger_count, triggered_at, is_active) 및 이력 저장."""
    alert.trigger_count += 1
    alert.triggered_at = datetime.now(tz=UTC)
    if alert.trigger_count >= alert.max_trigger_count:
        alert.is_active = False
    await save_alert_history(db, alert.user_id, alert_type, history_message)


# backward-compatible re-exports (lazy to avoid circular import)
__all__ = [
    "check_and_trigger_alerts",
    "check_and_trigger_stock_price_alerts",
    "check_rebalancing_alerts",
    "execute_auto_rebalancing_for_alert",
    "list_alert_history",
]


def __getattr__(name: str):
    if name == "check_and_trigger_alerts":
        from app.services.exchange_rate_alert_service import check_and_trigger_alerts
        return check_and_trigger_alerts
    if name == "check_and_trigger_stock_price_alerts":
        from app.services.stock_price_alert_service import check_and_trigger_stock_price_alerts
        return check_and_trigger_stock_price_alerts
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _select_items_to_show(
    trigger_condition: str,
    is_schedule_day: bool,
    drifting: list,
    all_items: list,
) -> tuple[list, bool] | None:
    """trigger_condition에 따라 (items_to_show, is_scheduled_report)를 반환.

    발송하지 않아야 하는 경우 None 반환.
    """
    if trigger_condition == "SCHEDULE_ONLY":
        if not is_schedule_day:
            return None
        return all_items, True
    if trigger_condition == "DRIFT_ONLY":
        if not drifting:
            return None
        return drifting, False
    # BOTH
    if is_schedule_day:
        return all_items, True
    if drifting:
        return drifting, False
    return None


async def _process_rebalancing_alert(
    alert,
    portfolio: Portfolio,
    drifting: list,
    items_to_show: list,
    is_scheduled_report: bool,
    threshold: float,
    email: str,
    composite_level: str,
    db: AsyncSession,
    fcm_token: str | None = None,
) -> bool:
    """단일 리밸런싱 알림을 처리 (AUTO 실행 또는 이메일/FCM 발송).

    성공 시 True, continue 필요(건너뜀) 시 False 반환.
    """
    import asyncio

    from app.services.email_service import send_rebalancing_alert
    from app.services.push_service import send_push_to_user

    mode = getattr(alert, "mode", "NOTIFY")

    # 시장 신호 기반 자동 실행 게이트
    if mode == "AUTO":
        market_mode = getattr(alert, "market_condition_mode", "DISABLED")
        _blocked = (market_mode == "CAUTIOUS" and composite_level == "RED") or (
            market_mode == "STRICT" and composite_level in ("YELLOW", "RED")
        )
        if _blocked:
            logger.info(
                "rebalancing_auto_skipped_market_signal",
                alert_id=str(alert.id),
                composite_level=composite_level,
                market_condition_mode=market_mode,
            )
            mode = "NOTIFY"

    if mode == "AUTO" and alert.account_id and drifting:
        return await execute_auto_rebalancing_for_alert(alert, portfolio, drifting, db)

    # NOTIFY: 이메일 + FCM 병렬 전송
    drift_count = len(drifting)
    push_title = f"리밸런싱 알림 — {portfolio.name}"
    push_body = (
        f"{drift_count}개 종목이 ±{threshold:.1f}% 이상 이탈했습니다."
        if drift_count
        else f"{portfolio.name} 정기 리밸런싱 리포트"
    )

    email_task = asyncio.create_task(
        send_rebalancing_alert(
            to_email=email,
            portfolio_name=portfolio.name,
            threshold_pct=threshold,
            items_to_show=items_to_show,
            drifting_count=drift_count,
            is_scheduled_report=is_scheduled_report,
            schedule_type=getattr(alert, "schedule_type", "DAILY"),
        )
    )
    push_task = asyncio.create_task(
        send_push_to_user(
            user_id=alert.user_id,
            title=push_title,
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING", "portfolio_id": str(portfolio.id)},
        )
    )

    try:
        await email_task
    except Exception as exc:
        logger.error("rebalancing_alert_email_failed", alert_id=str(alert.id), error=str(exc))
        push_task.cancel()
        return False

    # FCM 실패는 무시 (이메일이 성공하면 OK)
    with contextlib.suppress(Exception):
        await push_task

    return True


async def execute_auto_rebalancing_for_alert(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    drifting: list,
    db: AsyncSession,
) -> bool:
    """AUTO 모드 리밸런싱 주문을 생성하고 실행한다.

    장 중 여부 확인 후 실행. 성공 시 True, 오류/건너뜀 시 False 반환.
    신규 AUTO 전용 Job(rebalancing_auto_execution.py)에서도 직접 호출한다.
    """
    from app.utils.market_hours import is_korean_market_open

    if not is_korean_market_open():
        logger.info(
            "rebalancing_auto_skipped_market_closed",
            alert_id=str(alert.id),
        )
        return False

    return await _execute_auto_rebalancing(alert, portfolio, drifting, db)


async def _execute_auto_rebalancing(
    alert,
    portfolio: Portfolio,
    drifting: list,
    db: AsyncSession,
) -> bool:
    """AUTO 모드 리밸런싱 주문을 생성하고 실행한다 (내부용, 장 중 체크 없음).

    성공 시 True, 오류 시 False 반환.
    """
    from app.redis_client import get_redis
    from app.schemas.rebalancing import ExecutionOrderItem
    from app.services.rebalancing_execution_service import execute_rebalancing

    strategy = getattr(alert, "strategy", "BUY_ONLY")
    order_type = cast(Literal["MARKET", "LIMIT"], getattr(alert, "order_type", "MARKET"))

    orders: list[ExecutionOrderItem] = []
    for item in drifting:
        if item.ticker in ("CASH", "REAL_ESTATE") or item.shares_to_trade is None:
            continue
        qty = abs(int(item.shares_to_trade))
        if qty <= 0:
            continue
        side = "BUY" if item.diff_krw > 0 else "SELL"
        if strategy == "BUY_ONLY" and side == "SELL":
            continue

        # LIMIT 주문 시 현재가를 지정가로 사용 (None이면 MARKET으로 fallback)
        effective_order_type = order_type
        limit_price: float | None = None
        if order_type == "LIMIT":
            price = getattr(item, "current_price_krw", None)
            if price and price > 0:
                limit_price = float(price)
            else:
                effective_order_type = "MARKET"

        orders.append(
            ExecutionOrderItem(
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                side=side,
                quantity=qty,
                account_id=str(alert.account_id),
                order_type=effective_order_type,
                limit_price=limit_price,
            )
        )

    if orders:
        try:
            redis = await get_redis()
            await execute_rebalancing(
                user_id=alert.user_id,
                account_id=alert.account_id,
                orders=orders,
                db=db,
                redis=redis,
                portfolio_id=portfolio.id,
                triggered_by="AUTO",
                strategy=strategy,
            )
        except Exception as exc:
            logger.error("rebalancing_auto_execute_failed", alert_id=str(alert.id), error=str(exc))
            return False

    return True


async def check_rebalancing_alerts(db: AsyncSession) -> None:
    """활성 리밸런싱 알림을 조회하고 스케줄·조건에 따라 이메일 발송."""
    from app.redis_client import get_redis
    from app.services.market_signal_service import get_market_signal
    from app.services.portfolio_service import build_portfolio_overview
    from app.services.rebalancing_service import analyze_rebalancing

    # 시장 신호를 루프 전 한 번만 조회 (전체 알림 공용)
    try:
        _redis = await get_redis()
        _market_signal = await get_market_signal(_redis)
        composite_level: str = _market_signal.get("composite_level", "GREEN")
    except Exception as _exc:
        logger.warning("market_signal_fetch_failed_in_alert_check", error=str(_exc))
        composite_level = "GREEN"  # 조회 실패 시 안전 방향으로 실행 허용

    result = await db.execute(
        select(RebalancingAlert, Portfolio, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(RebalancingAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, portfolio, user_email, notification_email, fcm_token in rows:
        trigger_condition = getattr(alert, "trigger_condition", "DRIFT_ONLY")
        is_schedule_day = should_fire_today(alert)

        # BOTH: 매일 체크; DRIFT_ONLY/SCHEDULE_ONLY: 스케줄 날만 체크
        if not is_schedule_day and trigger_condition != "BOTH":
            continue
        if already_fired_today(alert):
            continue

        saved_ids = getattr(portfolio, "account_ids", None)
        effective_account_ids: list[uuid.UUID] | None = [uuid.UUID(aid) for aid in saved_ids] if saved_ids else None

        try:
            overview = await build_portfolio_overview(alert.user_id, db, account_ids=effective_account_ids)
        except Exception as exc:
            logger.error("rebalancing_alert_overview_failed", alert_id=str(alert.id), error=str(exc))
            continue

        try:
            analysis = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
        except Exception as exc:
            logger.error("rebalancing_alert_analysis_failed", alert_id=str(alert.id), error=str(exc))
            continue

        threshold = float(alert.threshold_pct)
        drifting = [item for item in analysis.items if abs(item.weight_diff_pct) > threshold]

        selected = _select_items_to_show(trigger_condition, is_schedule_day, drifting, analysis.items)
        if selected is None:
            continue
        items_to_show, is_scheduled_report = selected

        email = notification_email or user_email
        triggered = await _process_rebalancing_alert(
            alert=alert,
            portfolio=portfolio,
            drifting=drifting,
            items_to_show=items_to_show,
            is_scheduled_report=is_scheduled_report,
            threshold=threshold,
            email=email,
            composite_level=composite_level,
            db=db,
            fcm_token=fcm_token,
        )
        if not triggered:
            continue

        drift_desc = f"{len(drifting)}개 종목 드리프트" if drifting else "정기 보고"
        await save_alert_history(
            db,
            alert.user_id,
            "REBALANCING",
            (f"리밸런싱 알림: {portfolio.name} — {drift_desc} ({alert.schedule_type}) [시장신호: {composite_level}]"),
        )
        alert.last_triggered_at = datetime.now(tz=UTC)
        triggered_count += 1

    if triggered_count:
        await db.commit()
        alert_trigger_count.labels(alert_type="rebalancing").inc(triggered_count)
        logger.info("rebalancing_alerts_triggered", count=triggered_count)


async def list_alert_history(
    user_id: uuid.UUID,
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
):
    from app.models.alert import AlertHistory

    result = await db.execute(
        select(AlertHistory)
        .where(AlertHistory.user_id == user_id)
        .order_by(AlertHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
