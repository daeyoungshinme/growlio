"""KIS/Kiwoom 공유 HTTP 클라이언트 — 속도제한·재시도 로직 추출."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_DEFAULT_SEMAPHORE_LIMIT = 5

_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_ssl_client: httpx.AsyncClient | None = None
_nossl_client: httpx.AsyncClient | None = None


def _get_client(ssl_verify: bool) -> httpx.AsyncClient:
    global _ssl_client, _nossl_client
    if ssl_verify:
        if _ssl_client is None:
            _ssl_client = httpx.AsyncClient(timeout=30.0, verify=True, limits=_LIMITS)
        return _ssl_client
    else:
        if _nossl_client is None:
            _nossl_client = httpx.AsyncClient(timeout=30.0, verify=False, limits=_LIMITS)  # nosec B501 — 특정 증권사 API SSL 미지원
        return _nossl_client


async def close_http_client() -> None:
    """앱 종료 시 싱글턴 HTTP 클라이언트를 닫는다."""
    global _ssl_client, _nossl_client
    if _ssl_client is not None:
        await _ssl_client.aclose()
        _ssl_client = None
    if _nossl_client is not None:
        await _nossl_client.aclose()
        _nossl_client = None


class MaxRetriesExceededError(RuntimeError):
    """broker_request 모든 재시도 소진 시 발생."""


class AsyncRateLimiter:
    """토큰 버킷 방식 비동기 레이트 리미터 — 요청 시작 사이 최소 interval 보장."""

    def __init__(self, rate: float) -> None:
        self._interval = 1.0 / rate
        self._next_allowed: float = 0.0
        self._lock: asyncio.Lock | None = None  # 이벤트 루프 내 지연 초기화

    def _get_lock(self) -> asyncio.Lock:
        # asyncio 단일 스레드 → 경합 없이 안전한 지연 초기화
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def acquire(self) -> None:
        loop = asyncio.get_running_loop()  # get_event_loop() deprecated 대체
        async with self._get_lock():
            now = loop.time()
            wait = self._next_allowed - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_allowed = loop.time() + self._interval


def _is_rate_limit_body(response: httpx.Response) -> bool:
    """KIS EGW00201 (초당 거래건수 초과) 응답 감지."""
    try:
        return response.json().get("msg_cd") == "EGW00201"
    except Exception:
        return False


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
    post_request_delay: float = 0.05,
) -> dict[str, Any]:
    """KIS/Kiwoom 공통 HTTP 요청 함수 — 속도제한(429) 지수 백오프 + 재시도 포함.

    Args:
        check_token_expired: (data, status_code) → bool. 토큰 만료 여부 반환.
        check_api_error: (data, path) → None. API 오류 시 예외 발생.
        token_expired_exc: 토큰 만료 시 발생할 예외 클래스.
    """
    client = _get_client(ssl_verify)
    async with semaphore:
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
                        if _is_rate_limit_body(response):
                            # EGW00201 — 재시도 가능한 rate limit, WARNING으로 처리
                            logger.warning(
                                f"{log_prefix}_rate_limit_response",
                                status=response.status_code,
                                path=path,
                            )
                        else:
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
                await asyncio.sleep(post_request_delay)
                return data

            except httpx.HTTPStatusError as e:
                is_api_rate_limit = _is_rate_limit_body(e.response)
                if e.response.status_code == 429 or is_api_rate_limit:
                    if attempt >= retries - 1:
                        raise MaxRetriesExceededError(f"{log_prefix} API 속도 제한 초과 (재시도 {retries}회)") from e
                    # 기저 2s 추가 — KIS rate limit 윈도우 확실히 벗어나도록
                    wait = 2.0 + (2**attempt) + (random.uniform(0, 1) if is_api_rate_limit else 0)  # nosec B311 — jitter용, 보안 목적 아님
                    label = "api_rate_limit" if is_api_rate_limit else "rate_limit"
                    logger.warning(f"{log_prefix}_{label}", attempt=attempt, wait=round(wait, 2), path=path)
                    await asyncio.sleep(wait)
                elif 400 <= e.response.status_code < 500:
                    raise
                elif attempt < retries - 1:
                    await asyncio.sleep(1 + random.uniform(0, 0.5))  # nosec B311 — jitter용, 보안 목적 아님
                else:
                    raise
            except httpx.RequestError as e:
                if attempt < retries - 1:
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError(f"{log_prefix} API 요청 실패: {e}") from e

    raise MaxRetriesExceededError(f"{log_prefix} API 최대 재시도 초과")
