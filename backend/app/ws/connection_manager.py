"""WebSocket ConnectionManager — 실시간 가격 구독 연결 관리."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self) -> None:
        # ws_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # "ticker:market" → set[ws_id]
        self._subscriptions: defaultdict[str, set[str]] = defaultdict(set)
        # ws_id → set["ticker:market"]
        self._ws_keys: defaultdict[str, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> str:
        """이미 accept()된 WebSocket을 등록하고 ws_id를 반환한다."""
        ws_id = str(uuid.uuid4())
        async with self._lock:
            self._connections[ws_id] = ws
        return ws_id

    async def disconnect(self, ws_id: str) -> None:
        async with self._lock:
            self._connections.pop(ws_id, None)
            for key in self._ws_keys.pop(ws_id, set()):
                self._subscriptions[key].discard(ws_id)
                if not self._subscriptions[key]:
                    del self._subscriptions[key]

    async def subscribe(self, ws_id: str, tickers: list[dict[str, str]]) -> None:
        async with self._lock:
            for item in tickers:
                ticker = item.get("ticker", "")
                market = item.get("market", "")
                if not ticker or not market:
                    continue
                key = f"{ticker}:{market}"
                self._subscriptions[key].add(ws_id)
                self._ws_keys[ws_id].add(key)

    def get_all_subscribed_tickers(self) -> list[tuple[str, str]]:
        """현재 구독 중인 (ticker, market) 목록 — 구독자가 있는 종목만."""
        result = []
        for key, subscribers in self._subscriptions.items():
            if subscribers:
                parts = key.split(":", 1)
                if len(parts) == 2:
                    result.append((parts[0], parts[1]))
        return result

    async def broadcast_prices(self, prices: dict[str, dict[str, object]]) -> None:
        """prices: {ticker → {price, market, updated_at}} — 구독자별로 필터링해 전송."""
        if not prices:
            return

        ws_payloads: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
        for ticker, data in prices.items():
            market = data.get("market", "")
            key = f"{ticker}:{market}"
            for ws_id in list(self._subscriptions.get(key, set())):
                ws_payloads[ws_id][ticker] = data

        disconnected: list[str] = []
        for ws_id, payload in ws_payloads.items():
            ws = self._connections.get(ws_id)
            if not ws:
                continue
            try:
                await ws.send_text(json.dumps({"type": "price_update", "prices": payload}))
            except Exception as e:
                logger.warning("ws_send_failed", ws_id=ws_id, error=str(e))
                disconnected.append(ws_id)

        for ws_id in disconnected:
            await self.disconnect(ws_id)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()
