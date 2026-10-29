"""유저별 이메일+푸시 2채널 알림 발송 공용 헬퍼.

여러 알림 서비스(등급전환/매일요약/추천드리프트/연말절세 등)가 반복하던
"이메일 시도 → 실패 로깅 → 푸시 시도 → 실패 로깅 → 하나라도 성공하면 AlertHistory 저장"
블록을 한 곳으로 모은다. 발송 조건 판정(구독자 조회·dedup·콘텐츠 생성)은 각 서비스가 그대로 담당.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.alerts.alert_service import save_alert_history

logger = structlog.get_logger()


async def send_push_safely(
    user_id: uuid.UUID,
    *,
    title: str,
    body: str,
    fcm_token: str | None,
    data: dict[str, str] | None,
    failure_event: str,
    **log_context: str,
) -> bool:
    """푸시 1건을 보내고 예외는 `failure_event`로 로깅한 뒤 삼킨다. 반환: 발송 성공 여부.

    이메일 성공 여부·이력 저장 규칙이 알림마다 달라 `dispatch_dual_channel_alert`로 묶을 수 없는
    곳(플랜 생성·leg 실행 결과·드리프트 리포트·목표 달성·가격 알림)도 푸시 시도부는 이 함수 하나를 쓴다.
    """
    from app.services.push_service import send_push_to_user

    try:
        return await send_push_to_user(user_id=user_id, title=title, body=body, fcm_token=fcm_token, data=data)
    except Exception as exc:
        logger.error(failure_event, user_id=str(user_id), error=str(exc), **log_context)
        return False


async def dispatch_dual_channel_alert(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    event_prefix: str,
    alert_type: str,
    history_message: str,
    send_email: Callable[[], Awaitable[bool]],
    push_title: str,
    push_body: str,
    push_type: str,
    fcm_token: str | None,
    commit: bool = True,
    after_sent: Callable[[], Awaitable[None]] | None = None,
    push_data: dict[str, str] | None = None,
) -> bool:
    """이메일·푸시를 각각 독립적으로 시도하고, 하나라도 성공하면 `AlertHistory`를 저장한다.

    - `send_email`: 인자 없는 코루틴 팩토리(`lambda: send_x_email(to, ...)`) — bool 반환.
    - 각 채널 실패는 `<event_prefix>_email_failed` / `<event_prefix>_push_failed`로 로깅하고 삼킨다.
    - `after_sent`: 발송 성공 시 커밋 전에 실행할 추가 작업(예: dedup 플래그 마킹).
    - `commit=False`면 커밋을 호출부에 위임한다(루프 후 일괄 커밋하는 경우).
    - `push_data`: 푸시 data에 `type` 외에 더 실을 값(예: 탭 시 열 `portfolio_id`).

    반환: 이메일·푸시 중 하나라도 성공했으면 True.
    """
    email_sent = False
    try:
        email_sent = await send_email()
    except Exception as exc:
        logger.error(f"{event_prefix}_email_failed", user_id=str(user_id), error=str(exc))

    push_sent = await send_push_safely(
        user_id,
        title=push_title,
        body=push_body,
        fcm_token=fcm_token,
        data={"type": push_type, **(push_data or {})},
        failure_event=f"{event_prefix}_push_failed",
    )

    if not (email_sent or push_sent):
        return False

    await save_alert_history(db, user_id, alert_type, history_message)
    if after_sent is not None:
        await after_sent()
    if commit:
        await db.commit()
    return True
