from pydantic import BaseModel, Field


class DashboardStockPnl(BaseModel):
    """홈 히어로 "주식 평가손익" — 자산 탭 overview(합산 제외 계좌 제외)와 같은 값."""

    total_stock_krw: float
    unrealized_pnl_krw: float
    return_pct: float


class DashboardResponse(BaseModel):
    total_assets_krw: float
    investable_assets_krw: float | None = None  # 부동산 제외 — goal_achievement_pct의 분자
    asset_allocation: list[dict]
    goal_amount: float | None
    goal_achievement_pct: float | None
    stock_return_pct: float
    annual_return_pct: float | None
    annual_deposit_goal: float | None = None
    annual_deposit_current: float = 0.0
    deposit_achievement_pct: float | None = None
    estimated_annual_dividends: float | None = None
    cumulative_return_pct: float | None = None
    xirr_pct: float | None = Field(None, ge=-99, le=1000)
    goal_annual_return_pct: float | None = None
    return_goal_gap_pct: float | None = None
    retirement_target_year: int | None = None
    annual_dividend_goal: float | None = None
    dividend_goal_achievement_pct: float | None = None
    # 홈이 lite overview·적립 분석을 따로 받지 않게(plans/151 B1). 주식이 없거나 목표·적립 설정이 없으면 None
    stock_pnl: DashboardStockPnl | None = None
    goal_expected_month: str | None = None  # "YYYY-MM" — 실적 기준 예상, 없으면 계획 기준
