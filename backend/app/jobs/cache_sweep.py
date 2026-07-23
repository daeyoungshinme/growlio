"""in-memory 캐시(`cache_store.py`) 만료 키 능동 청소 Job.

lazy expiration만으로는 재방문하지 않는 유저의 캐시 엔트리가 TTL이 지나도 계속 dict에 남아
메모리와 `scan()` 풀스캔 비용을 함께 키운다 — 15분 간격으로 만료된 키를 능동적으로 제거한다.
"""

from __future__ import annotations

import structlog

from app.core.cache_store import get_cache_store

logger = structlog.get_logger()


async def run_cache_sweep() -> None:
    """만료된 in-memory 캐시 키를 청소한다."""
    store = await get_cache_store()
    removed = await store.sweep_expired()
    if removed:
        logger.info("cache_sweep_done", removed=removed)
