"""사용자 설정 및 증권사 자격증명 관리 API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.asset import AssetAccount
from app.models.user import User, UserSettings
from app.services.credential_service import decrypt, encrypt

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


class NotificationEmailUpdate(BaseModel):
    notification_email: str | None = None


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


@router.get("", response_model=SettingsResponse)
async def get_settings(
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
            has_open_banking=False, ob_token_expires_at=None,
            goal_amount=None, goal_annual_return_pct=None,
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
    )


@router.put("/dart")
async def update_dart_api_key(
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
async def delete_dart_api_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == current_user.id))
    if row:
        row.dart_api_key = None
        await db.commit()
    return {"detail": "DART API 키가 삭제되었습니다"}


@router.put("/goal")
async def update_goal(
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
        from datetime import datetime, timezone
        row.goal_start_date = datetime.combine(req.goal_start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    if req.goal_initial_amount is not None:
        row.goal_initial_amount = req.goal_initial_amount
    await db.commit()
    return {"detail": "목표가 저장되었습니다"}


@router.put("/notification-email")
async def update_notification_email(
    req: NotificationEmailUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 수신 이메일 설정. 비워두면 로그인 이메일로 발송됩니다."""
    row = await _get_or_create_settings(current_user.id, db)
    row.notification_email = req.notification_email or None
    await db.commit()
    return {"detail": "알림 이메일이 저장되었습니다"}


async def _get_or_create_settings(user_id, db: AsyncSession) -> UserSettings:
    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if not row:
        row = UserSettings(user_id=user_id)
        db.add(row)
        await db.flush()
    return row
