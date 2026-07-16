"""Supabase JWT 검증 서비스."""

from datetime import timedelta

import httpx
import jwt
import structlog
from jwt import PyJWKClient

from app.core.config import settings

logger = structlog.get_logger()

_jwks_client: PyJWKClient | None = None

_LEEWAY = timedelta(seconds=5)
_SUPABASE_TIMEOUT = 10.0


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            f"{settings.supabase_project_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
    return _jwks_client


def verify_supabase_token(token: str) -> dict:
    """Supabase 발급 JWT를 검증하고 payload를 반환.

    Raises ValueError on expired or invalid token.
    """
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[signing_key.algorithm_name],
            options={"verify_exp": True, "verify_aud": True},
            audience="authenticated",
            leeway=_LEEWAY,
        )
    except jwt.ExpiredSignatureError as e:
        raise ValueError("Token expired") from e
    except jwt.InvalidTokenError as e:
        logger.warning("token_verification_failed", error_type=type(e).__name__, detail=str(e))
        raise ValueError("Invalid token") from e
    except Exception as e:
        logger.error("jwks_fetch_failed", error=str(e))
        raise ValueError("Token verification failed") from e


async def verify_password(email: str, password: str) -> bool:
    """Supabase password grant로 이메일/비밀번호를 검증한다.

    회원 탈퇴처럼 로컬에 비밀번호 해시가 없는 민감 작업의 재인증 게이트로 사용.
    """
    async with httpx.AsyncClient(timeout=_SUPABASE_TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{settings.supabase_project_url}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": settings.supabase_anon_key},
                json={"email": email, "password": password},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.error("supabase_password_verify_unreachable", error=str(e))
            raise
    return resp.status_code == 200


async def delete_supabase_user(user_id: str) -> None:
    """Supabase Admin API로 Auth 유저(이메일/비밀번호 아이덴티티)를 삭제한다.

    실패 시 예외를 그대로 전파 — 호출부에서 로컬 데이터 삭제 여부를 결정한다.
    """
    async with httpx.AsyncClient(timeout=_SUPABASE_TIMEOUT) as client:
        resp = await client.delete(
            f"{settings.supabase_project_url}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
    resp.raise_for_status()
