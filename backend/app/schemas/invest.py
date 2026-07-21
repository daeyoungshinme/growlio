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
    actual_expected_goal_date: str | None = None  # "2037-04" — 현재 실적 기준 달성 예상일
    current_progress_pct: float | None  # 대시보드 goal_achievement_pct와 동일 소스(총자산÷목표금액)
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


class DepositGuideItem(BaseModel):
    annual_return_pct: float
    required_monthly_deposit: float
    required_annual_deposit: float


class GoalFeasibilityPreview(BaseModel):
    required_return_pct: float | None  # None이면 탐색 범위(-90%~500%) 내에서 달성 불가능
    pv: float  # 계산에 사용된 현재 자산(직접 입력값 또는 총자산 스냅샷)
    n_months: int
    note: str | None = None
    # 가정 수익률 프리셋(보수적/중립/공격적)별 필요 월/연 적립액 — monthly_deposit_amount와 무관하게
    # pv·목표금액·기간만으로 계산되는 별도 가이드(목표 달성에 필요한 월 적립액을 스스로 지어내지 않도록)
    deposit_guide: list[DepositGuideItem] = []
