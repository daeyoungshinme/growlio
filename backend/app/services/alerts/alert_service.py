"""공통 알림 저장/조회 서비스.

환율 알림 → alerts/exchange_rate_service.py
주가 알림 → alerts/stock_price_service.py
리밸런싱 알림 → rebalancing/alert_check.py, rebalancing/alert_test.py, rebalancing/alert_scope.py
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import redact_secrets
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
    # 발송 직후 항목별로 commit한다 — 루프 끝에서 한 번만 commit하면 중간 DB 오류 시 이미 보낸 알림의
    # trigger 갱신까지 롤백돼 다음 실행(5~10분 뒤)에 같은 메일이 다시 간다. expire_on_commit=False라
    # 루프가 이미 읽어 둔 다른 알림 객체는 그대로 쓸 수 있다.
    await db.commit()


async def run_isolated_alert_loop(
    db: AsyncSession,
    rows: Sequence[Any],
    handle_row: Callable[[Any], Awaitable[bool]],
    event: str,
) -> int:
    """알림 행마다 `handle_row`를 격리 실행하고 발동 건수를 돌려준다.

    항목별 commit이 DB 오류로 실패하면 세션이 실패 상태라 rollback해야 다음 항목을 처리할 수 있다. rollback은
    세션의 ORM 객체를 모두 expire시키므로(expire_on_commit과 무관) 이후 행의 알림 객체(row[0])는 쓰기 전에
    명시적으로 refresh한다 — 그대로 접근하면 비동기 세션에서 lazy load(MissingGreenlet)가 난다.
    """
    triggered = 0
    needs_refresh = False
    for row in rows:
        try:
            if needs_refresh:
                await db.refresh(row[0])
            if await handle_row(row):
                triggered += 1
        except Exception as e:
            logger.error(event, error=redact_secrets(str(e)), error_type=type(e).__name__)
            await db.rollback()
            needs_refresh = True
    return triggered


async def finalize_alert_batch(
    db: AsyncSession,
    metric_alert_type: str,
    triggered_count: int,
    **log_kwargs: Any,
) -> None:
    """알림 체크 루프 종료 후 공용 마무리: 발동 건이 있으면 메트릭 + 로그 (commit은 항목별로 이미 끝남).

    `metric_alert_type`은 Prometheus 라벨/로그 이벤트명에 쓰이는 소문자 slug(예: "exchange_rate").
    """
    if not triggered_count:
        return
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
