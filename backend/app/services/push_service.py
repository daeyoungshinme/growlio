"""FCM 푸시 알림 서비스 — firebase-admin 기반.

FIREBASE_CREDENTIALS_JSON 환경변수가 없으면 모든 호출이 no-op으로 처리됩니다.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog

logger = structlog.get_logger()

_firebase_app: object | None = None
_firebase_initialized = False


def _get_firebase_app() -> object | None:
    """Firebase 앱 인스턴스 반환. 자격증명 미설정 시 None."""
    global _firebase_app, _firebase_initialized
    if _firebase_initialized:
        return _firebase_app

    _firebase_initialized = True
    from app.config import settings

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


async def send_push(
    fcm_token: str | None,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> bool:
    """FCM 토큰으로 푸시 알림 발송.

    Firebase 미설정이거나 토큰이 없으면 False 반환. 실패해도 예외 전파 없음.
    """
    app = _get_firebase_app()
    if app is None or not fcm_token:
        return False

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
        return True
    except Exception as exc:
        err = str(exc)
        if "registration-token-not-registered" in err or "invalid-registration-token" in err:
            logger.info("push_token_invalid", hint="token should be cleared")
        else:
            logger.warning("push_failed", error=err)
        return False


async def send_push_to_user(
    user_id: uuid.UUID,
    title: str,
    body: str,
    fcm_token: str | None,
    data: dict[str, str] | None = None,
) -> bool:
    """user_id 로깅 컨텍스트 포함 푸시 발송 (alert_service.py에서 사용)."""
    result = await send_push(fcm_token, title, body, data)
    if result:
        logger.info("push_delivered", user_id=str(user_id))
    return result
