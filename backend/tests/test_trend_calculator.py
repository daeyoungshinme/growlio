"""trend_calculator.py 단위 테스트."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.trend_calculator import get_monthly_trend


class TestGetMonthlyTrend:
    @pytest.mark.asyncio
    async def test_returns_cached_data_when_redis_hit(self):
        user_id = uuid.uuid4()
        cached = [{"month": "2024-01-01", "total_krw": 1000000.0}]
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())
        db = AsyncMock()

        result = await get_monthly_trend(user_id, db, redis)

        assert result == cached
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_queries_db_when_redis_miss(self):
        user_id = uuid.uuid4()
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()

        row1 = MagicMock()
        row1.month = "2024-01-01"
        row1.total_krw = 2000000.0

        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([row1]))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        result = await get_monthly_trend(user_id, db, redis)

        assert len(result) == 1
        assert result[0]["month"] == "2024-01-01"
        assert result[0]["total_krw"] == pytest.approx(2000000.0)

    @pytest.mark.asyncio
    async def test_works_without_redis(self):
        user_id = uuid.uuid4()
        row = MagicMock()
        row.month = "2024-02-01"
        row.total_krw = 500000.0

        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([row]))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        result = await get_monthly_trend(user_id, db, None)

        assert len(result) == 1
        assert result[0]["total_krw"] == pytest.approx(500000.0)

    @pytest.mark.asyncio
    async def test_empty_result_when_no_snapshots(self):
        user_id = uuid.uuid4()
        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([]))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        result = await get_monthly_trend(user_id, db, None)
        assert result == []

    @pytest.mark.asyncio
    async def test_redis_error_falls_through_to_db(self):
        from redis.exceptions import RedisError

        user_id = uuid.uuid4()
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=RedisError("conn refused"))
        redis.set = AsyncMock()

        row = MagicMock()
        row.month = "2024-03-01"
        row.total_krw = 750000.0

        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([row]))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        result = await get_monthly_trend(user_id, db, redis)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_result_cached_after_db_query(self):
        user_id = uuid.uuid4()
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([]))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        await get_monthly_trend(user_id, db, redis)

        redis.setex.assert_called_once()
