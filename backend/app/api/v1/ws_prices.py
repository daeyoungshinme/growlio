"""WebSocket 실시간 가격 스트림 엔드포인트.

Protocol (C→S):
  {"action": "subscribe", "tickers": [{"ticker": "005930", "market": "KOSPI"}]}
  {"action": "ping"}
Protocol (S→C):
  {"type": "connected"}
  {"type": "price_update", "prices": {"005930": {"price": 75000, "market": "KOSPI", ...}}}
  {"type": "pong"} / {"type": "error", "message": "..."}
"""
from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.services.auth_service import verify_supabase_token
from app.ws.connection_manager import manager

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/prices")
async def ws_prices(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """실시간 주식 가격 WebSocket 스트림.

    연결 후 subscribe 메시지를 전송해야 가격 업데이트를 받는다.
    인증: query param ?token=<supabase_access_token>
    """
    try:
        verify_supabase_token(token)
    except ValueError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    ws_id = await manager.connect(websocket)
    logger.info("ws_prices_connected", ws_id=ws_id, total=manager.connection_count)

    try:
        await websocket.send_text(json.dumps({"type": "connected"}))

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                msg_err = json.dumps({"type": "error", "message": "JSON 형식 오류"})
                await websocket.send_text(msg_err)
                continue

            action = msg.get("action")
            if action == "subscribe":
                tickers = msg.get("tickers", [])
                if isinstance(tickers, list):
                    await manager.subscribe(ws_id, tickers)
                    logger.info("ws_subscribed", ws_id=ws_id, count=len(tickers))
            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("ws_prices_error", ws_id=ws_id, error=str(e))
    finally:
        await manager.disconnect(ws_id)
        logger.info("ws_prices_disconnected", ws_id=ws_id, total=manager.connection_count)
