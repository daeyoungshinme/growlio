"""공통 알림 저장/조회 서비스.

환율 알림 → alerts/exchange_rate_service.py
주가 알림 → alerts/stock_price_service.py
리밸런싱 알림 → rebalancing/alert_check.py, rebalancing/alert_test.py, rebalancing/alert_scope.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertHistory
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


async def notify_and_record_trigger(
    db: AsyncSession,
    alert: Any,
    history_alert_type: str,
    history_message: str,
    user_id: uuid.UUID,
    push_title: str,
    push_body: str,
    fcm_token: str | None,
) -> None:
    """알림 발동 시 공용 후속 처리: 푸시 발송 → trigger 상태 갱신 → 이력 저장.

    alerts/exchange_rate_service.py/alerts/stock_price_service.py가 이메일 발송 성공 후
    공유하는 마무리 단계 — 이메일 발송 자체는 알림 종류별 템플릿이 달라 호출부에서 처리한다.
    `history_alert_type`은 AlertHistory.alert_type에 저장되는 값(예: "EXCHANGE_RATE")으로,
    Prometheus 메트릭 라벨(소문자, 예: "exchange_rate")과는 별개다 — 후자는 finalize_alert_batch에 전달한다.
    """
    from app.services.push_service import send_push_to_user

    await send_push_to_user(user_id=user_id, title=push_title, body=push_body, fcm_token=fcm_token)
    await apply_alert_trigger(db, alert, history_alert_type, history_message)


async def finalize_alert_batch(
    db: AsyncSession,
    metric_alert_type: str,
    triggered_count: int,
    **log_kwargs: Any,
) -> None:
    """알림 체크 루프 종료 후 공용 마무리: 발동 건이 있으면 commit + 메트릭 + 로그.

    `metric_alert_type`은 Prometheus 라벨/로그 이벤트명에 쓰이는 소문자 slug(예: "exchange_rate").
    """
    if not triggered_count:
        return
    await db.commit()
    alert_trigger_count.labels(alert_type=metric_alert_type).inc(triggered_count)
    logger.info(f"{metric_alert_type}_alerts_triggered", count=triggered_count, **log_kwargs)


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
    "send_test_rebalancing_alert",
]


def __getattr__(name: str):
    if name == "check_and_trigger_alerts":
        from app.services.alerts.exchange_rate_service import check_and_trigger_alerts

        return check_and_trigger_alerts
    if name == "check_and_trigger_stock_price_alerts":
        from app.services.alerts.stock_price_service import check_and_trigger_stock_price_alerts

        return check_and_trigger_stock_price_alerts
    if name == "check_rebalancing_alerts":
        from app.services.rebalancing.alert_check import check_rebalancing_alerts

        return check_rebalancing_alerts
    if name == "send_test_rebalancing_alert":
        from app.services.rebalancing.alert_test import send_test_rebalancing_alert

        return send_test_rebalancing_alert
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
