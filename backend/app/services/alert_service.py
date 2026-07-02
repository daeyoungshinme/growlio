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
from sqlalchemy.orm import selectinload

from app.models.alert import AlertHistory, RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alert_calculator import (
    already_fired_today,
    should_fire_today,
)
from app.utils.market_hours import is_alert_execution_time
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
__all__ = [  # noqa: F822
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

    이메일·FCM 중 하나라도 성공하면 True 반환. 둘 다 실패하면 False 반환.
    """
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

    # AUTO 모드 실행은 rebalancing_auto_execution 인트라데이 잡이 전담한다.
    # 08:30 daily job(check_rebalancing_alerts)에서는 이메일/FCM 리포트만 발송한다.

    drift_count = len(drifting)
    push_title = f"리밸런싱 알림 — {portfolio.name}"
    push_body = (
        f"{drift_count}개 종목이 ±{threshold:.1f}% 이상 이탈했습니다."
        if drift_count
        else f"{portfolio.name} 정기 리밸런싱 리포트"
    )

    # 이메일 독립 처리
    email_sent = False
    try:
        email_sent = await send_rebalancing_alert(
            to_email=email,
            portfolio_name=portfolio.name,
            threshold_pct=threshold,
            items_to_show=items_to_show,
            drifting_count=drift_count,
            is_scheduled_report=is_scheduled_report,
            schedule_type=getattr(alert, "schedule_type", "DAILY"),
        )
    except Exception as exc:
        logger.error("rebalancing_alert_email_failed", alert_id=str(alert.id), error=str(exc))

    # FCM 독립 처리 — 이메일 실패와 무관하게 항상 시도
    push_sent = False
    with contextlib.suppress(Exception):
        push_sent = await send_push_to_user(
            user_id=alert.user_id,
            title=push_title,
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING", "portfolio_id": str(portfolio.id)},
        )

    any_sent = email_sent or push_sent
    if not any_sent:
        logger.warning(
            "rebalancing_alert_no_channel_sent",
            alert_id=str(alert.id),
            email_sent=email_sent,
            push_sent=push_sent,
        )
    return any_sent


_BROKER_ASSET_TYPES = {"STOCK_KIS", "STOCK_KIWOOM"}


async def execute_auto_rebalancing_for_alert(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    drifting: list,
    db: AsyncSession,
    ticker_account_map: dict[str, list] | None = None,
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

    return await _execute_auto_rebalancing(alert, portfolio, drifting, db, ticker_account_map or {})


def _build_sell_orders(
    item: Any,
    qty: int,
    ticker_account_map: dict[str, list],
    effective_order_type: str,
    limit_price: float | None,
    reference_price: float | None = None,
) -> list[Any]:
    """매도 주문을 실제 종목을 보유한 브로커 연동 계좌(들)로 분산 생성한다.

    포트폴리오 전체 합산 기준으로 계산된 매도 수량을, 종목을 실제로 보유한 계좌들 중
    보유수량이 큰 순서로 채워나간다. 배분 후에도 부족분이 남으면 억지로 다른 계좌에 밀어넣지 않고
    건너뛴다(계좌 실행 시점의 실시간 잔고 clamp가 최종 안전망 역할을 한다).
    """
    from app.schemas.rebalancing import ExecutionOrderItem

    holders = [
        a for a in ticker_account_map.get(item.ticker, []) if a.asset_type in _BROKER_ASSET_TYPES and a.quantity > 0
    ]
    holders.sort(key=lambda a: a.quantity, reverse=True)

    orders: list[Any] = []
    remaining = qty
    for acc in holders:
        if remaining <= 0:
            break
        take = min(remaining, int(acc.quantity))
        if take <= 0:
            continue
        orders.append(
            ExecutionOrderItem(
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                side="SELL",
                quantity=take,
                account_id=acc.account_id,
                order_type=effective_order_type,
                limit_price=limit_price,
                reference_price=reference_price,
            )
        )
        remaining -= take

    if remaining > 0:
        logger.info(
            "rebalancing_auto_sell_unallocated",
            ticker=item.ticker,
            requested_qty=qty,
            unallocated_qty=remaining,
            holder_accounts=len(holders),
        )
    return orders


async def refresh_live_prices(
    items: list,
    user_id: uuid.UUID,
    db: AsyncSession,
    redis: Any = None,
) -> None:
    """드리프트 항목의 `current_price_krw`를 실시간 시세로 갱신한다 (in-place).

    `analyze_rebalancing()`이 채운 `current_price_krw`는 계좌 동기화 시점의 DB 스냅샷 값이라
    자동실행·원클릭실행 시점에는 이미 낡았을 수 있다. 수동 실행 모달(`/stocks/prices-batch`)과
    동일하게 `price_service.fetch_prices_batch()`로 실시간 시세를 조회해 지정가 산정에 반영한다.
    조회 실패 종목은 기존 값을 그대로 둔다(폴백).
    """
    from app.services.price_service import fetch_prices_batch

    tickers = [(item.ticker, item.market) for item in items if item.ticker not in ("CASH", "REAL_ESTATE")]
    if not tickers:
        return

    try:
        price_map = await fetch_prices_batch(user_id, tickers, db, redis)
    except Exception as exc:
        logger.warning("rebalancing_live_price_refresh_failed", error=str(exc))
        return

    for item in items:
        price = price_map.get(item.ticker)
        if price and price > 0:
            item.current_price_krw = float(price)


def build_rebalancing_orders(
    drifting: list,
    ticker_account_map: dict[str, list],
    strategy: str,
    order_type: Literal["MARKET", "LIMIT"],
    buy_account_id: str,
    alert_id: str | None = None,
) -> list[Any]:
    """드리프트 항목 목록으로부터 실행 주문 목록을 생성한다.

    매도 주문은 `ticker_account_map`을 사용해 실제 종목을 보유한 브로커 연동 계좌(들)로
    분산 생성하고, 매수 주문은 `buy_account_id` 단일 계좌로 생성한다.
    AUTO 자동실행(`_execute_auto_rebalancing`)과 원클릭 실행(`quick_execute_rebalancing`)이
    공유하는 주문 생성 로직 — 두 경로가 서로 다른 동작을 하지 않도록 여기서 단일화한다.
    """
    from app.schemas.rebalancing import ExecutionOrderItem

    ticker_account_map = ticker_account_map or {}
    orders: list[ExecutionOrderItem] = []
    for item in drifting:
        if item.ticker in ("CASH", "REAL_ESTATE") or item.shares_to_trade is None:
            logger.info(
                "rebalancing_auto_item_skipped",
                alert_id=alert_id,
                ticker=item.ticker,
                reason="cash_or_no_shares_to_trade",
            )
            continue
        qty = abs(int(item.shares_to_trade))
        if qty <= 0:
            logger.info(
                "rebalancing_auto_item_skipped",
                alert_id=alert_id,
                ticker=item.ticker,
                reason="zero_qty",
                shares_to_trade=item.shares_to_trade,
            )
            continue
        side = "BUY" if item.diff_krw > 0 else "SELL"
        if strategy == "BUY_ONLY" and side == "SELL":
            logger.info(
                "rebalancing_auto_item_skipped",
                alert_id=alert_id,
                ticker=item.ticker,
                reason="buy_only_strategy",
            )
            continue

        # LIMIT 주문 시 현재가를 지정가로 사용 (None이면 MARKET으로 fallback)
        effective_order_type = order_type
        current_price = getattr(item, "current_price_krw", None)
        reference_price: float | None = float(current_price) if current_price and current_price > 0 else None
        limit_price: float | None = None
        if order_type == "LIMIT":
            if reference_price is not None:
                limit_price = reference_price
            else:
                effective_order_type = "MARKET"

        if side == "SELL":
            orders.extend(
                _build_sell_orders(item, qty, ticker_account_map, effective_order_type, limit_price, reference_price)
            )
            continue

        orders.append(
            ExecutionOrderItem(
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                side=side,
                quantity=qty,
                account_id=buy_account_id,
                order_type=effective_order_type,
                limit_price=limit_price,
                reference_price=reference_price,
            )
        )

    return orders


async def _execute_auto_rebalancing(
    alert,
    portfolio: Portfolio,
    drifting: list,
    db: AsyncSession,
    ticker_account_map: dict[str, list] | None = None,
) -> bool:
    """AUTO 모드 리밸런싱 주문을 생성하고 실행한다 (내부용, 장 중 체크 없음).

    성공 시 True, 오류 시 False 반환.
    """
    from app.redis_client import get_redis
    from app.services.rebalancing_execution_service import execute_rebalancing

    strategy = getattr(alert, "strategy", "BUY_ONLY")
    order_type = cast(Literal["MARKET", "LIMIT"], getattr(alert, "order_type", "MARKET"))

    redis = await get_redis()
    await refresh_live_prices(drifting, alert.user_id, db, redis)

    orders = build_rebalancing_orders(
        drifting, ticker_account_map or {}, strategy, order_type, str(alert.account_id), alert_id=str(alert.id)
    )

    if orders:
        try:
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


async def send_test_rebalancing_alert(
    portfolio_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, bool]:
    """리밸런싱 자동화 알림을 즉시 테스트 발송한다.

    스케줄/드리프트 조건 및 시장 신호 게이트를 무시하고 현재 포트폴리오 데이터로 발송.
    반환: {"email_sent": bool, "push_sent": bool}
    """
    from app.services.email_service import send_rebalancing_alert
    from app.services.portfolio_service import build_portfolio_overview
    from app.services.push_service import send_push_to_user
    from app.services.rebalancing_service import analyze_rebalancing

    result = await db.execute(
        select(RebalancingAlert, Portfolio, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == RebalancingAlert.user_id)
        .options(selectinload(Portfolio.linked_accounts), selectinload(Portfolio.items))
        .where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == user_id,
        )
    )
    row = result.first()
    if not row:
        raise ValueError("알림 설정을 찾을 수 없습니다")

    alert, portfolio, user_email, notification_email, fcm_token = row
    email = notification_email or user_email
    threshold = float(alert.threshold_pct)

    saved_ids = getattr(portfolio, "account_ids", None)
    effective_account_ids: list[uuid.UUID] | None = [uuid.UUID(aid) for aid in saved_ids] if saved_ids else None

    items_to_show: list = []
    drifting: list = []
    try:
        overview = await build_portfolio_overview(user_id, db, account_ids=effective_account_ids)
        analysis = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
        drifting = [item for item in analysis.items if abs(item.weight_diff_pct) > threshold]
        items_to_show = analysis.items
    except Exception as exc:
        logger.error("test_rebalancing_alert_analysis_failed", portfolio_id=str(portfolio_id), error=str(exc))

    email_sent = False
    try:
        email_sent = await send_rebalancing_alert(
            to_email=email,
            portfolio_name=portfolio.name,
            threshold_pct=threshold,
            items_to_show=items_to_show,
            drifting_count=len(drifting),
            is_scheduled_report=False,
            schedule_type=getattr(alert, "schedule_type", "DAILY"),
            is_test=True,
        )
    except Exception as exc:
        logger.error("test_rebalancing_alert_email_failed", portfolio_id=str(portfolio_id), error=str(exc))

    push_sent = False
    drift_info = f"{len(drifting)}개 종목이 ±{threshold:.1f}% 이상 이탈" if drifting else "현재 이탈 없음"
    with contextlib.suppress(Exception):
        push_sent = await send_push_to_user(
            user_id=user_id,
            title=f"[테스트] 리밸런싱 알림 — {portfolio.name}",
            body=f"테스트 알림입니다. {drift_info}.",
            fcm_token=fcm_token,
            data={"type": "REBALANCING", "portfolio_id": str(portfolio.id)},
        )

    await save_alert_history(db, user_id, "REBALANCING", f"[테스트] 리밸런싱 알림: {portfolio.name}")
    await db.commit()

    return {"email_sent": email_sent, "push_sent": push_sent}


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
        .options(selectinload(Portfolio.linked_accounts), selectinload(Portfolio.items))
        .where(RebalancingAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, portfolio, user_email, notification_email, fcm_token in rows:
        # 각 알림의 notify_time(HH:MM)과 현재 시각이 일치(±4분)하는지 확인
        notify_time = getattr(alert, "notify_time", "08:30")
        if not is_alert_execution_time(notify_time):
            continue

        trigger_condition = getattr(alert, "trigger_condition", "DRIFT_ONLY")
        is_schedule_day = should_fire_today(alert)

        # BOTH: 매일 체크; DRIFT_ONLY/SCHEDULE_ONLY: 스케줄 날만 체크
        if not is_schedule_day and trigger_condition != "BOTH":
            logger.debug(
                "rebalancing_alert_not_schedule_day",
                alert_id=str(alert.id),
                schedule=alert.schedule_type,
                trigger_condition=trigger_condition,
            )
            continue
        if already_fired_today(alert):
            logger.debug("rebalancing_alert_already_fired_today", alert_id=str(alert.id))
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
            logger.debug(
                "rebalancing_alert_no_items_selected",
                alert_id=str(alert.id),
                trigger_condition=trigger_condition,
                drifting_count=len(drifting),
            )
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
        # AUTO 모드는 last_triggered_at을 갱신하지 않는다.
        # 인트라데이 잡(rebalancing_auto_execution)에서 실제 실행 후 갱신하므로,
        # 여기서 갱신하면 already_fired_today()가 True → 당일 자동 실행 차단됨.
        if getattr(alert, "mode", "NOTIFY") != "AUTO":
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
