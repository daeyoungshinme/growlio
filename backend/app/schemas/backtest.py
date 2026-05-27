"""백테스팅 Pydantic 스키마."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class HoldingItem(BaseModel):
    ticker: str
    market: str
    weight: float  # 0~100, 합계 = 100


class BacktestPortfolioCreate(BaseModel):
    name: str
    holdings: list[HoldingItem]

    @field_validator("holdings")
    @classmethod
    def validate_holdings(cls, v: list[HoldingItem]) -> list[HoldingItem]:
        if not v:
            raise ValueError("종목이 최소 1개 이상이어야 합니다.")
        total = sum(h.weight for h in v)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"비중 합계가 100이어야 합니다. (현재: {total:.2f})")
        return v


class BacktestPortfolioUpdate(BaseModel):
    name: str | None = None
    holdings: list[HoldingItem] | None = None

    @field_validator("holdings")
    @classmethod
    def validate_holdings(cls, v: list[HoldingItem] | None) -> list[HoldingItem] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("종목이 최소 1개 이상이어야 합니다.")
        total = sum(h.weight for h in v)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"비중 합계가 100이어야 합니다. (현재: {total:.2f})")
        return v


class BacktestPortfolioResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    holdings: list[HoldingItem]
    created_at: datetime
    updated_at: datetime


# ── 백테스팅 실행 ─────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    portfolio_ids: list[uuid.UUID]
    start_date: date
    end_date: date
    include_spy: bool = True
    include_real_portfolio: bool = True
    reinvest_dividends: bool = True

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date는 start_date 이후여야 합니다.")
        return v


class SeriesData(BaseModel):
    name: str
    values: list[float | None]  # 기준 100으로 정규화. None = 해당 날짜 데이터 없음 (앞부분 패딩)


class PortfolioMetrics(BaseModel):
    name: str
    total_return_pct: float
    cagr_pct: float
    mdd_pct: float
    sharpe_ratio: float


class BacktestResult(BaseModel):
    dates: list[str]       # "YYYY-MM-DD" 목록
    series: list[SeriesData]
    metrics: list[PortfolioMetrics]
