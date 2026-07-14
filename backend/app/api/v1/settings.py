"""사용자 설정 및 증권사 자격증명 관리 API."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.enums import AssetClass, GoalRiskTolerance, IndexRegion
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.services._settings_queries import get_or_create_settings, get_settings_row, has_active_kis_credentials
from app.services.credential_service import encrypt
from app.services.recommendation_universe import MAX_GOAL_CANDIDATE_TICKERS
from app.utils.cache_keys import (
    dashboard_summary_key,
    invalidate_goal_recommendation_caches,
    invalidate_user_caches,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class DartApiKeyUpdate(BaseModel):
    api_key: str


class GoalUpdate(BaseModel):
    goal_amount: float | None = None
    goal_annual_return_pct: float | None = None
    annual_deposit_goal: float | None = None
    monthly_deposit_amount: float | None = None
    retirement_target_year: int | None = None
    goal_start_date: date | None = None
    goal_initial_amount: float | None = None
    annual_dividend_goal: float | None = None

    @field_validator(
        "goal_amount", "annual_deposit_goal", "goal_initial_amount", "monthly_deposit_amount", "annual_dividend_goal"
    )
    @classmethod
    def validate_positive(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("금액은 0 이상이어야 합니다")
        return v

    @field_validator("goal_annual_return_pct")
    @classmethod
    def validate_return_pct(cls, v: float | None) -> float | None:
        if v is not None and not (0 <= v <= 100):
            raise ValueError("수익률은 0~100% 범위여야 합니다")
        return v

    @field_validator("retirement_target_year")
    @classmethod
    def validate_target_year(cls, v: int | None) -> int | None:
        if v is not None and v < date.today().year:
            raise ValueError("목표 연도는 현재 연도 이상이어야 합니다")
        return v


class GoalCandidateTicker(BaseModel):
    ticker: str
    name: str
    market: str
    asset_class: AssetClass = AssetClass.EQUITY
    index_region: IndexRegion | None = None


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
    max_weight_pct: float = 40.0
    cagr_lookback_years: int = 10
    short_term_equity_floor_pct: float = 80.0

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


class NotificationEmailUpdate(BaseModel):
    notification_email: EmailStr | None = None


class AutoDcaUpdate(BaseModel):
    enabled: bool
    day: int | None = None
    amount: float | None = None
    portfolio_id: str | None = None
    account_id: str | None = None

    @field_validator("day")
    @classmethod
    def validate_day(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 28):
            raise ValueError("실행일은 1~28 사이여야 합니다")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("매수 금액은 0보다 커야 합니다")
        if v is not None and v > 1_000_000_000:
            raise ValueError("매수 금액은 10억 원을 초과할 수 없습니다")
        return v


class PushTokenUpdate(BaseModel):
    fcm_token: str | None = None


class CompositeSignalAlertsUpdate(BaseModel):
    enabled: bool


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
    auto_dca_enabled: bool = False
    auto_dca_day: int | None = None
    auto_dca_amount: float | None = None
    auto_dca_portfolio_id: str | None = None
    auto_dca_account_id: str | None = None
    auto_dca_last_executed_at: str | None = None
    annual_dividend_goal: float | None = None
    fcm_token_stored: bool = False
    composite_signal_alerts_enabled: bool = True
    goal_candidate_tickers: list[GoalCandidateTicker] = []
    goal_risk_tolerance: GoalRiskTolerance = GoalRiskTolerance.CONSERVATIVE
    goal_max_weight_pct: float = 40.0
    goal_cagr_lookback_years: int = 10
    goal_short_term_equity_floor_pct: float = 80.0


@router.get("", response_model=SettingsResponse)
@limiter.limit("30/minute")
async def get_settings(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 설정 조회 (자격증명 원문은 반환하지 않음)."""
    row = await get_settings_row(db, current_user.id)
    has_kis = await has_active_kis_credentials(db, current_user.id)

    if not row:
        return SettingsResponse(
            has_kis=has_kis,
            has_dart=False,
            goal_amount=None,
            goal_annual_return_pct=None,
            annual_deposit_goal=None,
            user_email=current_user.email,
            notification_email=None,
        )
    return SettingsResponse(
        has_kis=has_kis,
        has_dart=bool(row.dart_api_key),
        goal_amount=float(row.goal_amount) if row.goal_amount else None,
        goal_annual_return_pct=float(row.goal_annual_return_pct) if row.goal_annual_return_pct else None,
        annual_deposit_goal=float(row.annual_deposit_goal) if row.annual_deposit_goal else None,
        monthly_deposit_amount=float(row.monthly_deposit_amount) if row.monthly_deposit_amount else None,
        retirement_target_year=row.retirement_target_year,
        user_email=current_user.email,
        notification_email=row.notification_email,
        auto_dca_enabled=row.auto_dca_enabled,
        auto_dca_day=row.auto_dca_day,
        auto_dca_amount=float(row.auto_dca_amount) if row.auto_dca_amount else None,
        auto_dca_portfolio_id=str(row.auto_dca_portfolio_id) if row.auto_dca_portfolio_id else None,
        auto_dca_account_id=str(row.auto_dca_account_id) if row.auto_dca_account_id else None,
        auto_dca_last_executed_at=row.auto_dca_last_executed_at.isoformat() if row.auto_dca_last_executed_at else None,
        annual_dividend_goal=float(row.annual_dividend_goal) if row.annual_dividend_goal else None,
        fcm_token_stored=bool(row.fcm_token),
        composite_signal_alerts_enabled=row.composite_signal_alerts_enabled,
        goal_candidate_tickers=[GoalCandidateTicker(**t) for t in (row.goal_candidate_tickers or [])],
        goal_risk_tolerance=(
            GoalRiskTolerance(row.goal_risk_tolerance) if row.goal_risk_tolerance else GoalRiskTolerance.CONSERVATIVE
        ),
        goal_max_weight_pct=float(row.goal_max_weight_pct) if row.goal_max_weight_pct else 40.0,
        goal_cagr_lookback_years=row.goal_cagr_lookback_years or 10,
        goal_short_term_equity_floor_pct=(
            float(row.goal_short_term_equity_floor_pct) if row.goal_short_term_equity_floor_pct else 80.0
        ),
    )


@router.put("/dart")
@limiter.limit("10/minute")
async def update_dart_api_key(
    request: Request,
    req: DartApiKeyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DART OpenAPI 키 저장."""
    row = await get_or_create_settings(db, current_user.id)
    row.dart_api_key = encrypt(req.api_key)
    await db.commit()
    return {"detail": "DART API 키가 저장되었습니다"}


@router.delete("/dart")
@limiter.limit("10/minute")
async def delete_dart_api_key(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await get_settings_row(db, current_user.id)
    if row:
        row.dart_api_key = None
        await db.commit()
    return {"detail": "DART API 키가 삭제되었습니다"}


@router.put("/goal")
@limiter.limit("20/minute")
async def update_goal(
    request: Request,
    req: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """투자 목표 설정."""
    row = await get_or_create_settings(db, current_user.id)
    if req.goal_amount is not None:
        row.goal_amount = req.goal_amount
    if req.goal_annual_return_pct is not None:
        row.goal_annual_return_pct = req.goal_annual_return_pct
    if req.annual_deposit_goal is not None:
        row.annual_deposit_goal = req.annual_deposit_goal
    if req.monthly_deposit_amount is not None:
        row.monthly_deposit_amount = req.monthly_deposit_amount
    if req.retirement_target_year is not None:
        row.retirement_target_year = req.retirement_target_year
    if req.goal_start_date is not None:
        from datetime import datetime

        row.goal_start_date = datetime.combine(req.goal_start_date, datetime.min.time()).replace(tzinfo=UTC)
    if req.goal_initial_amount is not None:
        row.goal_initial_amount = req.goal_initial_amount
    if req.annual_dividend_goal is not None:
        row.annual_dividend_goal = req.annual_dividend_goal
    await db.commit()
    redis = await get_redis()
    await invalidate_user_caches(redis, dashboard_summary_key(current_user.id))
    await invalidate_goal_recommendation_caches(redis, current_user.id)
    return {"detail": "목표가 저장되었습니다"}


@router.put("/goal-candidate-tickers")
@limiter.limit("20/minute")
async def update_goal_candidate_tickers(
    request: Request,
    req: GoalCandidateTickersUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표 역산 추천에 사용할 사용자 등록 후보 ETF 목록 저장(전체 교체)."""
    row = await get_or_create_settings(db, current_user.id)
    row.goal_candidate_tickers = [t.model_dump() for t in req.tickers]
    await db.commit()
    redis = await get_redis()
    await invalidate_goal_recommendation_caches(redis, current_user.id)
    return {"detail": "후보 ETF 목록이 저장되었습니다"}


@router.put("/goal-recommendation-options")
@limiter.limit("20/minute")
async def update_goal_recommendation_options(
    request: Request,
    req: GoalRecommendationOptionsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표 역산 추천 엔진의 리스크 성향/종목당 최대비중/CAGR 산출기간 설정(전체 교체)."""
    row = await get_or_create_settings(db, current_user.id)
    row.goal_risk_tolerance = req.risk_tolerance.value
    row.goal_max_weight_pct = req.max_weight_pct
    row.goal_cagr_lookback_years = req.cagr_lookback_years
    row.goal_short_term_equity_floor_pct = req.short_term_equity_floor_pct
    await db.commit()
    redis = await get_redis()
    await invalidate_goal_recommendation_caches(redis, current_user.id)
    return {"detail": "목표 역산 추천 설정이 저장되었습니다"}


@router.put("/notification-email")
@limiter.limit("10/minute")
async def update_notification_email(
    request: Request,
    req: NotificationEmailUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 수신 이메일 설정. 비워두면 로그인 이메일로 발송됩니다."""
    row = await get_or_create_settings(db, current_user.id)
    row.notification_email = req.notification_email or None
    await db.commit()
    return {"detail": "알림 이메일이 저장되었습니다"}


@router.put("/auto-dca")
@limiter.limit("10/minute")
async def update_auto_dca(
    request: Request,
    req: AutoDcaUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """자동 DCA 정기매수 설정."""
    row = await get_or_create_settings(db, current_user.id)
    row.auto_dca_enabled = req.enabled
    row.auto_dca_day = req.day
    row.auto_dca_amount = req.amount
    row.auto_dca_portfolio_id = uuid_mod.UUID(req.portfolio_id) if req.portfolio_id else None
    row.auto_dca_account_id = uuid_mod.UUID(req.account_id) if req.account_id else None
    await db.commit()
    return {"detail": "자동 정기매수 설정이 저장되었습니다"}


@router.put("/composite-signal-alerts")
@limiter.limit("10/minute")
async def update_composite_signal_alerts(
    request: Request,
    req: CompositeSignalAlertsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """시장/리스크 복합신호 알림(이메일·푸시) 수신 여부 — 신호가 유저 단위이므로 계정 단일 설정."""
    row = await get_or_create_settings(db, current_user.id)
    row.composite_signal_alerts_enabled = req.enabled
    await db.commit()
    return {"detail": "복합신호 알림 설정이 저장되었습니다"}


@router.put("/push-token")
@limiter.limit("10/minute")
async def update_push_token(
    request: Request,
    req: PushTokenUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FCM 푸시 알림 토큰 등록/삭제. fcm_token=null 전달 시 토큰 삭제."""
    row = await get_or_create_settings(db, current_user.id)
    row.fcm_token = req.fcm_token or None
    await db.commit()
    msg = "푸시 알림 토큰이 저장되었습니다" if req.fcm_token else "푸시 알림 토큰이 삭제되었습니다"
    return {"detail": msg}


@router.post("/test-email")
@limiter.limit("3/minute")
async def send_test_email_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 이메일 설정 확인용 테스트 이메일 발송."""
    from app.services.email_service import send_test_email

    row = await get_settings_row(db, current_user.id)
    to_email = (row.notification_email if row else None) or current_user.email

    try:
        sent = await send_test_email(to_email)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMTP가 설정되지 않았습니다. 서버 관리자에게 문의하세요",
        ) from e

    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이메일 발송에 실패했습니다",
        )

    return {"detail": f"{to_email}으로 테스트 이메일을 발송했습니다."}
