"""Redis 분산 락 — 동일 계좌 동시 sync 방지."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog

logger = structlog.get_logger()


@asynccontextmanager
async def redis_lock(
    redis,
    key: str,
    ttl: int = 60,
) -> AsyncGenerator[bool, None]:
    """Redis SET NX EX 기반 분산 락 컨텍스트 매니저.

    락 획득 성공 시 True를 yield, 실패 시 False를 yield.
    컨텍스트 종료 시 자신이 발급한 락만 삭제한다.
    """
    lock_value = str(uuid.uuid4())
    acquired = await redis.set(key, lock_value, nx=True, ex=ttl)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            current = await redis.get(key)
            if current == lock_value:
                await redis.delete(key)
                logger.debug("redis_lock_released", key=key)
