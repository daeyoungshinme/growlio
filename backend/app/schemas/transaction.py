from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.enums import TransactionType
from app.schemas._validators import NonNegativeAmount, PositiveAmount


class TransactionCreate(BaseModel):
    account_id: UUID | None = None
    transaction_type: TransactionType
    amount: PositiveAmount
    transaction_date: date
    ticker: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    fee: NonNegativeAmount | None = None


class TransactionUpdate(BaseModel):
    transaction_type: TransactionType | None = None
    amount: PositiveAmount | None = None
    transaction_date: date | None = None
    ticker: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    fee: NonNegativeAmount | None = None


class TransactionResponse(BaseModel):
    id: UUID
    account_id: UUID | None
    transaction_type: TransactionType
    amount: float
    fee: float | None
    transaction_date: date
    ticker: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionTotal(BaseModel):
    """계좌·유형별 거래 합계 — 목록 한 페이지(기본 100건)를 화면에서 더하면 오래된 기록이 빠졌다(plans/90 B2)."""

    account_id: UUID | None
    transaction_type: TransactionType
    total_amount: float
    count: int
