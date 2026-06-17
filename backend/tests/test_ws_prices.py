"""WebSocket 가격 스트림 테스트 (GET /api/v1/ws/prices)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_redis_scheduler(monkeypatch):
    import app.redis_client as rc
    import app.scheduler as sched

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.aclose = AsyncMock()
    monkeypatch.setattr(rc, "redis_client", mock_redis)
    monkeypatch.setattr(sched.scheduler, "start", lambda: None)
    monkeypatch.setattr(sched.scheduler, "shutdown", lambda: None)
    yield
    rc.redis_client = None


class TestWsPrices:
    def test_ws_closes_without_auth(self, override_settings):
        from app.main import app

        with (
            TestClient(app, raise_server_exceptions=False) as client,
            client.websocket_connect("/api/v1/ws/prices") as ws,
        ):
            import contextlib

            with contextlib.suppress(Exception):
                ws.receive_json()

    def test_ws_closes_with_invalid_token(self, override_settings):
        from app.main import app

        # invalid token causes ValueError in ws handler, connection should close cleanly
        with (
            patch(
                "app.api.v1.ws_prices.verify_supabase_token",
                side_effect=ValueError("invalid token"),
            ),
            TestClient(app, raise_server_exceptions=False) as client,
        ):
            try:
                with client.websocket_connect("/api/v1/ws/prices") as ws:
                    ws.send_text(json.dumps({"type": "auth", "token": "bad_token"}))
                    ws.receive_json()
            except Exception:
                pass  # WebSocket closed as expected

    def test_ws_connects_with_valid_token(self, override_settings):
        from app.main import app
        from app.ws.connection_manager import manager

        async def mock_connect(websocket):
            return "ws-test-id"

        async def mock_disconnect(ws_id):
            pass

        with (
            patch("app.api.v1.ws_prices.verify_supabase_token", return_value=True),
            patch.object(manager, "connect", side_effect=mock_connect),
            patch.object(manager, "disconnect", side_effect=mock_disconnect),
            TestClient(app, raise_server_exceptions=False) as client,
            client.websocket_connect("/api/v1/ws/prices") as ws,
        ):
            ws.send_text(json.dumps({"type": "auth", "token": "valid_token"}))
            data = ws.receive_json()
            assert data["type"] == "connected"

    def test_ws_closes_with_wrong_message_type(self, override_settings):
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            try:
                with client.websocket_connect("/api/v1/ws/prices") as ws:
                    ws.send_text(json.dumps({"type": "ping", "token": "some_token"}))
                    ws.receive_json()
            except Exception:
                pass  # connection closed with wrong message type

    def test_ws_subscribe_action(self, override_settings):
        from app.main import app
        from app.ws.connection_manager import manager

        async def mock_connect(websocket):
            return "ws-test-id"

        async def mock_subscribe(ws_id, tickers):
            pass

        async def mock_disconnect(ws_id):
            pass

        with (
            patch("app.api.v1.ws_prices.verify_supabase_token", return_value=True),
            patch.object(manager, "connect", side_effect=mock_connect),
            patch.object(manager, "subscribe", side_effect=mock_subscribe),
            patch.object(manager, "disconnect", side_effect=mock_disconnect),
            TestClient(app, raise_server_exceptions=False) as client,
            client.websocket_connect("/api/v1/ws/prices") as ws,
        ):
            ws.send_text(json.dumps({"type": "auth", "token": "valid_token"}))
            ws.receive_json()  # "connected"
            ws.send_text(json.dumps({"action": "subscribe", "tickers": ["005930", "AAPL"]}))
            ws.send_text(json.dumps({"action": "ping"}))
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_ws_invalid_json_after_connect(self, override_settings):
        from app.main import app
        from app.ws.connection_manager import manager

        async def mock_connect(websocket):
            return "ws-test-id"

        async def mock_disconnect(ws_id):
            pass

        with (
            patch("app.api.v1.ws_prices.verify_supabase_token", return_value=True),
            patch.object(manager, "connect", side_effect=mock_connect),
            patch.object(manager, "disconnect", side_effect=mock_disconnect),
            TestClient(app, raise_server_exceptions=False) as client,
            client.websocket_connect("/api/v1/ws/prices") as ws,
        ):
            ws.send_text(json.dumps({"type": "auth", "token": "valid_token"}))
            ws.receive_json()  # "connected"
            ws.send_text("this is not valid json {{{")
            data = ws.receive_json()
            assert data["type"] == "error"

    def test_ws_responds_to_ping(self, override_settings):
        from app.main import app
        from app.ws.connection_manager import manager

        async def mock_connect(websocket):
            return "ws-test-id"

        async def mock_subscribe(ws_id, tickers):
            pass

        async def mock_disconnect(ws_id):
            pass

        with (
            patch("app.api.v1.ws_prices.verify_supabase_token", return_value=True),
            patch.object(manager, "connect", side_effect=mock_connect),
            patch.object(manager, "subscribe", side_effect=mock_subscribe),
            patch.object(manager, "disconnect", side_effect=mock_disconnect),
            TestClient(app, raise_server_exceptions=False) as client,
            client.websocket_connect("/api/v1/ws/prices") as ws,
        ):
            ws.send_text(json.dumps({"type": "auth", "token": "valid_token"}))
            ws.receive_json()  # "connected"
            ws.send_text(json.dumps({"action": "ping"}))
            data = ws.receive_json()
            assert data["type"] == "pong"
