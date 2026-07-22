"""프로세스 내 in-memory TTL 캐시 store — 구 Redis 클라이언트 대체.

배포가 단일 프로세스(uvicorn --workers 미지정, Render free plan 단일 인스턴스)이므로
프로세스 간 상태 공유가 필요 없다. Redis의 get/set/setex/delete/scan/unlink/ping
최소 인터페이스를 그대로 구현해 호출부(cache_keys.py 등) 로직 변경을 최소화한다.
"""

from __future__ import annotations

import asyncio
import fnmatch
import re
import time


class CacheStore:
    """dict 기반 TTL 캐시. `set(..., nx=True)`는 asyncio.Lock으로 원자성을 보장한다."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, expires_at: float | None) -> bool:
        return expires_at is not None and expires_at <= time.monotonic()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if self._is_expired(expires_at):
                del self._data[key]
                return None
            return value

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        async with self._lock:
            if nx:
                existing = self._data.get(key)
                if existing is not None and not self._is_expired(existing[1]):
                    return False
            expires_at = time.monotonic() + ex if ex is not None else None
            self._data[key] = (value, expires_at)
            return True

    async def setex(self, key: str, ttl: int, value: str) -> None:
        await self.set(key, value, ex=ttl)

    async def mget(self, keys: list[str]) -> list[str | None]:
        async with self._lock:
            result: list[str | None] = []
            for key in keys:
                entry = self._data.get(key)
                if entry is None or self._is_expired(entry[1]):
                    result.append(None)
                else:
                    result.append(entry[0])
            return result

    async def delete(self, *keys: str) -> None:
        async with self._lock:
            for key in keys:
                self._data.pop(key, None)

    async def unlink(self, *keys: str) -> None:
        await self.delete(*keys)

    async def scan(self, cursor: int, match: str, count: int = 100) -> tuple[int, list[str]]:
        """SCAN 흉내 — in-memory라 커서 없이 한 번에 전체 매칭 키를 반환하고 cursor=0을 돌려준다."""
        async with self._lock:
            regex = re.compile(fnmatch.translate(match))
            matched = [
                key
                for key, (_, expires_at) in self._data.items()
                if not self._is_expired(expires_at) and regex.match(key)
            ]
            return 0, matched

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        async with self._lock:
            self._data.clear()


cache_store: CacheStore | None = None


async def get_cache_store() -> CacheStore:
    global cache_store
    if cache_store is None:
        cache_store = CacheStore()
    return cache_store


async def close_cache_store() -> None:
    global cache_store
    if cache_store:
        await cache_store.aclose()
        cache_store = None
