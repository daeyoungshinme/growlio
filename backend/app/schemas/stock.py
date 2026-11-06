"""종목 시세 API 요청 스키마."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class TickerMarket(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    market: str
    account_id: uuid.UUID | None = None  # KIS 연동 보유 계좌 — 다른 소스가 전부 실패했을 때만 사용


class StockPriceBatchRequest(BaseModel):
    items: list[TickerMarket] = Field(..., max_length=50)
