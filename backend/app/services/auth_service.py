"""Supabase JWT 검증 서비스."""

from datetime import timedelta

import jwt
import structlog
from jwt import PyJWKClient

from app.config import settings

logger = structlog.get_logger()

_jwks_client: PyJWKClient | None = None

_LEEWAY = timedelta(seconds=5)


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
