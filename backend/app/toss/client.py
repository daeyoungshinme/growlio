"""토스증권 Open API 기본 HTTP 클라이언트 — 속도제한 + 재시도 포함.

KIS/키움과 동일하게 `providers/http_client.broker_request()`에 위임하되, 토스 특유의
응답 형태를 어댑팅한다:
  - 성공 응답은 `{"result": ...}`로 감싸져 온다 (호출부가 언랩).
  - 오류 응답은 `{"error": {"requestId", "code", "message", "data"}}` 형태.
  - 토큰 만료는 HTTP 401 + code `expired-token`/`invalid-token`.
  - rate limit은 HTTP 429 + code `rate-limit-exceeded`/`edge-rate-limit-exceeded`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.core.config import settings
from app.providers.http_client import AsyncRateLimiter, broker_request
from app.toss.constants import TOSS_BASE_URL

logger = structlog.get_logger()

_semaphore = asyncio.Semaphore(settings.toss_semaphore_limit)
_rate_limiter = AsyncRateLimiter(rate=settings.toss_rate_per_second)

_TOKEN_ERROR_CODES = frozenset({"expired-token", "invalid-token"})


class TossTokenExpiredError(Exception):
    """토스 액세스 토큰 만료/무효 오류."""


class TossApiError(Exception):
    """토스 API 논리 오류 (error envelope)."""

    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(f"토스 API 오류 [{code}]: {message}")


def _error_envelope(data: dict[str, Any]) -> dict[str, Any] | None:
    err = data.get("error")
    return err if isinstance(err, dict) else None


def _check_toss_token_expired(data: dict[str, Any], status_code: int) -> bool:
    err = _error_envelope(data)
    code = err.get("code") if err else None
    return status_code == 401 or code in _TOKEN_ERROR_CODES


def _check_toss_api_error(data: dict[str, Any], path: str) -> None:
    err = _error_envelope(data)
    if not err:
        return
    code = str(err.get("code") or "unknown")
    msg = str(err.get("message") or "알 수 없는 오류")
    logger.warning("toss_api_error", code=code, msg=msg, path=path, request_id=err.get("requestId"))
    if code in _TOKEN_ERROR_CODES:
        raise TossTokenExpiredError(msg)
    raise TossApiError(code, msg)


async def toss_request(
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    retries: int | None = None,
) -> dict[str, Any]:
    """토스 Open API 기본 HTTP 클라이언트. 성공 시 `{"result": ...}` dict를 그대로 반환한다."""
    await _rate_limiter.acquire()  # broker_request 밖에서 호출 — 세마포어 취득 전 간격 보장
    return await broker_request(
        method,
        path,
        base_url=TOSS_BASE_URL,
        headers=headers,
        params=params,
        json=json,
        retries=retries if retries is not None else settings.toss_default_retries,
        ssl_verify=True,
        semaphore=_semaphore,
        log_prefix="toss",
        check_token_expired=_check_toss_token_expired,
        check_api_error=_check_toss_api_error,
        token_expired_exc=TossTokenExpiredError,
    )
