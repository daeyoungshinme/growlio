"""portfolio_history_service.py 단위 테스트 — get_allocation_history."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestGetAllocationHistory:
    @pytest.mark.asyncio
    async def test_cache_cache_hit_skips_db(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        cached = [{"month": "2024-01-01", "total_krw": 10_000_000, "allocations": []}]
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await get_allocation_history(uuid.uuid4(), mock_db, cache=cache)

        assert result == cached
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await get_allocation_history(uuid.uuid4(), mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_aggregates_monthly_data(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        row1 = SimpleNamespace(month="2024-01-01", asset_type="STOCK_KIS", amount_krw=5_000_000.0)
        row2 = SimpleNamespace(month="2024-01-01", asset_type="BANK_ACCOUNT", amount_krw=3_000_000.0)
        row3 = SimpleNamespace(month="2024-02-01", asset_type="STOCK_KIS", amount_krw=6_000_000.0)

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [row1, row2, row3]
            else:
                result.all.return_value = []
            return result

        mock_db.execute = mock_execute

        result = await get_allocation_history(uuid.uuid4(), mock_db, months=3)

        # Should have 2 months
        assert len(result) == 2
        jan = next(r for r in result if "2024-01" in r["month"])
        assert jan["total_krw"] == pytest.approx(8_000_000.0)

    @pytest.mark.asyncio
    async def test_position_data_overrides_stock_types(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        row1 = SimpleNamespace(month="2024-01-01", asset_type="STOCK_KIS", amount_krw=5_000_000.0)

        pos_row = SimpleNamespace(month="2024-01-01", asset_type="STOCK_DOMESTIC", amount_krw=3_000_000.0)

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [row1]
            else:
                result.all.return_value = [pos_row]
            return result

        mock_db.execute = mock_execute

        result = await get_allocation_history(uuid.uuid4(), mock_db, months=3)

        assert len(result) == 1
        alloc_types = [a["asset_type"] for a in result[0]["allocations"]]
        assert "STOCK_DOMESTIC" in alloc_types
        # STOCK_KIS should be replaced by STOCK_DOMESTIC
        assert "STOCK_KIS" not in alloc_types

    @pytest.mark.asyncio
    async def test_result_stored_in_cache(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        row1 = SimpleNamespace(month="2024-01-01", asset_type="BANK_ACCOUNT", amount_krw=1_000_000.0)

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [row1]
            else:
                result.all.return_value = []
            return result

        mock_db.execute = mock_execute

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.setex = AsyncMock()

        await get_allocation_history(uuid.uuid4(), mock_db, cache=cache, months=3)

        cache.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_account_id_passed_as_query_param(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        captured_params = []

        async def mock_execute(query, params=None):
            captured_params.append(params)
            result = MagicMock()
            result.all.return_value = []
            return result

        mock_db.execute = mock_execute
        account_id = uuid.uuid4()

        await get_allocation_history(uuid.uuid4(), mock_db, months=3, account_id=account_id)

        assert len(captured_params) == 2  # asset_type 쿼리 + market breakdown 쿼리
        assert all(p["account_id"] == str(account_id) for p in captured_params)

    @pytest.mark.asyncio
    async def test_no_account_id_passes_none(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        captured_params = []

        async def mock_execute(query, params=None):
            captured_params.append(params)
            result = MagicMock()
            result.all.return_value = []
            return result

        mock_db.execute = mock_execute

        await get_allocation_history(uuid.uuid4(), mock_db, months=3)

        assert all(p["account_id"] is None for p in captured_params)

    @pytest.mark.asyncio
    async def test_account_id_uses_separate_cache_key(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.setex = AsyncMock()

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        user_id = uuid.uuid4()
        account_id = uuid.uuid4()
        await get_allocation_history(user_id, mock_db, cache=cache, months=3, account_id=account_id)
        await get_allocation_history(user_id, mock_db, cache=cache, months=3)

        keys_used = [call.args[0] for call in cache.get.call_args_list]
        assert len(set(keys_used)) == 2

    @pytest.mark.asyncio
    async def test_zero_total_months_excluded(self, mock_db, override_settings):
        from app.services.portfolio_history_service import get_allocation_history

        # A month with 0 total should be excluded
        row1 = SimpleNamespace(month="2024-01-01", asset_type="BANK_ACCOUNT", amount_krw=0.0)

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [row1]
            else:
                result.all.return_value = []
            return result

        mock_db.execute = mock_execute

        result = await get_allocation_history(uuid.uuid4(), mock_db, months=3)
        assert result == []
