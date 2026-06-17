"""목표환율 / 리밸런싱 알림 체크 서비스."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import ExchangeRateAlert, RebalancingAlert, StockPriceAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alert_calculator import (
    already_fired_today,
    should_fire_today,
    should_trigger_exchange_rate,
    should_trigger_stock_price,
)
from app.services.alert_repository import save_alert_history
from app.utils.currency import fetch_usd_krw
from app.utils.metrics import alert_trigger_count

logger = structlog.get_logger()


async def check_and_trigger_alerts(db: AsyncSession) -> None:
    """활성 알림을 조회하고 조건 충족 시 이메일/푸시 발송 후 비활성화."""
    from app.services.email_service import send_exchange_rate_alert
    from app.services.push_service import send_push_to_user

    current_rate = await fetch_usd_krw(None, force_refresh=True)
    if current_rate <= 0:
        logger.warning("alert_check_skipped_no_rate")
        return

    result = await db.execute(
        select(
            ExchangeRateAlert,
            User.email,
            UserSettings.notification_email,
            UserSettings.fcm_token,
        )
        .join(User, User.id == ExchangeRateAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(ExchangeRateAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, user_email, notification_email, fcm_token in rows:
        if not should_trigger_exchange_rate(alert, current_rate):
            continue

        email = notification_email or user_email
        target = float(alert.target_rate)
        try:
            await send_exchange_rate_alert(
                to_email=email,
                target_rate=target,
                direction=alert.direction,
                current_rate=current_rate,
            )
        except Exception as exc:
            logger.error("exchange_rate_alert_email_failed", error=str(exc), alert_id=str(alert.id))
            continue

        direction_label = "이하" if alert.direction == "BELOW" else "이상"
        await send_push_to_user(
            user_id=alert.user_id,
            title="환율 알림",
            body=f"USD/KRW {current_rate:.0f}원 (목표 {target:.0f}원 {direction_label})",
            fcm_token=fcm_token,
        )

        alert.trigger_count += 1
        alert.triggered_at = datetime.now(tz=UTC)
        if alert.trigger_count >= alert.max_trigger_count:
            alert.is_active = False
        await save_alert_history(
            db,
            alert.user_id,
            "EXCHANGE_RATE",
            f"환율 알림: USD/KRW {current_rate:.0f}원 (목표 {target:.0f}원 {direction_label})",
        )
        triggered_count += 1

    if triggered_count:
        await db.commit()
        alert_trigger_count.labels(alert_type="exchange_rate").inc(triggered_count)
        logger.info("exchange_rate_alerts_triggered", count=triggered_count, current_rate=current_rate)


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
) -> bool:
    """단일 리밸런싱 알림을 처리 (AUTO 실행 또는 이메일 발송).

    성공 시 True, continue 필요(건너뜀) 시 False 반환.
    """
    from app.services.email_service import send_rebalancing_alert

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
        return await _execute_auto_rebalancing(alert, portfolio, drifting, db)

    try:
        await send_rebalancing_alert(
            to_email=email,
            portfolio_name=portfolio.name,
            threshold_pct=threshold,
            items_to_show=items_to_show,
            drifting_count=len(drifting),
            is_scheduled_report=is_scheduled_report,
            schedule_type=getattr(alert, "schedule_type", "DAILY"),
        )
    except Exception as exc:
        logger.error("rebalancing_alert_email_failed", alert_id=str(alert.id), error=str(exc))
        return False

    return True


async def _execute_auto_rebalancing(
    alert,
    portfolio: Portfolio,
    drifting: list,
    db: AsyncSession,
) -> bool:
    """AUTO 모드 리밸런싱 주문을 생성하고 실행한다.

    성공 시 True, 오류 시 False 반환.
    """
    from app.redis_client import get_redis
    from app.schemas.rebalancing import ExecutionOrderItem
    from app.services.rebalancing_execution_service import execute_rebalancing

    strategy = getattr(alert, "strategy", "BUY_ONLY")
    order_type = getattr(alert, "order_type", "MARKET")

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
        orders.append(
            ExecutionOrderItem(
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                side=side,
                quantity=qty,
                account_id=str(alert.account_id),
                order_type=order_type,
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
        select(RebalancingAlert, Portfolio, User.email, UserSettings.notification_email)
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(RebalancingAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, portfolio, user_email, notification_email in rows:
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


async def check_and_trigger_stock_price_alerts(db: AsyncSession, redis) -> None:
    """활성 주가 알림을 조회하고 조건 충족 시 이메일/푸시 발송 후 비활성화."""
    from app.services.email_service import send_stock_price_alert
    from app.services.price_service import fetch_prices_batch
    from app.services.push_service import send_push_to_user

    result = await db.execute(
        select(
            StockPriceAlert,
            User.email,
            UserSettings.notification_email,
            UserSettings.fcm_token,
        )
        .join(User, User.id == StockPriceAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(StockPriceAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()
    if not rows:
        return

    sample_user_id = rows[0][0].user_id
    unique_tickers = list({(a.ticker, a.market) for a, _, _, _ in rows})
    price_map = await fetch_prices_batch(sample_user_id, unique_tickers, db, redis)

    triggered_count = 0
    for alert, user_email, notification_email, fcm_token in rows:
        price = price_map.get(alert.ticker)
        if not price:
            continue
        if not should_trigger_stock_price(alert, price):
            continue

        email = notification_email or user_email
        target = float(alert.target_price)
        try:
            await send_stock_price_alert(
                to_email=email,
                ticker=alert.ticker,
                name=alert.name,
                target_price=target,
                current_price=price,
                direction=alert.direction,
            )
        except Exception as exc:
            logger.error("stock_price_alert_email_failed", error=str(exc), alert_id=str(alert.id))
            continue

        direction_label = "이하" if alert.direction == "BELOW" else "이상"
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"주가 알림: {alert.name}",
            body=f"{price:,.0f}원 (목표 {target:,.0f}원 {direction_label})",
            fcm_token=fcm_token,
        )

        alert.trigger_count += 1
        alert.triggered_at = datetime.now(tz=UTC)
        if alert.trigger_count >= alert.max_trigger_count:
            alert.is_active = False
        await save_alert_history(
            db,
            alert.user_id,
            "STOCK_PRICE",
            (f"주가 알림: {alert.name}({alert.ticker}) {price:,.0f}원 (목표 {target:,.0f}원 {direction_label})"),
        )
        triggered_count += 1

    if triggered_count:
        await db.commit()
        alert_trigger_count.labels(alert_type="stock_price").inc(triggered_count)
        logger.info("stock_price_alerts_triggered", count=triggered_count)


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
