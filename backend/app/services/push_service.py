"""FCM 푸시 알림 서비스 — firebase-admin 기반.

FIREBASE_CREDENTIALS_JSON 환경변수가 없으면 모든 호출이 no-op으로 처리됩니다.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from enum import StrEnum

import structlog
from sqlalchemy import update

logger = structlog.get_logger()

_firebase_app: object | None = None
_firebase_initialized = False


def _get_firebase_app() -> object | None:
    """Firebase 앱 인스턴스 반환. 자격증명 미설정 시 None."""
    global _firebase_app, _firebase_initialized
    if _firebase_initialized:
        return _firebase_app

    _firebase_initialized = True
    from app.core.config import settings

    if not settings.firebase_credentials_json:
        logger.info("firebase_push_disabled", reason="FIREBASE_CREDENTIALS_JSON not set")
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred_dict = json.loads(settings.firebase_credentials_json)
        cred = credentials.Certificate(cred_dict)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("firebase_initialized")
        return _firebase_app
    except Exception as exc:
        logger.error("firebase_init_failed", error=str(exc))
        return None


class PushResult(StrEnum):
    SENT = "sent"
    SKIPPED = "skipped"  # Firebase 미설정 또는 토큰 없음
    INVALID_TOKEN = "invalid_token"  # nosec B105 — 결과 코드; 앱 삭제·재설치 등으로 FCM이 토큰을 폐기함
    FAILED = "failed"


async def deliver_push(
    fcm_token: str | None,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> PushResult:
    """FCM 토큰으로 푸시 알림 발송 — 결과를 구분해 돌려준다. 실패해도 예외 전파 없음."""
    app = _get_firebase_app()
    if app is None or not fcm_token:
        return PushResult.SKIPPED

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=fcm_token,
            data=data or {},
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: messaging.send(message, app=app))
        logger.info("push_sent")
        return PushResult.SENT
    except Exception as exc:
        err = str(exc)
        if "registration-token-not-registered" in err or "invalid-registration-token" in err:
            logger.info("push_token_invalid")
            return PushResult.INVALID_TOKEN
        logger.warning("push_failed", error=err)
        return PushResult.FAILED


async def send_push(
    fcm_token: str | None,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> bool:
    """FCM 토큰으로 푸시 알림 발송. Firebase 미설정·토큰 없음·실패 시 False."""
    return await deliver_push(fcm_token, title, body, data) is PushResult.SENT


async def _clear_invalid_token(user_id: uuid.UUID, fcm_token: str) -> None:
    """폐기된 토큰을 지워 이후 알림 잡(5~10분 주기)이 같은 토큰으로 FCM을 계속 부르지 않게 한다.

    호출부들이 각자 트랜잭션 중간에 푸시를 보내므로 그 세션을 건드리지 않고 별도 세션에서 커밋한다.
    그 사이 사용자가 새 토큰을 등록했으면 덮어쓰지 않도록 토큰 값까지 일치할 때만 지운다(plans/61 A4).
    """
    from app.core.database import AsyncSessionLocal
    from app.models.user import UserSettings

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(UserSettings)
                .where(UserSettings.user_id == user_id, UserSettings.fcm_token == fcm_token)
                .values(fcm_token=None)
            )
            await db.commit()
        logger.info("push_token_cleared", user_id=str(user_id))
    except Exception as exc:
        logger.warning("push_token_clear_failed", user_id=str(user_id), error=str(exc))


async def send_push_to_user(
    user_id: uuid.UUID,
    title: str,
    body: str,
    fcm_token: str | None,
    data: dict[str, str] | None = None,
) -> bool:
    """user_id 로깅 컨텍스트 포함 푸시 발송 (alert_service.py에서 사용). 폐기된 토큰은 지운다."""
    result = await deliver_push(fcm_token, title, body, data)
    if result is PushResult.SENT:
        logger.info("push_delivered", user_id=str(user_id))
        return True
    if result is PushResult.INVALID_TOKEN and fcm_token:
        await _clear_invalid_token(user_id, fcm_token)
    return False
