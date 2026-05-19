"""통합 포트폴리오 Pydantic 스키마 (백테스팅·리밸런싱 공용)."""
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class PortfolioItem(BaseModel):
    ticker: str
    name: str = ""   # 자동완성 없이 추가 시 빈 문자열 허용
    market: str
    weight: float    # 0~100, 합계 = 100


class PortfolioCreate(BaseModel):
    name: str
    items: list[PortfolioItem]
    base_type: str = "STOCK_ONLY"  # STOCK_ONLY | TOTAL_ASSETS

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[PortfolioItem]) -> list[PortfolioItem]:
        if not v:
            raise ValueError("종목이 최소 1개 이상이어야 합니다.")
        total = sum(i.weight for i in v)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"비중 합계가 100이어야 합니다. (현재: {total:.2f})")
        return v

    @field_validator("base_type")
    @classmethod
    def validate_base_type(cls, v: str) -> str:
        if v not in ("STOCK_ONLY", "TOTAL_ASSETS"):
            raise ValueError("base_type은 STOCK_ONLY 또는 TOTAL_ASSETS이어야 합니다.")
        return v


class PortfolioUpdate(BaseModel):
    name: str | None = None
    items: list[PortfolioItem] | None = None
    base_type: str | None = None

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[PortfolioItem] | None) -> list[PortfolioItem] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("종목이 최소 1개 이상이어야 합니다.")
        total = sum(i.weight for i in v)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"비중 합계가 100이어야 합니다. (현재: {total:.2f})")
        return v

    @field_validator("base_type")
    @classmethod
    def validate_base_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ("STOCK_ONLY", "TOTAL_ASSETS"):
            raise ValueError("base_type은 STOCK_ONLY 또는 TOTAL_ASSETS이어야 합니다.")
        return v


class PortfolioResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    items: list[PortfolioItem]
    base_type: str
    created_at: datetime
    updated_at: datetime
