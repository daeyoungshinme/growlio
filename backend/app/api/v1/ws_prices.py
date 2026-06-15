"""WebSocket 실시간 가격 스트림 엔드포인트.

Protocol (C→S):
  1. 연결 직후 인증 메시지 전송 (3초 이내):
     {"type": "auth", "token": "<supabase_access_token>"}
  2. 구독 요청:
     {"action": "subscribe", "tickers": [{"ticker": "005930", "market": "KOSPI"}]}
  3. {"action": "ping"}
Protocol (S→C):
  {"type": "connected"}
  {"type": "price_update", "prices": {"005930": {"price": 75000, "market": "KOSPI", ...}}}
  {"type": "pong"} / {"type": "error", "detail": "..."}
"""
from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.auth_service import verify_supabase_token
from app.ws.connection_manager import manager

logger = structlog.get_logger()

router = APIRouter(tags=["websocket"])

_AUTH_TIMEOUT_SECONDS = 3.0


@router.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket) -> None:
    """실시간 주식 가격 WebSocket 스트림.

    연결 직후 auth 메시지로 인증한 뒤 subscribe 메시지를 전송해야 가격 업데이트를 받는다.
    토큰은 URL이 아닌 첫 번째 메시지로 전달하여 로그/히스토리 노출을 방지한다.
    """
    await websocket.accept()

    # 인증 메시지 대기 (타임아웃 내 미수신 시 종료)
    try:
        raw_auth = await asyncio.wait_for(
            websocket.receive_text(), timeout=_AUTH_TIMEOUT_SECONDS
        )
        auth_msg = json.loads(raw_auth)
        if auth_msg.get("type") != "auth":
            raise ValueError("auth 메시지가 아님")
        verify_supabase_token(auth_msg.get("token", ""))
    except (TimeoutError, json.JSONDecodeError, ValueError, KeyError):
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
                await websocket.send_text(json.dumps({"type": "error", "detail": "JSON 형식 오류"}))
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
        pass  # 클라이언트 정상 종료 — 추가 처리 불필요
    except Exception as e:
        logger.warning("ws_prices_error", ws_id=ws_id, error=str(e))
    finally:
        await manager.disconnect(ws_id)
        logger.info("ws_prices_disconnected", ws_id=ws_id, total=manager.connection_count)
