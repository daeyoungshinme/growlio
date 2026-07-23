"""키움증권 REST API 기본 HTTP 클라이언트 — 속도제한 + 재시도 포함."""

import asyncio
from typing import Any

import structlog

from app.core.config import settings
from app.kiwoom.constants import KIWOOM_MOCK_BASE_URL, KIWOOM_REAL_BASE_URL
from app.providers.http_client import AsyncRateLimiter, broker_request

logger = structlog.get_logger()

_semaphore = asyncio.Semaphore(settings.kiwoom_semaphore_limit)
_rate_limiter = AsyncRateLimiter(rate=settings.kiwoom_rate_per_second)


class KiwoomTokenExpiredError(Exception):
    """키움 토큰 만료 오류."""


class KiwoomApiError(Exception):
    """키움 API 논리 오류 (return_code != "0")."""

    def __init__(self, return_code: str, msg: str) -> None:
        self.return_code = return_code
        self.msg = msg
        super().__init__(f"키움 API 오류 [{return_code}]: {msg}")


def _check_kiwoom_token_expired(data: dict[str, Any], status_code: int) -> bool:
    return status_code == 401


def _is_token_invalid_error(return_code: str, msg: str) -> bool:
    """키움은 토큰 무효를 HTTP 401이 아닌 200 + return_code=3 + 메시지 내 8005 서브코드로 응답한다."""
    return return_code == "3" and "8005" in msg


def _check_kiwoom_api_error(data: dict[str, Any], path: str, *, quiet: bool = False) -> None:
    return_code = data.get("return_code")
    if return_code is not None and str(return_code) != "0":
        msg = data.get("return_msg", "알 수 없는 오류")
        log = logger.debug if quiet else logger.warning
        log("kiwoom_api_error", return_code=return_code, msg=msg, path=path)
        if _is_token_invalid_error(str(return_code), msg):
            raise KiwoomTokenExpiredError(msg)
        raise KiwoomApiError(str(return_code), msg)


async def kiwoom_request(
    method: str,
    path: str,
    *,
    is_mock: bool,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    retries: int | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """키움 OpenAPI+ 기본 HTTP 클라이언트.

    quiet=True면 API 논리 오류(return_code != "0")를 WARNING 대신 DEBUG로 로깅한다 —
    호출부가 실패를 정상 제어 흐름으로 취급하는 경우(예: 거래소구분 프로빙) 사용.
    """
    await _rate_limiter.acquire()  # broker_request 밖에서 호출 — 세마포어 취득 전 간격 보장
    return await broker_request(
        method,
        path,
        base_url=KIWOOM_MOCK_BASE_URL if is_mock else KIWOOM_REAL_BASE_URL,
        headers=headers,
        params=params,
        json=json,
        retries=retries if retries is not None else settings.kiwoom_default_retries,
        ssl_verify=True,
        semaphore=_semaphore,
        log_prefix="kiwoom",
        check_token_expired=_check_kiwoom_token_expired,
        check_api_error=lambda data, path: _check_kiwoom_api_error(data, path, quiet=quiet),
        token_expired_exc=KiwoomTokenExpiredError,
    )
