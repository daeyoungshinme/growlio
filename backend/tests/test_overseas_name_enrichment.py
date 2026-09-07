"""providers/_overseas_name_enrichment.py 단위 테스트."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.providers._overseas_name_enrichment import enrich_overseas_positions
from app.utils.cache_keys import TTL_OVERSEAS_STOCK_META, overseas_stock_meta_key


def _position(ticker: str, name: str, market: str = "US") -> dict:
    return {"ticker": ticker, "name": name, "market": market, "currency": "USD"}


def _meta_mock(mapping: dict[str, tuple[str | None, str | None]]):
    async def _resolve(ticker: str):
        return mapping.get(ticker, (None, None))

    return AsyncMock(side_effect=_resolve)


class TestEnrichOverseasPositions:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_lookup(self, mock_cache):
        mock_cache.get = AsyncMock(return_value=json.dumps({"name": "Invesco QQQ Trust", "market": "NASDAQ"}))

        with patch("app.providers._overseas_name_enrichment.resolve_ticker_meta", new=AsyncMock()) as resolve_mock:
            result = await enrich_overseas_positions([_position("QQQ", "QQQ 인베스코 ETF")], mock_cache)

        resolve_mock.assert_not_called()
        assert result[0]["name"] == "Invesco QQQ Trust"
        assert result[0]["market"] == "NASDAQ"

    @pytest.mark.asyncio
    async def test_cache_miss_looks_up_and_caches_name_and_market(self, mock_cache):
        mock_cache.get = AsyncMock(return_value=None)

        with patch(
            "app.providers._overseas_name_enrichment.resolve_ticker_meta",
            new=_meta_mock({"SPY": ("SPDR S&P 500 ETF Trust", "NYSE")}),
        ):
            result = await enrich_overseas_positions([_position("SPY", "SPY SPDR ETF")], mock_cache)

        assert result[0]["name"] == "SPDR S&P 500 ETF Trust"
        assert result[0]["market"] == "NYSE"
        mock_cache.setex.assert_any_call(
            overseas_stock_meta_key("SPY"),
            TTL_OVERSEAS_STOCK_META,
            json.dumps({"name": "SPDR S&P 500 ETF Trust", "market": "NYSE"}, ensure_ascii=False, allow_nan=False),
        )

    @pytest.mark.asyncio
    async def test_lookup_failure_keeps_original_name_and_falls_back_to_nasdaq(self, mock_cache):
        mock_cache.get = AsyncMock(return_value=None)

        with patch(
            "app.providers._overseas_name_enrichment.resolve_ticker_meta",
            new=_meta_mock({}),  # (None, None)
        ):
            result = await enrich_overseas_positions([_position("XYZ", "브로커원본이름")], mock_cache)

        assert result[0]["name"] == "브로커원본이름"
        assert result[0]["market"] == "NASDAQ"  # "US" 센티널은 항상 유효 시장으로 확정
        mock_cache.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_broker_confirmed_market_is_not_overwritten(self, mock_cache):
        """KIS처럼 브로커가 이미 확정한 시장(NYSE 등)은 조회 결과로 덮어쓰지 않는다."""
        mock_cache.get = AsyncMock(return_value=None)

        with patch(
            "app.providers._overseas_name_enrichment.resolve_ticker_meta",
            new=_meta_mock({"AAPL": ("Apple Inc.", "NASDAQ")}),
        ):
            result = await enrich_overseas_positions([_position("AAPL", "애플", market="AMEX")], mock_cache)

        assert result[0]["name"] == "Apple Inc."
        assert result[0]["market"] == "AMEX"  # 브로커 값 유지

    @pytest.mark.asyncio
    async def test_unmapped_yahoo_exchange_falls_back_to_nasdaq(self, mock_cache):
        mock_cache.get = AsyncMock(return_value=None)

        with patch(
            "app.providers._overseas_name_enrichment.resolve_ticker_meta",
            new=_meta_mock({"FOO": ("Foo Corp", "PNK")}),  # 유효 미국 시장 아님
        ):
            result = await enrich_overseas_positions([_position("FOO", "Foo")], mock_cache)

        assert result[0]["name"] == "Foo Corp"
        assert result[0]["market"] == "NASDAQ"

    @pytest.mark.asyncio
    async def test_duplicate_tickers_looked_up_once(self, mock_cache):
        mock_cache.get = AsyncMock(return_value=None)
        resolve_mock = _meta_mock({"AAPL": ("Apple Inc.", "NASDAQ")})

        with patch("app.providers._overseas_name_enrichment.resolve_ticker_meta", new=resolve_mock):
            result = await enrich_overseas_positions(
                [_position("AAPL", "애플1"), _position("AAPL", "애플2")], mock_cache
            )

        resolve_mock.assert_awaited_once_with("AAPL")
        assert [p["name"] for p in result] == ["Apple Inc.", "Apple Inc."]
