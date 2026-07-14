"""리밸런싱 실행/실행 이력 스키마."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class ExecutionOrderItem(BaseModel):
    ticker: str
    name: str
    market: str
    side: str  # "BUY" | "SELL"
    quantity: int  # 양수 (방향은 side로)
    account_id: str | None = None  # 실행할 KIS 계좌 ID (None이면 default_account_id 사용)
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: float | None = None  # 국내=KRW 정수, 해외=USD 소수점 2자리
    reference_price: float | None = None  # 주문 생성 시점 조회한 참고 시세(표시 전용, 브로커 API에는 전달 안 됨)

    @model_validator(mode="after")
    def validate_limit_price(self) -> "ExecutionOrderItem":
        if self.order_type == "LIMIT" and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("지정가 주문에는 양수의 limit_price가 필요합니다.")
        return self


class ExecutionRequest(BaseModel):
    account_id: uuid.UUID | None = None  # 기본 KIS 계좌 (order에 account_id 없을 때 폴백)
    orders: list[ExecutionOrderItem]
    strategy: Literal["FULL", "BUY_ONLY", "TWO_PHASE"] = "FULL"

    @field_validator("orders")
    @classmethod
    def validate_orders(cls, v: list[ExecutionOrderItem]) -> list[ExecutionOrderItem]:
        if not v:
            raise ValueError("주문 항목이 최소 1개 이상이어야 합니다.")
        return v


class QuickExecuteOverride(BaseModel):
    """원클릭 실행(quick-execute) 시 저장된 알림 설정 대신 사용할 화면 값 override."""

    account_id: uuid.UUID | None = None
    strategy: Literal["FULL", "BUY_ONLY", "TWO_PHASE"] | None = None
    order_type: Literal["MARKET", "LIMIT"] | None = None


class QuickExecuteResult(BaseModel):
    """ "지금 테스트 실행" 결과 — AUTO와 동일하게 대기 플랜을 생성하고 이메일로 안내한다 (즉시 체결 아님)."""

    status: Literal["PLAN_GENERATED", "NO_DRIFT", "ALREADY_PENDING", "MARKET_BLOCKED"]
    message: str
    email_sent: bool = False
    plan_id: uuid.UUID | None = None
    buy_count: int = 0
    sell_count: int = 0


class KisBalancePosition(BaseModel):
    ticker: str
    name: str
    market: str
    quantity: int
    avg_price: float
    current_price: float
    value_krw: float


class KisBalanceResponse(BaseModel):
    account_id: str
    account_name: str
    is_mock: bool
    positions: list[KisBalancePosition]
    deposit_krw: float
    orderable_krw: float | None = None  # KIS만 지원 (nrcvb_buy_amt), 키움=None
    error: str | None = None  # 일괄 조회 시 계좌별 오류 메시지


# 키움 잔고 응답 — KIS와 동일한 구조
KiwoomBalanceResponse = KisBalanceResponse


class OrderResult(BaseModel):
    ticker: str
    name: str
    market: str
    side: str
    quantity: int
    status: str  # "SUCCESS" | "FAILED" | "SKIPPED"
    order_no: str | None = None
    error_msg: str | None = None
    order_type: str = "MARKET"
    price: float | None = None  # 지정가 또는 주문 생성 시점 참고 시세 (국내=KRW, 해외=USD)


class ExecutionResult(BaseModel):
    account_id: str
    account_name: str
    is_mock: bool
    orders: list[OrderResult]
    success_count: int
    fail_count: int
    executed_at: str  # ISO timestamp


class RebalancingExecutionSummary(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID | None
    triggered_by: str  # "MANUAL" | "AUTO"
    strategy: str  # "FULL" | "BUY_ONLY" | "TWO_PHASE"
    total_success: int
    total_fail: int
    total_skipped: int
    executed_at: datetime

    model_config = {"from_attributes": True}


class RebalancingExecutionDetail(RebalancingExecutionSummary):
    results: list[ExecutionResult] | None = None
