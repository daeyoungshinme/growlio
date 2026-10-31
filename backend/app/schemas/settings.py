"""사용자 설정 API(`api/v1/settings.py`) 요청·응답 스키마."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.constants import (
    DEFAULT_GOAL_CAGR_LOOKBACK_YEARS,
    DEFAULT_GOAL_MAX_WEIGHT_PCT,
    DEFAULT_GOAL_SHORT_TERM_EQUITY_FLOOR_PCT,
    MAX_GOAL_CANDIDATE_TICKERS,
)
from app.enums import AgeGroup, GoalRiskTolerance, IncomeBracket
from app.schemas._validators import validate_non_negative_amount, validate_positive_amount
from app.schemas.asset import MAX_CREDENTIAL_LENGTH
from app.schemas.rebalancing.goal import GoalCandidateTicker
from app.utils.kst import today_kst

# 목표 연도 상한(현재 연도 기준) — 은퇴 목표도 충분히 담는 값
MAX_GOAL_YEARS_AHEAD = 100


class DartApiKeyUpdate(BaseModel):
    api_key: str = Field(min_length=1, max_length=MAX_CREDENTIAL_LENGTH)  # 암호화 후 String(512)


class GoalUpdate(BaseModel):
    goal_amount: float | None = None
    goal_annual_return_pct: float | None = None
    annual_deposit_goal: float | None = None
    monthly_deposit_amount: float | None = None
    retirement_target_year: int | None = None
    goal_start_date: date | None = None
    goal_initial_amount: float | None = None
    annual_dividend_goal: float | None = None
    birth_year: int | None = None

    @field_validator(
        "goal_amount", "annual_deposit_goal", "goal_initial_amount", "monthly_deposit_amount", "annual_dividend_goal"
    )
    @classmethod
    def validate_positive(cls, v: float | None) -> float | None:
        return validate_non_negative_amount(v)

    @field_validator("goal_annual_return_pct")
    @classmethod
    def validate_return_pct(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("수익률은 0~100% 범위여야 합니다")
        return v

    @field_validator("retirement_target_year")
    @classmethod
    def validate_target_year(cls, v: int | None) -> int | None:
        if v is not None and v < today_kst().year:
            raise ValueError("목표 연도는 현재 연도 이상이어야 합니다")
        # 상한이 없으면 10000이 저장돼 목표 추천의 date(target_year, 12, 31)이 매번 500을 냈다(계획 57 C4)
        if v is not None and v > today_kst().year + MAX_GOAL_YEARS_AHEAD:
            raise ValueError(f"목표 연도는 {MAX_GOAL_YEARS_AHEAD}년 이내여야 합니다")
        return v

    @field_validator("birth_year")
    @classmethod
    def validate_birth_year(cls, v: int | None) -> int | None:
        if v is not None and not (1900 <= v <= today_kst().year):
            raise ValueError("출생연도가 올바르지 않습니다")
        return v


class GoalCandidateTickersUpdate(BaseModel):
    tickers: list[GoalCandidateTicker]

    @field_validator("tickers")
    @classmethod
    def validate_max_count(cls, v: list[GoalCandidateTicker]) -> list[GoalCandidateTicker]:
        if len(v) > MAX_GOAL_CANDIDATE_TICKERS:
            raise ValueError(f"후보 ETF는 최대 {MAX_GOAL_CANDIDATE_TICKERS}개까지 등록할 수 있습니다")
        return v


class GoalRecommendationOptionsUpdate(BaseModel):
    risk_tolerance: GoalRiskTolerance = GoalRiskTolerance.CONSERVATIVE
    max_weight_pct: float = DEFAULT_GOAL_MAX_WEIGHT_PCT
    cagr_lookback_years: int = DEFAULT_GOAL_CAGR_LOOKBACK_YEARS
    short_term_equity_floor_pct: float = DEFAULT_GOAL_SHORT_TERM_EQUITY_FLOOR_PCT
    age_group: AgeGroup | None = None  # 연령대별 추천(goal-recommendation/by-age) 전용 — 미입력 시 None
    # 전체 자산 기준 추천(get_goal_recommendation) 전용 자산군 상한(%) — None이면 상한 없음(기본값).
    bond_ceiling_pct: float | None = None
    cash_ceiling_pct: float | None = None

    @field_validator("max_weight_pct")
    @classmethod
    def validate_max_weight(cls, v: float) -> float:
        if not (10 <= v <= 100):
            raise ValueError("종목당 최대 비중은 10~100% 범위여야 합니다")
        return v

    @field_validator("cagr_lookback_years")
    @classmethod
    def validate_lookback(cls, v: int) -> int:
        if v not in (3, 5, 10):
            raise ValueError("수익률 산출 기간은 3/5/10년 중 하나여야 합니다")
        return v

    @field_validator("short_term_equity_floor_pct")
    @classmethod
    def validate_short_term_equity_floor(cls, v: float) -> float:
        if not (0 <= v <= 100):
            raise ValueError("단기 목표 최소 주식 비중은 0~100% 범위여야 합니다")
        return v

    @field_validator("bond_ceiling_pct", "cash_ceiling_pct")
    @classmethod
    def validate_class_ceiling(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("자산군 비중 상한은 0~100% 범위여야 합니다")
        return v


class NotificationEmailUpdate(BaseModel):
    notification_email: EmailStr | None = None


class PushTokenUpdate(BaseModel):
    fcm_token: str | None = Field(default=None, max_length=512)


class ToggleUpdate(BaseModel):
    enabled: bool


class IncomeBracketUpdate(BaseModel):
    """절세 액션 플랜의 연금 세액공제율 분기용 소득 구간. None이면 미입력(13.2% 하한값 추정)."""

    income_bracket: IncomeBracket | None = None


class AutoRebalancingDailyCapUpdate(BaseModel):
    """AUTO 리밸런싱 유저 단위 하루 합산 거래대금 상한(KRW). None(또는 생략)이면 무제한(기본값)."""

    daily_value_cap_krw: float | None = None

    @field_validator("daily_value_cap_krw")
    @classmethod
    def validate_positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("하루 합산 거래한도는 0보다 커야 합니다")
        return validate_positive_amount(v)


class SettingsResponse(BaseModel):
    has_kis: bool
    has_dart: bool
    goal_amount: float | None
    goal_annual_return_pct: float | None
    annual_deposit_goal: float | None
    monthly_deposit_amount: float | None = None
    retirement_target_year: int | None = None
    user_email: str
    notification_email: str | None = None
    annual_dividend_goal: float | None = None
    fcm_token_stored: bool = False
    composite_signal_alerts_enabled: bool = True
    market_signal_daily_digest_enabled: bool = False
    year_end_tax_reminder_enabled: bool = False
    goal_achievement_alerts_enabled: bool = True
    monthly_report_enabled: bool = True
    recommendation_drift_alert_enabled: bool = False
    challenge_reminders_enabled: bool = False
    goal_candidate_tickers: list[GoalCandidateTicker] = []
    goal_risk_tolerance: GoalRiskTolerance = GoalRiskTolerance.CONSERVATIVE
    goal_max_weight_pct: float = DEFAULT_GOAL_MAX_WEIGHT_PCT
    goal_cagr_lookback_years: int = DEFAULT_GOAL_CAGR_LOOKBACK_YEARS
    goal_short_term_equity_floor_pct: float = DEFAULT_GOAL_SHORT_TERM_EQUITY_FLOOR_PCT
    goal_bond_ceiling_pct: float | None = None
    goal_cash_ceiling_pct: float | None = None
    age_group: AgeGroup | None = None
    birth_year: int | None = None
    income_bracket: IncomeBracket | None = None
    # 서버 전역 설정(env) — 유저별 조정 불가. 리밸런싱 알림 설정 화면에서 AUTO 모드의
    # 1건당 거래대금 안전장치 상한을 안내하기 위해 노출한다 (app/services/rebalancing/order_builder.py 참고).
    auto_rebalancing_max_order_value_krw: float = 50_000_000.0
    # 유저 단위 하루 합산 거래대금 상한 — None이면 무제한(기본값). 위 1건당 상한과 별개(app/models/user.py 참고).
    auto_rebalancing_daily_value_cap_krw: float | None = None
