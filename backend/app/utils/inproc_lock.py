"""프로세스 내 락 — 동일 계좌 동시 sync 방지, 콜드 캐시 single-flight 중복 조회 방지.

배포가 단일 프로세스라 진짜 분산 락은 필요 없다. `CacheStore.set(nx=True, ex=...)`로
동일한 SET NX EX 시맨틱을 유지해 락 로직 자체는 그대로 재사용한다.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore

logger = structlog.get_logger()


@asynccontextmanager
async def inproc_lock(
    cache: CacheStore,
    key: str,
    ttl: int = 60,
) -> AsyncGenerator[bool, None]:
    """SET NX EX 기반 락 컨텍스트 매니저.

    락 획득 성공 시 True를 yield, 실패 시 False를 yield.
    컨텍스트 종료 시 자신이 발급한 락만 삭제한다.
    """
    lock_value = str(uuid.uuid4())
    acquired = await cache.set(key, lock_value, nx=True, ex=ttl)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            try:
                current = await cache.get(key)
                if current == lock_value:
                    await cache.delete(key)
                    logger.debug("inproc_lock_released", key=key)
            except Exception as e:
                logger.warning("inproc_lock_release_failed", key=key, error=str(e))


async def single_flight_fetch(
    cache: CacheStore,
    cache_key: str,
    get_cached: Callable[[], Awaitable[Any | None]],
    fetch_and_cache: Callable[[], Awaitable[Any]],
    lock_ttl: int = 15,
    wait_interval: float = 0.2,
    max_wait_iterations: int = 10,
) -> Any:
    """캐시 미스 시 동시 요청 중 하나만 실제 조회를 수행하고 나머지는 그 결과를 기다린다.

    콜드 캐시(TTL 만료·재배포·신규 유저) 상황에서 여러 요청이 동시에 미스를 겪으면
    각자 외부 API를 중복 호출(fan-out)하게 되는 문제를 막기 위한 락. 락 획득 실패 시
    잠깐 대기하며 캐시가 채워지길 기다리되, 락 보유자가 실패/지연되는 경우를 대비해
    일정 횟수 후에는 직접 조회해 응답이 무한정 지연되지 않도록 한다.
    """
    async with inproc_lock(cache, f"lock:{cache_key}", ttl=lock_ttl) as acquired:
        if acquired:
            return await fetch_and_cache()

        for _ in range(max_wait_iterations):
            await asyncio.sleep(wait_interval)
            cached = await get_cached()
            if cached is not None:
                return cached

        logger.warning("single_flight_wait_timeout_fallback", cache_key=cache_key)
        return await fetch_and_cache()
