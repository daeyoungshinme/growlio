"""KIS/Kiwoom 공유 HTTP 클라이언트 — 속도제한·재시도 로직 추출."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_DEFAULT_SEMAPHORE_LIMIT = 5


async def broker_request(
    method: str,
    path: str,
    *,
    base_url: str,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    retries: int = 3,
    ssl_verify: bool = True,
    semaphore: asyncio.Semaphore,
    log_prefix: str,
    check_token_expired: Callable[[dict[str, Any], int], bool],
    check_api_error: Callable[[dict[str, Any], str], None],
    token_expired_exc: type[Exception],
) -> dict[str, Any]:
    """KIS/Kiwoom 공통 HTTP 요청 함수 — 속도제한(429) 지수 백오프 + 재시도 포함.

    Args:
        check_token_expired: (data, status_code) → bool. 토큰 만료 여부 반환.
        check_api_error: (data, path) → None. API 오류 시 예외 발생.
        token_expired_exc: 토큰 만료 시 발생할 예외 클래스.
    """
    async with semaphore, httpx.AsyncClient(timeout=30.0, verify=ssl_verify) as client:
        for attempt in range(retries):
            try:
                response = await client.request(
                    method,
                    f"{base_url}{path}",
                    headers=headers,
                    params=params,
                    json=json,
                )
                if response.status_code >= 400:
                    try:
                        error_body = response.json()
                        logger.error(
                            f"{log_prefix}_http_error",
                            status=response.status_code,
                            body=error_body,
                            path=path,
                        )
                        if check_token_expired(error_body, response.status_code):
                            raise token_expired_exc()
                    except token_expired_exc:
                        raise
                    except Exception:
                        logger.error(
                            f"{log_prefix}_http_error",
                            status=response.status_code,
                            body=response.text,
                            path=path,
                        )
                    response.raise_for_status()
                data = response.json()
                check_api_error(data, path)
                await asyncio.sleep(0.05)
                return data

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"{log_prefix}_rate_limit", attempt=attempt, wait=wait)
                    await asyncio.sleep(wait)
                elif 400 <= e.response.status_code < 500:
                    raise
                elif attempt < retries - 1:
                    await asyncio.sleep(1)
                else:
                    raise
            except httpx.RequestError as e:
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError(f"{log_prefix} API 요청 실패: {e}") from e

    raise RuntimeError(f"{log_prefix} API 최대 재시도 초과")
