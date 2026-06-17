"""ws/connection_manager.py 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.ws.connection_manager import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_returns_ws_id(self, manager):
        ws = AsyncMock()
        ws_id = await manager.connect(ws)
        assert isinstance(ws_id, str)
        assert len(ws_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_multiple_connections_unique_ids(self, manager):
        ws1, ws2 = AsyncMock(), AsyncMock()
        id1 = await manager.connect(ws1)
        id2 = await manager.connect(ws2)
        assert id1 != id2
        assert manager.connection_count == 2


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_removes_ws(self, manager):
        ws = AsyncMock()
        ws_id = await manager.connect(ws)
        assert manager.connection_count == 1

        await manager.disconnect(ws_id)
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown_id_is_noop(self, manager):
        await manager.disconnect("nonexistent-id")
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_cleans_subscriptions(self, manager):
        ws = AsyncMock()
        ws_id = await manager.connect(ws)
        await manager.subscribe(ws_id, [{"ticker": "AAPL", "market": "NASDAQ"}])

        tickers = manager.get_all_subscribed_tickers()
        assert ("AAPL", "NASDAQ") in tickers

        await manager.disconnect(ws_id)
        tickers = manager.get_all_subscribed_tickers()
        assert ("AAPL", "NASDAQ") not in tickers


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_adds_ticker(self, manager):
        ws = AsyncMock()
        ws_id = await manager.connect(ws)

        await manager.subscribe(ws_id, [{"ticker": "005930", "market": "KOSPI"}])

        tickers = manager.get_all_subscribed_tickers()
        assert ("005930", "KOSPI") in tickers

    @pytest.mark.asyncio
    async def test_subscribe_skips_empty_ticker(self, manager):
        ws = AsyncMock()
        ws_id = await manager.connect(ws)

        await manager.subscribe(ws_id, [{"ticker": "", "market": "KOSPI"}])

        tickers = manager.get_all_subscribed_tickers()
        assert tickers == []

    @pytest.mark.asyncio
    async def test_subscribe_multiple_tickers(self, manager):
        ws = AsyncMock()
        ws_id = await manager.connect(ws)

        await manager.subscribe(
            ws_id,
            [
                {"ticker": "AAPL", "market": "NASDAQ"},
                {"ticker": "TSLA", "market": "NASDAQ"},
            ],
        )

        tickers = manager.get_all_subscribed_tickers()
        assert len(tickers) == 2


class TestGetAllSubscribedTickers:
    @pytest.mark.asyncio
    async def test_empty_when_no_subscribers(self, manager):
        assert manager.get_all_subscribed_tickers() == []

    @pytest.mark.asyncio
    async def test_returns_only_active_subscriptions(self, manager):
        ws = AsyncMock()
        ws_id = await manager.connect(ws)
        await manager.subscribe(ws_id, [{"ticker": "AAPL", "market": "NASDAQ"}])

        result = manager.get_all_subscribed_tickers()
        assert ("AAPL", "NASDAQ") in result


class TestBroadcastPrices:
    @pytest.mark.asyncio
    async def test_empty_prices_is_noop(self, manager):
        await manager.broadcast_prices({})  # No error

    @pytest.mark.asyncio
    async def test_sends_to_subscribed_client(self, manager):
        ws = AsyncMock()
        ws_id = await manager.connect(ws)
        await manager.subscribe(ws_id, [{"ticker": "AAPL", "market": "NASDAQ"}])

        await manager.broadcast_prices(
            {"AAPL": {"price": 185.0, "market": "NASDAQ", "updated_at": "2024-01-01T00:00:00Z"}}
        )

        ws.send_text.assert_called_once()
        call_arg = ws.send_text.call_args[0][0]
        assert "price_update" in call_arg
        assert "AAPL" in call_arg

    @pytest.mark.asyncio
    async def test_disconnects_broken_ws_on_send_failure(self, manager):
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=Exception("connection closed"))
        ws_id = await manager.connect(ws)
        await manager.subscribe(ws_id, [{"ticker": "AAPL", "market": "NASDAQ"}])

        await manager.broadcast_prices({"AAPL": {"price": 185.0, "market": "NASDAQ", "updated_at": "now"}})

        assert manager.connection_count == 0


class TestConnectionCount:
    @pytest.mark.asyncio
    async def test_initial_count_zero(self, manager):
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_count_increases_with_connections(self, manager):
        for _ in range(3):
            await manager.connect(AsyncMock())
        assert manager.connection_count == 3


class TestBroadcastPricesEdgeCases:
    @pytest.mark.asyncio
    async def test_stale_subscription_skipped(self, manager):
        """ws_id가 구독에 있지만 connections에 없으면 건너뛴다."""
        ws = AsyncMock()
        ws_id = await manager.connect(ws)
        await manager.subscribe(ws_id, [{"ticker": "AAPL", "market": "NASDAQ"}])
        # Simulate stale subscription by removing from connections only
        manager._connections.pop(ws_id, None)

        await manager.broadcast_prices({"AAPL": {"price": 185.0, "market": "NASDAQ", "updated_at": "now"}})

        ws.send_text.assert_not_called()
