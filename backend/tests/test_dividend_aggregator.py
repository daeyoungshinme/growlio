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


@pytest.mark.asyncio
async def test_aggregates_exclude_soft_deleted_accounts(mock_db, override_settings):
    """plans/95 A4 — 연간·월별 수령 배당이 삭제(soft) 계좌 배당을 빼고 계좌 미지정 배당은 유지."""
    from app.services.dividend.aggregator import _fetch_dividend_aggregates

    exec_result = MagicMock()
    exec_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=exec_result)

    await _fetch_dividend_aggregates(uuid.uuid4(), mock_db, 2026)

    sql = str(mock_db.execute.call_args[0][0])
    assert "LEFT JOIN asset_accounts a ON a.id = t.account_id" in sql
    assert "t.account_id IS NULL OR a.is_active = TRUE" in sql
