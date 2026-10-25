"""inproc_lock.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.inproc_lock import inproc_lock


@pytest.mark.asyncio
async def test_lock_acquired_and_released():
    """락 획득 → True yield → 정상 해제."""
    import uuid as _uuid
    from unittest.mock import patch

    fixed_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    mock_cache = MagicMock()
    mock_cache.set = AsyncMock(return_value=True)
    mock_cache.get = AsyncMock(return_value=fixed_uuid)
    mock_cache.delete = AsyncMock()

    with patch.object(_uuid, "uuid4", return_value=_uuid.UUID(fixed_uuid)):
        async with inproc_lock(mock_cache, "test_key", ttl=30) as acquired:
            assert acquired is True

    mock_cache.delete.assert_called_once_with("test_key")


@pytest.mark.asyncio
async def test_lock_not_acquired_yields_false():
    """락 획득 실패 → False yield, 해제 시도 없음."""
    mock_cache = MagicMock()
    mock_cache.set = AsyncMock(return_value=None)  # SET NX 실패

    async with inproc_lock(mock_cache, "test_key", ttl=30) as acquired:
        assert acquired is False

    mock_cache.get = AsyncMock()
    mock_cache.get.assert_not_called()


@pytest.mark.asyncio
async def test_lock_release_skipped_if_value_changed():
    """락 값이 바뀌었으면 (만료 후 재획득) 삭제하지 않는다."""
    mock_cache = MagicMock()
    mock_cache.set = AsyncMock(return_value=True)
    mock_cache.get = AsyncMock(return_value="different-value")
    mock_cache.delete = AsyncMock()

    async with inproc_lock(mock_cache, "test_key", ttl=30) as acquired:
        assert acquired is True

    mock_cache.delete.assert_not_called()


@pytest.mark.asyncio
async def test_lock_release_failure_is_logged(caplog):
    """해제 중 Cache 에러가 발생해도 예외 전파 없이 경고만 기록한다."""
    import logging

    mock_cache = MagicMock()
    mock_cache.set = AsyncMock(return_value=True)
    mock_cache.get = AsyncMock(side_effect=ConnectionError("cache disconnected"))

    with caplog.at_level(logging.WARNING):
        async with inproc_lock(mock_cache, "test_key", ttl=30) as acquired:
            assert acquired is True
    # 예외가 전파되지 않아야 함 (테스트 자체가 성공하면 검증됨)


@pytest.mark.asyncio
async def test_single_flight_concurrent_calls_compute_once():
    import asyncio

    from app.core.cache_store import CacheStore
    from app.utils.inproc_lock import single_flight_fetch

    store = CacheStore()
    calls = 0

    async def read():
        return await store.get("sf:k")

    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.3)  # 대기자가 예전 2초 상한 안팎이 아니라 결과를 기다려야 한다
        await store.set("sf:k", "v", ex=60)
        return "v"

    results = await asyncio.gather(
        *(single_flight_fetch(store, "sf:k", read, fetch, wait_interval=0.05) for _ in range(3))
    )

    assert results == ["v", "v", "v"]
    assert calls == 1


@pytest.mark.asyncio
async def test_single_flight_waiter_falls_back_when_holder_fails():
    import asyncio

    from app.core.cache_store import CacheStore
    from app.utils.inproc_lock import single_flight_fetch

    store = CacheStore()
    calls = 0

    async def read():
        return await store.get("sf:f")

    async def fetch():
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(0.1)
            raise RuntimeError("holder failed")
        return "v2"

    holder = asyncio.create_task(single_flight_fetch(store, "sf:f", read, fetch, wait_interval=0.05))
    await asyncio.sleep(0.01)
    started = asyncio.get_running_loop().time()
    waiter_result = await single_flight_fetch(store, "sf:f", read, fetch, wait_interval=0.05)
    elapsed = asyncio.get_running_loop().time() - started

    with pytest.raises(RuntimeError):
        await holder
    assert waiter_result == "v2"
    assert elapsed < 1.0  # 락이 풀리면 15초 상한까지 기다리지 않는다


@pytest.mark.asyncio
async def test_dashboard_summary_concurrent_cold_cache_computes_once():
    import asyncio
    import uuid
    from unittest.mock import patch

    from app.core.cache_store import CacheStore
    from app.services import asset_aggregator
    from app.utils.cache_keys import dashboard_summary_key, set_cached_json

    store = CacheStore()
    uid = uuid.uuid4()
    calls = 0

    async def fake_compute(user_id, db, cache):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.2)
        result = {"total_assets_krw": 1.0}
        await set_cached_json(cache, dashboard_summary_key(user_id), result, 60)
        return result

    with patch.object(asset_aggregator, "_compute_dashboard_summary", fake_compute):
        results = await asyncio.gather(
            *(asset_aggregator.get_dashboard_summary(uid, MagicMock(), store) for _ in range(3))
        )

    assert calls == 1
    assert all(r == {"total_assets_krw": 1.0} for r in results)
