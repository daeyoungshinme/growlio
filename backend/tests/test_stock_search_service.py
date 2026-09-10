"""services/stock_search_service.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.stock_search_service import resolve_ticker_meta


class TestResolveTickerMeta:
    @pytest.mark.asyncio
    async def test_returns_name_and_market_on_exact_match(self):
        with patch(
            "app.services.stock_search_service._search_yahoo",
            new=AsyncMock(return_value=[{"ticker": "SPY", "name": "SPDR S&P 500 ETF Trust", "market": "NYSE"}]),
        ):
            name, market = await resolve_ticker_meta("spy")

        assert name == "SPDR S&P 500 ETF Trust"
        assert market == "NYSE"

    @pytest.mark.asyncio
    async def test_returns_none_pair_when_no_exact_match(self):
        with patch("app.services.stock_search_service._search_yahoo", new=AsyncMock(return_value=[])):
            assert await resolve_ticker_meta("SPY") == (None, None)
