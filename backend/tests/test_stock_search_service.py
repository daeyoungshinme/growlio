"""services/stock_search_service.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.stock_search_service import resolve_english_name


class TestResolveEnglishName:
    @pytest.mark.asyncio
    async def test_returns_name_on_exact_ticker_match(self):
        with patch(
            "app.services.stock_search_service._search_yahoo",
            new=AsyncMock(
                return_value=[
                    {"ticker": "QQQ", "name": "Invesco QQQ Trust, Series 1", "market": "NASDAQ"},
                ]
            ),
        ):
            result = await resolve_english_name("qqq")

        assert result == "Invesco QQQ Trust, Series 1"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_exact_match(self):
        with patch(
            "app.services.stock_search_service._search_yahoo",
            new=AsyncMock(return_value=[{"ticker": "QQQM", "name": "Invesco NASDAQ 100 ETF", "market": "NASDAQ"}]),
        ):
            result = await resolve_english_name("QQQ")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_search_fails_empty(self):
        with patch("app.services.stock_search_service._search_yahoo", new=AsyncMock(return_value=[])):
            result = await resolve_english_name("QQQ")

        assert result is None
