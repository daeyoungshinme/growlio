from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.enums import TransactionType
from app.schemas._validators import validate_non_negative_amount, validate_positive_amount


class TransactionCreate(BaseModel):
    account_id: UUID | None = None
    transaction_type: TransactionType
    amount: float
    transaction_date: date
    ticker: str | None = None
    notes: str | None = None
    fee: float | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        return validate_positive_amount(v)  # type: ignore[return-value]

    @field_validator("fee")
    @classmethod
    def fee_non_negative(cls, v: float | None) -> float | None:
        return validate_non_negative_amount(v)


class TransactionUpdate(BaseModel):
    transaction_type: TransactionType | None = None
    amount: float | None = None
    transaction_date: date | None = None
    ticker: str | None = None
    notes: str | None = None
    fee: float | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float | None) -> float | None:
        return validate_positive_amount(v)

    @field_validator("fee")
    @classmethod
    def fee_non_negative(cls, v: float | None) -> float | None:
        return validate_non_negative_amount(v)


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
