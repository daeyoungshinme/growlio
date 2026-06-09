"""목표환율 / 리밸런싱 알림 체크 서비스."""
from __future__ import annotations

import calendar
import uuid
from datetime import UTC, datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertHistory, ExchangeRateAlert, RebalancingAlert, StockPriceAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.utils.currency import fetch_usd_krw
from app.utils.metrics import alert_trigger_count

logger = structlog.get_logger()

_MULTI_TRIGGER_COOLDOWN = timedelta(hours=1)


async def _save_alert_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    alert_type: str,
    message: str,
) -> None:
    db.add(AlertHistory(user_id=user_id, alert_type=alert_type, message=message))


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
            ExchangeRateAlert, User.email,
            UserSettings.notification_email, UserSettings.fcm_token,
        )
        .join(User, User.id == ExchangeRateAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(ExchangeRateAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, user_email, notification_email, fcm_token in rows:
        email = notification_email or user_email
        target = float(alert.target_rate)
        should_trigger = (
            (alert.direction == "BELOW" and current_rate <= target)
            or (alert.direction == "ABOVE" and current_rate >= target)
        )
        if not should_trigger:
            continue

        # 다회 발동 알림: 쿨다운 체크 (마지막 발동 후 1시간 이내면 건너뜀)
        if alert.max_trigger_count > 1 and alert.triggered_at:
            elapsed = datetime.now(tz=UTC) - alert.triggered_at
            if elapsed < _MULTI_TRIGGER_COOLDOWN:
                continue

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
        await _save_alert_history(
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


_KST = timezone(timedelta(hours=9))

# QUARTERLY/SEMIANNUAL/ANNUAL: 쿨다운(일) 경과 후 지정 날짜에 발송
_SCHEDULE_MIN_DAYS: dict[str, int] = {
    "QUARTERLY": 80,
    "SEMIANNUAL": 170,
    "ANNUAL": 350,
}


def _should_fire_today(alert: RebalancingAlert) -> bool:
    """오늘이 해당 알림의 발송일인지 확인."""
    today = datetime.now(tz=_KST).date()
    schedule = alert.schedule_type or "DAILY"

    if schedule == "DAILY":
        return True

    if schedule == "WEEKLY":
        target_dow = alert.schedule_day_of_week if alert.schedule_day_of_week is not None else 0
        return today.weekday() == target_dow

    if schedule == "MONTHLY":
        target_day = alert.schedule_day_of_month or 1
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.day == min(target_day, last_day)

    if schedule in _SCHEDULE_MIN_DAYS:
        target_day = alert.schedule_day_of_month or 1
        last_day = calendar.monthrange(today.year, today.month)[1]
        if today.day != min(target_day, last_day):
            return False
        if not alert.last_triggered_at:
            return True  # 최초 발송
        min_days = _SCHEDULE_MIN_DAYS[schedule]
        elapsed_days = (today - alert.last_triggered_at.astimezone(_KST).date()).days
        return elapsed_days >= min_days

    return False


def _already_fired_today(alert: RebalancingAlert) -> bool:
    """오늘 이미 발송됐는지 확인 (중복 방지)."""
    if not alert.last_triggered_at:
        return False
    today = datetime.now(tz=_KST).date()
    fired_date = alert.last_triggered_at.astimezone(_KST).date()
    return fired_date == today


async def check_rebalancing_alerts(db: AsyncSession) -> None:
    """활성 리밸런싱 알림을 조회하고 스케줄·조건에 따라 이메일 발송."""
    from app.services.email_service import send_rebalancing_alert
    from app.services.portfolio_service import build_portfolio_overview
    from app.services.rebalancing_service import analyze_rebalancing

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
        # 1. 오늘 발송일인지 확인
        if not _should_fire_today(alert):
            continue

        # 2. 오늘 이미 발송했으면 건너뜀
        if _already_fired_today(alert):
            continue

        # 3. 포트폴리오 분석
        saved_ids = getattr(portfolio, "account_ids", None)
        effective_account_ids: list[uuid.UUID] | None = (
            [uuid.UUID(aid) for aid in saved_ids] if saved_ids else None
        )

        try:
            overview = await build_portfolio_overview(
                alert.user_id, db, account_ids=effective_account_ids
            )
        except Exception as exc:
            logger.error("rebalancing_alert_overview_failed", alert_id=str(alert.id), error=str(exc))
            continue

        try:
            analysis = analyze_rebalancing(portfolio, overview)
        except Exception as exc:
            logger.error("rebalancing_alert_analysis_failed", alert_id=str(alert.id), error=str(exc))
            continue

        threshold = float(alert.threshold_pct)
        drifting = [item for item in analysis.items if abs(item.weight_diff_pct) > threshold]

        # 4. 발송 여부 결정
        only_when_drift = getattr(alert, "only_when_drift", True)
        if only_when_drift:
            if not drifting:
                continue
            items_to_show = drifting
            is_scheduled_report = False
        else:
            items_to_show = analysis.items
            is_scheduled_report = True

        mode = getattr(alert, "mode", "NOTIFY")
        email = notification_email or user_email

        if mode == "AUTO" and alert.account_id and drifting:
            # 5a. AUTO 모드: 자동 주문 실행
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
                    continue
        else:
            # 5b. NOTIFY 모드: 이메일 알림만
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
                continue

        drift_desc = f"{len(drifting)}개 종목 드리프트" if drifting else "정기 보고"
        await _save_alert_history(
            db,
            alert.user_id,
            "REBALANCING",
            f"리밸런싱 알림: {portfolio.name} — {drift_desc} ({alert.schedule_type})",
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
            StockPriceAlert, User.email,
            UserSettings.notification_email, UserSettings.fcm_token,
        )
        .join(User, User.id == StockPriceAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(StockPriceAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()
    if not rows:
        return

    # ticker별 그룹화 후 배치 조회 (user_id는 첫 번째 유저 기준)
    sample_user_id = rows[0][0].user_id
    unique_tickers = list({(a.ticker, a.market) for a, _, _, _ in rows})
    price_map = await fetch_prices_batch(sample_user_id, unique_tickers, db, redis)

    triggered_count = 0
    for alert, user_email, notification_email, fcm_token in rows:
        price = price_map.get(alert.ticker)
        if not price:
            continue

        target = float(alert.target_price)
        should_trigger = (
            (alert.direction == "BELOW" and price <= target)
            or (alert.direction == "ABOVE" and price >= target)
        )
        if not should_trigger:
            continue

        if alert.max_trigger_count > 1 and alert.triggered_at:
            elapsed = datetime.now(tz=UTC) - alert.triggered_at
            if elapsed < _MULTI_TRIGGER_COOLDOWN:
                continue

        email = notification_email or user_email
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
        await _save_alert_history(
            db,
            alert.user_id,
            "STOCK_PRICE",
            (
                f"주가 알림: {alert.name}({alert.ticker})"
                f" {price:,.0f}원 (목표 {target:,.0f}원 {direction_label})"
            ),
        )
        triggered_count += 1

    if triggered_count:
        await db.commit()
        alert_trigger_count.labels(alert_type="stock_price").inc(triggered_count)
        logger.info("stock_price_alerts_triggered", count=triggered_count)
