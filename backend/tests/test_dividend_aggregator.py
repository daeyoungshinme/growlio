"""dividend_aggregator.py 단위 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetDividendSummary:
    @pytest.mark.asyncio
    async def test_cache_cache_hit(self, mock_db, override_settings):
        import json

        from app.services.dividend.aggregator import get_dividend_summary

        cached = {
            "annual_received": 500_000.0,
            "monthly_breakdown": [],
            "monthly_ticker_breakdown": [],
            "estimated_annual": 600_000.0,
        }
        cache = AsyncMock()
        cache.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await get_dividend_summary(uuid.uuid4(), mock_db, cache=cache)

        assert result["annual_received"] == 500_000.0
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_summary_with_db_data(self, mock_db, override_settings):
        from app.services.dividend.aggregator import get_dividend_summary

        # Mock _fetch_dividend_aggregates to return rows
        row_annual = SimpleNamespace(kind="annual", month=None, ticker=None, total=300_000.0)
        row_monthly = SimpleNamespace(kind="monthly", month="2024-01", ticker=None, total=100_000.0)
        row_ticker = SimpleNamespace(kind="monthly_ticker", month="2024-01", ticker="AAPL", total=100_000.0)

        exec_result = MagicMock()
        exec_result.all.return_value = [row_annual, row_monthly, row_ticker]
        mock_db.execute = AsyncMock(return_value=exec_result)

        with patch("app.services.dividend.aggregator.get_ticker_dividend_summary", new=AsyncMock(return_value=[])):
            result = await get_dividend_summary(uuid.uuid4(), mock_db)

        assert result["annual_received"] == 300_000.0
        assert len(result["monthly_breakdown"]) == 1
        assert len(result["monthly_ticker_breakdown"]) == 1

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result(self, mock_db, override_settings):
        from app.services.dividend.aggregator import get_dividend_summary

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        cache = AsyncMock()
        cache.get = AsyncMock(return_value=None)
        cache.setex = AsyncMock()

        with patch("app.services.dividend.aggregator.get_ticker_dividend_summary", new=AsyncMock(return_value=[])):
            await get_dividend_summary(uuid.uuid4(), mock_db, cache=cache)

        cache.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_rows_returns_zeros(self, mock_db, override_settings):
        from app.services.dividend.aggregator import get_dividend_summary

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        with patch("app.services.dividend.aggregator.get_ticker_dividend_summary", new=AsyncMock(return_value=[])):
            result = await get_dividend_summary(uuid.uuid4(), mock_db)

        assert result["annual_received"] == 0.0
        assert result["monthly_breakdown"] == []
        assert result["estimated_annual"] == 0.0
