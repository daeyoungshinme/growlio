"""리밸런싱 자동화 알림 즉시 테스트 발송."""

from __future__ import annotations

import contextlib
import uuid
from typing import Any, Literal, cast

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import save_alert_history
from app.services.rebalancing.alert_scope import resolve_effective_account_ids
from app.services.rebalancing.order_builder import build_rebalancing_orders, filter_drifting_items

__all__ = ["send_test_rebalancing_alert"]

logger = structlog.get_logger()


async def send_test_rebalancing_alert(
    portfolio_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    account_id: uuid.UUID | None = None,
    redis: Any = None,
) -> dict[str, bool]:
    """리밸런싱 자동화 알림을 즉시 테스트 발송한다.

    스케줄/드리프트 조건 및 시장 신호 게이트를 무시하고 현재 포트폴리오 데이터로 발송.
    `account_id`는 portfolio.alert_scope == PER_ACCOUNT일 때 어느 계좌 전용 알림 행을
    테스트할지 지정한다(AGGREGATE면 무시하고 alert_scope == "AGGREGATE" 행을 조회).
    반환: {"email_sent": bool, "push_sent": bool}
    """
    from app.services.email_service import send_rebalancing_alert
    from app.services.portfolio_service import build_portfolio_overview
    from app.services.push_service import send_push_to_user
    from app.services.rebalancing.service import analyze_rebalancing

    account_filter = (
        (RebalancingAlert.alert_scope == "PER_ACCOUNT") & (RebalancingAlert.account_id == account_id)
        if account_id is not None
        else RebalancingAlert.alert_scope == "AGGREGATE"
    )
    result = await db.execute(
        select(RebalancingAlert, Portfolio, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == RebalancingAlert.user_id)
        .options(selectinload(Portfolio.linked_accounts), selectinload(Portfolio.items))
        .where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == user_id,
            account_filter,
        )
    )
    row = result.first()
    if not row:
        raise ValueError("알림 설정을 찾을 수 없습니다")

    alert, portfolio, user_email, notification_email, fcm_token = row
    email = notification_email or user_email
    threshold = float(alert.threshold_pct)

    effective_account_ids = resolve_effective_account_ids(alert, portfolio)

    items_to_show: list = []
    drifting: list = []
    ticker_account_map: dict[str, list] = {}
    try:
        overview = await build_portfolio_overview(user_id, db, account_ids=effective_account_ids, redis=redis)
        analysis = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
        drifting = filter_drifting_items(analysis.items, threshold)
        items_to_show = analysis.items
        ticker_account_map = analysis.ticker_account_map
    except Exception as exc:
        logger.error("test_rebalancing_alert_analysis_failed", portfolio_id=str(portfolio_id), error=str(exc))

    order_preview_items: list = []
    if drifting:
        strategy = getattr(alert, "strategy", "BUY_ONLY")
        order_type = cast(Literal["MARKET", "LIMIT"], getattr(alert, "order_type", "MARKET"))
        buy_account_id = str(alert.account_id) if alert.account_id else ""
        order_preview_items = build_rebalancing_orders(
            drifting, ticker_account_map, strategy, order_type, buy_account_id, alert_id=str(alert.id)
        )

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
            order_preview_items=order_preview_items,
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
