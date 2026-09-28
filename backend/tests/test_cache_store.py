"""CacheStore.sweep_expired() + cache_sweep job 테스트."""

from unittest.mock import AsyncMock, MagicMock, patch

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
        assert store.take_lru_evictions() == 1
        assert store.take_lru_evictions() == 0

    @pytest.mark.asyncio
    async def test_evicts_expired_entries_before_live_ones(self):
        from app.core import cache_store as cache_store_module

        store = CacheStore()
        with patch.object(cache_store_module, "_MAX_ENTRIES", 3):
            await store.set("lock", "1", nx=True, ex=3600)  # 가장 오래됐지만 살아 있는 항목
            await store.set("stale", "2", ex=-1)
            await store.set("c", "3")
            await store.set("d", "4")  # 상한 초과 → 만료된 "stale"만 치우고 LRU 축출 없음

        assert await store.get("lock") == "1"
        assert await store.get("d") == "4"
        assert len(store) == 3
        assert store.take_lru_evictions() == 0


class TestRunCacheSweep:
    @pytest.mark.asyncio
    async def test_calls_sweep_expired_on_shared_store(self):
        from app.jobs.cache_sweep import run_cache_sweep

        mock_store = AsyncMock()
        mock_store.sweep_expired = AsyncMock(return_value=3)
        mock_store.take_lru_evictions = MagicMock(return_value=0)

        with patch("app.jobs.cache_sweep.get_cache_store", AsyncMock(return_value=mock_store)):
            await run_cache_sweep()

        mock_store.sweep_expired.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_warns_when_live_entries_were_evicted(self):
        from app.jobs.cache_sweep import run_cache_sweep

        store = CacheStore()
        store._lru_evictions = 5
        with (
            patch("app.jobs.cache_sweep.get_cache_store", AsyncMock(return_value=store)),
            patch("app.jobs.cache_sweep.logger") as logger,
        ):
            await run_cache_sweep()
            await run_cache_sweep()  # 카운터가 리셋돼 두 번째 실행은 경고하지 않는다

        logger.warning.assert_called_once_with("cache_lru_evictions", evicted=5, entries=0)
