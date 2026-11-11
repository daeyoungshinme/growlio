import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


class GoalAccelerationScenario(BaseModel):
    years_earlier: int
    new_expected_goal_date: str  # "2036-04"
    required_monthly_deposit: float
    required_annual_deposit: float
    extra_monthly_deposit: float  # 현재 월 적립액 대비 추가로 필요한 금액
    # 적립액은 그대로 두고 수익률만 높인다면 필요한 연수익률(%) — 탐색범위(-90%~500%) 밖이면 None(달성 어려움)
    required_return_pct: float | None
    extra_return_pct: float | None  # 현재 가정 수익률(goal_annual_return_pct) 대비 추가로 필요한 %p


class GoalTimeline(BaseModel):
    months_to_goal: int | None
    expected_goal_date: str | None  # "2039-01" — 최초 계획 기준 달성 예정일
    actual_expected_goal_date: str | None = None  # "2037-04" — 현재 실적 기준 달성 예상일
    current_progress_pct: float | None  # 대시보드 goal_achievement_pct와 동일 소스(부동산 제외 투자자산÷목표금액)
    on_track: bool | None
    lead_lag_months: int | None  # 양수=앞서는 개월, 음수=뒤처지는 개월
    # 현재 페이스보다 N년 더 빨리 달성하려면 월 적립액을 얼마로 늘려야 하는지 역산 — 목표 미달성 시에만 채워짐
    acceleration_scenarios: list[GoalAccelerationScenario] = []


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


class FxPositionResponse(BaseModel):
    """USD/KRW 1년 통계적 위치 — 예측이 아닌 과거 분포·변동성 기반 참고치."""

    rate: float
    low_1y: float
    high_1y: float
    percentile_1y: float  # 1년 종가 중 현재보다 낮았던 비율(%) — 낮을수록 달러가 싸다
    ma20: float
    ma60: float
    deviation_ma20_pct: float
    deviation_ma60_pct: float
    sigma_1m: float  # 일간 로그수익률 표준편차 × √21 × 현재 환율(원)
    range_1m_low: float
    range_1m_high: float
    zone: Literal["CHEAP", "NEUTRAL", "EXPENSIVE"]


class FxTrancheResponse(BaseModel):
    label: str
    target_rate: float | None  # None = 지금(또는 적립일) 환전
    usd: float
    krw_estimate: float


class FxPortfolioOption(BaseModel):
    id: uuid.UUID
    name: str


class FxPlanHeldAccount(BaseModel):
    account_id: uuid.UUID
    name: str
    usd: float
    # LIVE = 증권사 실시간, SYNCED = 마지막 동기화 값(토스·실시간 실패), MANUAL = 수기 계좌에 직접 입력한 값
    source: Literal["LIVE", "SYNCED", "MANUAL"]


class FxPlanResponse(BaseModel):
    position: FxPositionResponse | None  # 1년 시계열 조회 실패 시 None
    rate_is_live: bool = True  # False면 실시간 환율이 없어 1년 일봉 마지막 종가(없으면 설정 fallback) 기준
    status: Literal["OK", "SUFFICIENT", "NO_DEPOSIT_GOAL", "NO_OVERSEAS", "NO_PORTFOLIO", "NO_RATE"]
    portfolio_id: uuid.UUID | None
    portfolio_name: str | None
    portfolio_options: list[FxPortfolioOption]  # 해외 비중이 있는 포트폴리오
    months: int
    overseas_weight_pct: float
    monthly_deposit_krw: float | None
    monthly_need_usd: float
    held_usd: float
    need_usd: float
    tranches: list[FxTrancheResponse]
    # plans/121 B
    # DCA_AMOUNT = 정액 적립 알림 금액의 해외 몫, MONTHLY_GOAL = 월 적립액 × 해외 비중. 계산 전 상태면 None
    deposit_source: Literal["DCA_AMOUNT", "MONTHLY_GOAL"] | None = None
    held_usd_is_live: bool = False  # 달러가 있는 계좌를 모두 증권사에서 실시간으로 읽었는지
    held_usd_accounts: list[FxPlanHeldAccount] = []  # 보유 달러 계좌별 내역(0달러 제외, 큰 순)
    waiting_fx_usd: float = 0.0  # 환전 대기 중인 적립 매수를 진행하려면 지금 더 필요한 달러


class FxPlanAlertTarget(BaseModel):
    # ExchangeRateAlert.target_rate는 Numeric(10,2), planned_usd는 Numeric(18,2)
    target_rate: float = Field(gt=0, le=100_000, allow_inf_nan=False)
    usd: float = Field(ge=0, le=100_000_000, allow_inf_nan=False)


def _unique_targets(v: list[FxPlanAlertTarget]) -> list[FxPlanAlertTarget]:
    rates = [round(t.target_rate, 2) for t in v]
    if len(rates) != len(set(rates)):
        raise ValueError("같은 목표 환율이 중복되었습니다")
    return v


class FxPlanAlertTargets(BaseModel):
    """계획 구간 목표 — 빈 목록이면 이 범위의 미발동 계획 알림을 모두 지운다."""

    targets: list[FxPlanAlertTarget] = Field(max_length=5)

    @field_validator("targets")
    @classmethod
    def unique_targets(cls, v: list[FxPlanAlertTarget]) -> list[FxPlanAlertTarget]:
        return _unique_targets(v)


class FxPlanAlertSyncRequest(FxPlanAlertTargets):
    """계획 구간 목표로 환율 알림을 맞춘다 — 빈 목록이면 이 포트폴리오의 미발동 계획 알림을 모두 지운다."""

    portfolio_id: uuid.UUID


class FxPlanAlertSyncResponse(BaseModel):
    created: int
    updated: int
    removed: int
    skipped_manual: int  # 같은 목표의 직접 등록한 BELOW 알림이 이미 있어 만들지 않은 구간 수


# ── 추가 환전 항목(여행 등, plans/123) ─────────────────────────

_MAX_USD = 100_000_000  # planned_usd·amount_usd Numeric(18,2) 안쪽의 넉넉한 상한


class FxExtraNeedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    amount_usd: float = Field(gt=0, le=_MAX_USD, allow_inf_nan=False)
    exchanged_usd: float = Field(0, ge=0, le=_MAX_USD, allow_inf_nan=False)
    due_date: date

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("이름을 입력해 주세요")
        return v


class FxExtraNeedUpdate(BaseModel):
    """보낸 필드만 바꾼다(null은 무시)."""

    name: str | None = Field(None, min_length=1, max_length=40)
    amount_usd: float | None = Field(None, gt=0, le=_MAX_USD, allow_inf_nan=False)
    exchanged_usd: float | None = Field(None, ge=0, le=_MAX_USD, allow_inf_nan=False)
    due_date: date | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("이름을 입력해 주세요")
        return v


class FxExtraNeedResponse(BaseModel):
    id: uuid.UUID
    name: str
    amount_usd: float
    exchanged_usd: float
    remaining_usd: float
    due_date: date
    days_left: int  # 음수면 필요일이 지남
    # OK = 구간 있음, DONE = 다 환전함, PAST_DUE = 필요일 지남, NO_RATE = 환율을 몰라 구간 계산 안 함
    status: Literal["OK", "DONE", "PAST_DUE", "NO_RATE"]
    tranches: list[FxTrancheResponse]


class FxExtraNeedsResponse(BaseModel):
    rate: float | None  # 구간 계산에 쓴 환율(항목이 없거나 환율을 모르면 None)
    rate_is_live: bool = True
    needs: list[FxExtraNeedResponse]
