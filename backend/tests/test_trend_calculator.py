"""trend_calculator.py 단위 테스트."""

from __future__ import annotations

import json
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.trend_calculator import _trend_window_start, get_monthly_trend


class TestGetMonthlyTrend:
    @pytest.mark.asyncio
    async def test_returns_cached_data_when_cache_hit(self):
        user_id = uuid.uuid4()
        cached = [{"month": "2024-01-01", "total_krw": 1000000.0}]
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps(cached).encode())
        db = AsyncMock()

        result = await get_monthly_trend(user_id, db, cache)

        assert result == cached
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_queries_db_when_cache_miss(self):
        user_id = uuid.uuid4()
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()

        row1 = MagicMock()
        row1.month = "2024-01-01"
        row1.total_krw = 2000000.0

        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([row1]))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        result = await get_monthly_trend(user_id, db, cache)

        assert len(result) == 1
        assert result[0]["month"] == "2024-01-01"
        assert result[0]["total_krw"] == pytest.approx(2000000.0)

    @pytest.mark.asyncio
    async def test_works_without_cache(self):
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
    async def test_result_cached_after_db_query(self):
        user_id = uuid.uuid4()
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.setex = AsyncMock()

        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([]))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        await get_monthly_trend(user_id, db, cache)

        cache.setex.assert_called_once()


class TestTrendWindowStart:
    """12개월 창 시작일은 KST 오늘 기준(DB UTC CURRENT_DATE 아님, 계획 59 A4)."""

    @pytest.mark.parametrize(
        ("today", "expected"),
        [
            (date(2026, 10, 1), date(2025, 11, 1)),
            (date(2026, 12, 31), date(2026, 1, 1)),
            (date(2026, 11, 15), date(2025, 12, 1)),
            (date(2026, 1, 1), date(2025, 2, 1)),
        ],
    )
    def test_window_start(self, today, expected):
        assert _trend_window_start(today) == expected

    @pytest.mark.asyncio
    async def test_query_binds_kst_start_date(self, monkeypatch):
        from app.services import trend_calculator as tc

        monkeypatch.setattr(tc, "today_kst", lambda: date(2026, 11, 1))
        execute_result = MagicMock()
        execute_result.__iter__ = MagicMock(return_value=iter([]))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=execute_result)

        await tc.get_monthly_trend(uuid.uuid4(), db, None)

        sql, params = db.execute.call_args.args
        assert "CURRENT_DATE" not in str(sql)
        assert params["start_date"] == date(2025, 12, 1)
