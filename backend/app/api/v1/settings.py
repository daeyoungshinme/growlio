"""사용자 설정 및 증권사 자격증명 관리 API."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.user import User, UserSettings
from app.services.credential_service import encrypt

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

    @field_validator("goal_amount", "annual_deposit_goal", "goal_initial_amount", "monthly_deposit_amount")
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


class SettingsResponse(BaseModel):
    has_kis: bool
    has_dart: bool
    has_open_banking: bool
    ob_token_expires_at: str | None
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
    fcm_token_stored: bool = False


@router.get("", response_model=SettingsResponse)
@limiter.limit("30/minute")
async def get_settings(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 설정 조회 (자격증명 원문은 반환하지 않음)."""
    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == current_user.id))

    # has_kis: 자격증명이 설정된 활성 KIS 계좌 존재 여부
    kis_account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.user_id == current_user.id,
            AssetAccount.data_source == "KIS_API",
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.kis_app_key != None,  # noqa: E711
        )
    )
    has_kis = kis_account is not None

    if not row:
        return SettingsResponse(
            has_kis=has_kis,
            has_dart=False,
            has_open_banking=False,
            ob_token_expires_at=None,
            goal_amount=None,
            goal_annual_return_pct=None,
            annual_deposit_goal=None,
            user_email=current_user.email,
            notification_email=None,
        )
    return SettingsResponse(
        has_kis=has_kis,
        has_dart=bool(row.dart_api_key),
        has_open_banking=bool(row.ob_access_token),
        ob_token_expires_at=row.ob_token_expires_at.isoformat() if row.ob_token_expires_at else None,
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
        fcm_token_stored=bool(row.fcm_token),
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
    row = await _get_or_create_settings(current_user.id, db)
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
    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == current_user.id))
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
    row = await _get_or_create_settings(current_user.id, db)
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
    await db.commit()
    return {"detail": "목표가 저장되었습니다"}


@router.put("/notification-email")
@limiter.limit("10/minute")
async def update_notification_email(
    request: Request,
    req: NotificationEmailUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 수신 이메일 설정. 비워두면 로그인 이메일로 발송됩니다."""
    row = await _get_or_create_settings(current_user.id, db)
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
    row = await _get_or_create_settings(current_user.id, db)
    row.auto_dca_enabled = req.enabled
    row.auto_dca_day = req.day
    row.auto_dca_amount = req.amount
    row.auto_dca_portfolio_id = uuid_mod.UUID(req.portfolio_id) if req.portfolio_id else None
    row.auto_dca_account_id = uuid_mod.UUID(req.account_id) if req.account_id else None
    await db.commit()
    return {"detail": "자동 정기매수 설정이 저장되었습니다"}


@router.put("/push-token")
@limiter.limit("10/minute")
async def update_push_token(
    request: Request,
    req: PushTokenUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FCM 푸시 알림 토큰 등록/삭제. fcm_token=null 전달 시 토큰 삭제."""
    row = await _get_or_create_settings(current_user.id, db)
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

    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == current_user.id))
    to_email = (row.notification_email if row else None) or current_user.email

    try:
        await send_test_email(to_email)
    except RuntimeError as e:
        if "smtp_not_configured" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SMTP가 설정되지 않았습니다. 서버 관리자에게 문의하세요",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이메일 발송에 실패했습니다",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이메일 발송에 실패했습니다",
        ) from e

    return {"detail": f"{to_email}으로 테스트 이메일을 발송했습니다."}


async def _get_or_create_settings(user_id, db: AsyncSession) -> UserSettings:
    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if not row:
        row = UserSettings(user_id=user_id)
        db.add(row)
        await db.flush()
    return row
