from pydantic import BaseModel


class DCAProjectionPoint(BaseModel):
    month: str  # "2024-01"
    projected_krw: float
    actual_krw: float | None
    achievement_pct: float | None
    has_data: bool


class YearlyAchievement(BaseModel):
    year: int
    projected_year_end_krw: float
    actual_year_end_krw: float | None
    achievement_pct: float | None
    has_data: bool


class GoalTimeline(BaseModel):
    months_to_goal: int | None
    expected_goal_date: str | None  # "2039-01" — 최초 계획 기준 달성 예정일
    actual_expected_goal_date: str | None  # "2037-04" — 현재 실적 기준 달성 예상일
    current_progress_pct: float | None
    on_track: bool | None
    lead_lag_months: int | None  # 양수=앞서는 개월, 음수=뒤처지는 개월


class DCASettings(BaseModel):
    monthly_deposit_amount: float | None
    goal_annual_return_pct: float | None
    goal_amount: float | None
    goal_start_date: str | None  # "2024-01-01"
    goal_initial_amount: float | None


class DCAAnalysisResponse(BaseModel):
    settings: DCASettings
    projection_months: list[DCAProjectionPoint]
    yearly_achievements: list[YearlyAchievement]
    goal_timeline: GoalTimeline
    is_configured: bool
