"""Supabase JWT 검증 서비스."""

from datetime import timedelta

import httpx
import jwt
import structlog
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError

from app.core.config import settings
from app.core.job_runner import report_handled_failure

logger = structlog.get_logger()

_jwks_client: PyJWKClient | None = None

_LEEWAY = timedelta(seconds=5)
_SUPABASE_TIMEOUT = 10.0
# JWKS fetch는 동기 urllib이라 이벤트 루프를 막는다 — 기본 30초 대신 짧게(키가 캐시돼 있으면 fetch 없음)
_JWKS_TIMEOUT = 5


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            f"{settings.supabase_project_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            timeout=_JWKS_TIMEOUT,
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
    except PyJWKClientConnectionError as e:
        # JWKS 엔드포인트 장애면 모든 인증 요청이 401이 된다 — Sentry로 알린다(plans/95 B)
        report_handled_failure("jwks_fetch_failed", e)
        raise ValueError("Token verification failed") from e
    except PyJWKClientError as e:
        # 알 수 없는 kid 등 토큰 쪽 문제 — 장애가 아니므로 warning
        logger.warning("jwks_signing_key_not_found", error=str(e))
        raise ValueError("Invalid token") from e
    except Exception as e:
        report_handled_failure("jwks_fetch_failed", e)
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
        except httpx.TransportError as e:
            # Connect/Timeout뿐 아니라 ReadError 등도 — 좁게 잡으면 나머지가 500으로 샜다
            logger.error("supabase_password_verify_unreachable", error=str(e))
            raise
    if resp.status_code == 429 or resp.status_code >= 500:
        # 레이트리밋·장애를 "비밀번호 불일치"로 보이지 않게 호출부(503)로 넘긴다(plans/61 D)
        logger.error("supabase_password_verify_unavailable", status=resp.status_code)
        resp.raise_for_status()
    return resp.status_code == 200


async def supabase_user_exists(user_id: str) -> bool:
    """Supabase Admin API로 Auth 유저 존재 여부를 확인한다 (200 → True, 404 → False, 그 외 예외 전파)."""
    async with httpx.AsyncClient(timeout=_SUPABASE_TIMEOUT) as client:
        resp = await client.get(
            f"{settings.supabase_project_url}/auth/v1/admin/users/{user_id}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
    if resp.status_code == 404:
        return False
    resp.raise_for_status()
    return True


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
