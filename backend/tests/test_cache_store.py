"""CacheStore.sweep_expired() + cache_sweep job 테스트."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.cache_store import CacheStore


class TestSweepExpired:
    @pytest.mark.asyncio
    async def test_removes_only_expired_keys(self):
        store = CacheStore()
        await store.set("expired", "v1", ex=-1)  # 이미 만료된 상태로 저장
        await store.set("fresh", "v2", ex=3600)
        await store.set("no_ttl", "v3")

        removed = await store.sweep_expired()

        assert removed == 1
        assert await store.get("expired") is None
        assert await store.get("fresh") == "v2"
        assert await store.get("no_ttl") == "v3"

    @pytest.mark.asyncio
    async def test_no_expired_keys_returns_zero(self):
        store = CacheStore()
        await store.set("fresh", "v", ex=3600)

        removed = await store.sweep_expired()

        assert removed == 0


class TestMaxEntriesEviction:
    @pytest.mark.asyncio
    async def test_evicts_least_recently_used_when_over_cap(self):
        from app.core import cache_store as cache_store_module

        store = CacheStore()
        with patch.object(cache_store_module, "_MAX_ENTRIES", 3):
            await store.set("a", "1")
            await store.set("b", "2")
            await store.set("c", "3")
            await store.get("a")  # "a"를 최근 사용으로 승격 → 다음 evict 대상은 "b"
            await store.set("d", "4")  # 상한(3) 초과 → 가장 오래 안 쓰인 "b" 제거

        assert await store.get("b") is None
        assert await store.get("a") == "1"
        assert await store.get("c") == "3"
        assert await store.get("d") == "4"


class TestRunCacheSweep:
    @pytest.mark.asyncio
    async def test_calls_sweep_expired_on_shared_store(self):
        from app.jobs.cache_sweep import run_cache_sweep

        mock_store = AsyncMock()
        mock_store.sweep_expired = AsyncMock(return_value=3)

        with patch("app.jobs.cache_sweep.get_cache_store", AsyncMock(return_value=mock_store)):
            await run_cache_sweep()

        mock_store.sweep_expired.assert_awaited_once()
