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
    status: Literal["PENDING", "EXECUTED", "CANCELED", "REJECTED", "EXPIRED", "FAILED"]
    deadline_at: datetime
    decided_at: datetime | None
    execution_id: uuid.UUID | None
    error_message: str | None
    actionable: bool  # status == PENDING and now < deadline_at
    items: list[RebalancingPlanItemOut]


class PlanActionResponse(BaseModel):
    status: str
    message: str


class SellDecisionRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]


class PlanTokenPreview(BaseModel):
    valid: bool
    reason: str | None = None  # "NOT_FOUND" | "ALREADY_DECIDED" | "EXPIRED"
    actionable: bool = False
    leg: RebalancingPlanLegSummary | None = None
