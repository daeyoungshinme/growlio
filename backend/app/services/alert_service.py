"""공통 알림 저장/조회 서비스.

환율 알림 → exchange_rate_alert_service.py
주가 알림 → stock_price_alert_service.py
리밸런싱 알림 → rebalancing_alert_service.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertHistory

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


async def list_alert_history(
    user_id: uuid.UUID,
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
):
    result = await db.execute(
        select(AlertHistory)
        .where(AlertHistory.user_id == user_id)
        .order_by(AlertHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# backward-compatible re-exports (lazy to avoid circular import)
__all__ = [  # noqa: F822
    "check_and_trigger_alerts",
    "check_and_trigger_stock_price_alerts",
    "check_rebalancing_alerts",
    "execute_auto_rebalancing_for_alert",
    "send_test_rebalancing_alert",
    "build_rebalancing_orders",
    "refresh_live_prices",
]


def __getattr__(name: str):
    if name == "check_and_trigger_alerts":
        from app.services.exchange_rate_alert_service import check_and_trigger_alerts

        return check_and_trigger_alerts
    if name == "check_and_trigger_stock_price_alerts":
        from app.services.stock_price_alert_service import check_and_trigger_stock_price_alerts

        return check_and_trigger_stock_price_alerts
    if name in (
        "check_rebalancing_alerts",
        "execute_auto_rebalancing_for_alert",
        "send_test_rebalancing_alert",
        "build_rebalancing_orders",
        "refresh_live_prices",
    ):
        import app.services.rebalancing_alert_service as _rebalancing_alert_service

        return getattr(_rebalancing_alert_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
