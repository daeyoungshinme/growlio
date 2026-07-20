from pydantic import BaseModel, Field


class DashboardResponse(BaseModel):
    total_assets_krw: float
    asset_allocation: list[dict]
    goal_amount: float | None
    goal_achievement_pct: float | None
    stock_return_pct: float
    annual_return_pct: float | None
    monthly_trend: list[dict]
    annual_deposit_goal: float | None = None
    annual_deposit_current: float = 0.0
    deposit_achievement_pct: float | None = None
    annual_dividends_received: float | None = None
    estimated_annual_dividends: float | None = None
    dividend_monthly_breakdown: list[dict] = []
    cumulative_return_pct: float | None = None
    xirr_pct: float | None = Field(None, ge=-99, le=1000)
    xirr_is_estimated: bool = False
    goal_annual_return_pct: float | None = None
    return_goal_gap_pct: float | None = None
    retirement_target_year: int | None = None
    annual_dividend_goal: float | None = None
    dividend_goal_achievement_pct: float | None = None
