"""providers/_overseas_name_enrichment.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.providers._overseas_name_enrichment import enrich_overseas_names
from app.utils.cache_keys import TTL_OVERSEAS_STOCK_NAME, overseas_stock_name_key


def _position(ticker: str, name: str) -> dict:
    return {"ticker": ticker, "name": name, "market": "NASDAQ", "currency": "USD"}


class TestEnrichOverseasNames:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_lookup(self, mock_redis):
        mock_redis.get = AsyncMock(return_value=b"Invesco QQQ Trust, Series 1")

        with patch("app.providers._overseas_name_enrichment.resolve_english_name", new=AsyncMock()) as resolve_mock:
            result = await enrich_overseas_names([_position("QQQ", "QQQ 인베스코 ETF")], mock_redis)

        resolve_mock.assert_not_called()
        assert result[0]["name"] == "Invesco QQQ Trust, Series 1"

    @pytest.mark.asyncio
    async def test_cache_miss_looks_up_and_caches(self, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)

        with patch(
            "app.providers._overseas_name_enrichment.resolve_english_name",
            new=AsyncMock(return_value="Invesco QQQ Trust, Series 1"),
        ):
            result = await enrich_overseas_names([_position("QQQ", "QQQ 인베스코 ETF")], mock_redis)

        assert result[0]["name"] == "Invesco QQQ Trust, Series 1"
        mock_redis.setex.assert_any_call(
            overseas_stock_name_key("QQQ"), TTL_OVERSEAS_STOCK_NAME, "Invesco QQQ Trust, Series 1"
        )

    @pytest.mark.asyncio
    async def test_lookup_failure_falls_back_to_original_name_without_caching(self, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)

        with patch("app.providers._overseas_name_enrichment.resolve_english_name", new=AsyncMock(return_value=None)):
            result = await enrich_overseas_names([_position("XYZ", "브로커원본이름")], mock_redis)

        assert result[0]["name"] == "브로커원본이름"
        mock_redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_tickers_looked_up_once(self, mock_redis):
        mock_redis.get = AsyncMock(return_value=None)

        with patch(
            "app.providers._overseas_name_enrichment.resolve_english_name",
            new=AsyncMock(return_value="Apple Inc."),
        ) as resolve_mock:
            result = await enrich_overseas_names([_position("AAPL", "애플1"), _position("AAPL", "애플2")], mock_redis)

        resolve_mock.assert_called_once_with("AAPL")
        assert [p["name"] for p in result] == ["Apple Inc.", "Apple Inc."]
