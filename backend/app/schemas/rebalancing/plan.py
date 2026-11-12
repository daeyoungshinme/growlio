"""리밸런싱 대기 플랜 스키마 (AUTO 모드: 계획 생성 → 매수 대기/매도 승인)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class RebalancingPlanItemOut(BaseModel):
    ticker: str | None
    name: str | None
    market: str | None
    quantity: int
    account_id: str | None
    order_type: str
    limit_price: float | None
    reference_price: float | None

    model_config = {"from_attributes": True}


class RebalancingPlanLegSummary(BaseModel):
    plan_id: uuid.UUID
    leg_id: uuid.UUID
    portfolio_id: uuid.UUID | None
    portfolio_name: str | None
    account_id: uuid.UUID | None
    account_name: str | None
    side: Literal["BUY", "SELL"]
    status: Literal["PENDING", "WAITING_FX", "EXECUTED", "CANCELED", "REJECTED", "EXPIRED", "FAILED"]
    deadline_at: datetime
    decided_at: datetime | None
    execution_id: uuid.UUID | None
    error_message: str | None
    actionable: bool  # status == PENDING and now < deadline_at
    # 이 leg는 실행되지 않고 끝났는데(FAILED/EXPIRED/REJECTED/CANCELED) 같은 플랜의 다른 leg는 체결된 "반쪽 실행"
    partially_executed: bool = False
    # 환전 대기(WAITING_FX, plans/120) — 마지막 판정의 필요/보유 달러와 자동 재확인 기한
    required_usd: float | None = None
    available_usd: float | None = None
    fx_retry_until: datetime | None = None
    items: list[RebalancingPlanItemOut]


class PlanActionResponse(BaseModel):
    status: str
    message: str
    # 환전 대기 재매수(STILL_SHORT) 응답에서 최신 필요/보유 달러
    required_usd: float | None = None
    available_usd: float | None = None


class SellDecisionRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]


class PlanTokenPreview(BaseModel):
    valid: bool
    reason: str | None = None  # "NOT_FOUND" | "ALREADY_DECIDED" | "EXPIRED" | "IN_PROGRESS" | "WAITING_FX"
    actionable: bool = False
    leg: RebalancingPlanLegSummary | None = None
