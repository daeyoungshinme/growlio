"""백테스팅 Pydantic 스키마."""

import uuid
from collections.abc import Sequence
from datetime import date

from pydantic import BaseModel, Field, ValidationInfo, field_validator

# ── 백테스팅 실행 ─────────────────────────────────────────


# 백테스트는 시작일부터 일 단위로 순회한다 — 하한이 없으면 1900년 같은 값으로 요청 하나가 수십만 회 루프를 돈다
MIN_BACKTEST_START = date(1990, 1, 1)


class BacktestRunRequest(BaseModel):
    portfolio_ids: list[uuid.UUID] = Field(max_length=30)  # 빈 목록 허용 — SPY·실포트폴리오만 비교
    start_date: date = Field(ge=MIN_BACKTEST_START)
    end_date: date
    include_spy: bool = True
    include_real_portfolio: bool = True
    reinvest_dividends: bool = True

    @field_validator("end_date")
    @classmethod
    def validate_dates(cls, v: date, info: ValidationInfo) -> date:
        start = info.data.get("start_date")
        if start and v <= start:
            raise ValueError("end_date는 start_date 이후여야 합니다.")
        return v


class SeriesData(BaseModel):
    name: str
    values: Sequence[float | None]  # 기준 100으로 정규화. None = 해당 날짜 데이터 없음 (앞부분 패딩)


class PortfolioMetrics(BaseModel):
    name: str
    total_return_pct: float
    cagr_pct: float
    mdd_pct: float
    sharpe_ratio: float
    volatility_pct: float = 0.0
    sortino_ratio: float = 0.0


class BacktestResult(BaseModel):
    dates: list[str]  # "YYYY-MM-DD" 목록
    series: list[SeriesData]
    metrics: list[PortfolioMetrics]
