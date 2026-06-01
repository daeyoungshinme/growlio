import asyncio
from typing import Any

import structlog

from app.kis.constants import KIS_MOCK_BASE_URL, KIS_REAL_BASE_URL
from app.providers.http_client import broker_request

logger = structlog.get_logger()

_semaphore = asyncio.Semaphore(5)


class KisTokenExpiredError(Exception):
    """KIS 토큰 만료 오류 (EGW00123)."""


class KisApiError(Exception):
    """KIS API 논리 오류 (rt_cd != "0")."""

    def __init__(self, rt_cd: str, msg: str) -> None:
        self.rt_cd = rt_cd
        self.msg = msg
        super().__init__(f"KIS API 오류 [{rt_cd}]: {msg}")


def _check_kis_token_expired(data: dict[str, Any], status_code: int) -> bool:
    return data.get("msg_cd") == "EGW00123"


def _check_kis_api_error(data: dict[str, Any], path: str) -> None:
    if data.get("rt_cd") not in ("0", None):
        rt_cd = data.get("rt_cd", "?")
        msg = data.get("msg1", "알 수 없는 오류")
        logger.warning("kis_api_error", rt_cd=rt_cd, msg=msg, path=path)
        raise KisApiError(rt_cd, msg)


async def kis_request(
    method: str,
    path: str,
    *,
    is_mock: bool,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    retries: int = 3,
) -> dict[str, Any]:
    """KIS OpenAPI 기본 HTTP 클라이언트 — 속도제한 + 재시도 포함."""
    return await broker_request(
        method,
        path,
        base_url=KIS_MOCK_BASE_URL if is_mock else KIS_REAL_BASE_URL,
        headers=headers,
        params=params,
        json=json,
        retries=retries,
        ssl_verify=not is_mock,
        semaphore=_semaphore,
        log_prefix="kis",
        check_token_expired=_check_kis_token_expired,
        check_api_error=_check_kis_api_error,
        token_expired_exc=KisTokenExpiredError,
    )
