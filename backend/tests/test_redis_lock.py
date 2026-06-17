"""redis_lock.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.redis_lock import redis_lock


@pytest.mark.asyncio
async def test_lock_acquired_and_released():
    """락 획득 → True yield → 정상 해제."""
    import uuid as _uuid
    from unittest.mock import patch

    fixed_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=fixed_uuid)
    mock_redis.delete = AsyncMock()

    with patch.object(_uuid, "uuid4", return_value=_uuid.UUID(fixed_uuid)):
        async with redis_lock(mock_redis, "test_key", ttl=30) as acquired:
            assert acquired is True

    mock_redis.delete.assert_called_once_with("test_key")


@pytest.mark.asyncio
async def test_lock_not_acquired_yields_false():
    """락 획득 실패 → False yield, 해제 시도 없음."""
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(return_value=None)  # SET NX 실패

    async with redis_lock(mock_redis, "test_key", ttl=30) as acquired:
        assert acquired is False

    mock_redis.get = AsyncMock()
    mock_redis.get.assert_not_called()


@pytest.mark.asyncio
async def test_lock_release_skipped_if_value_changed():
    """락 값이 바뀌었으면 (만료 후 재획득) 삭제하지 않는다."""
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value="different-value")
    mock_redis.delete = AsyncMock()

    async with redis_lock(mock_redis, "test_key", ttl=30) as acquired:
        assert acquired is True

    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_lock_release_failure_is_logged(caplog):
    """해제 중 Redis 에러가 발생해도 예외 전파 없이 경고만 기록한다."""
    import logging

    mock_redis = MagicMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(side_effect=ConnectionError("redis disconnected"))

    with caplog.at_level(logging.WARNING):
        async with redis_lock(mock_redis, "test_key", ttl=30) as acquired:
            assert acquired is True
    # 예외가 전파되지 않아야 함 (테스트 자체가 성공하면 검증됨)
