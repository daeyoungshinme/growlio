"""금융결제원 오픈뱅킹 OAuth2 연동 API."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.user import User, UserSettings
from app.providers.openbanking import exchange_code_for_token, get_authorize_url, get_user_accounts
from app.redis_client import get_redis
from app.services.credential_service import decrypt, encrypt
from app.utils.cache_keys import TTL_OB_STATE, ob_state_key

logger = structlog.get_logger()

router = APIRouter(prefix="/open-banking", tags=["open-banking"])

_OB_TOKEN_DEFAULT_TTL = 90 * 24 * 3600  # 금융결제원 기본 토큰 유효기간 90일


@router.get("/connect")
@limiter.limit("10/minute")
async def connect_open_banking(
    request: Request,
    current_user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis),
):
    """오픈뱅킹 OAuth2 인증 시작 — 금융결제원 인증 페이지로 리다이렉트."""
    state = secrets.token_urlsafe(16)
    await redis.setex(ob_state_key(state), TTL_OB_STATE, str(current_user.id))
    redirect_url = get_authorize_url(state)
    return {"authorize_url": redirect_url}


@router.get("/callback")
@limiter.limit("20/minute")
async def open_banking_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """오픈뱅킹 OAuth2 콜백 — 토큰 교환 후 계좌 목록 저장."""
    user_id = await redis.getdel(ob_state_key(state))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="유효하지 않은 state 값입니다"
        )

    # state에 바인딩된 user_id가 실제로 DB에 존재하는지 검증
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.warning("ob_callback_invalid_user_id", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="유효하지 않은 state 값입니다"
        ) from None

    user_exists = await db.scalar(select(User).where(User.id == uid))
    if not user_exists:
        logger.warning("ob_callback_user_not_found", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="유효하지 않은 state 값입니다"
        )

    try:
        token_data = await exchange_code_for_token(code)
    except Exception as e:
        logger.error("ob_token_exchange_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="금융결제원 토큰 교환에 실패했습니다. 잠시 후 다시 시도해주세요.",
        ) from e
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    user_seq_no = token_data.get("user_seq_no")
    expires_in = int(token_data.get("expires_in", _OB_TOKEN_DEFAULT_TTL))

    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == uid))
    if not settings_row:
        settings_row = UserSettings(user_id=uid)
        db.add(settings_row)

    settings_row.ob_access_token = encrypt(access_token) if access_token else None
    settings_row.ob_refresh_token = encrypt(refresh_token) if refresh_token else None
    settings_row.ob_user_seq_no = user_seq_no
    settings_row.ob_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    await db.commit()

    # 프론트엔드로 리다이렉트 (연결 성공 페이지)
    return RedirectResponse(url=f"{settings.frontend_url}/settings?ob_connected=1")


@router.get("/accounts")
@limiter.limit("30/minute")
async def list_ob_accounts(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """오픈뱅킹으로 연결된 은행 계좌 목록 조회."""
    settings_row = await db.scalar(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    if not settings_row or not settings_row.ob_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="오픈뱅킹이 연결되지 않았습니다. /connect를 먼저 실행하세요.",
        )

    accounts = await get_user_accounts(
        access_token=decrypt(settings_row.ob_access_token),
        user_seq_no=settings_row.ob_user_seq_no or "",
    )
    return {
        "connected": True,
        "token_expires_at": settings_row.ob_token_expires_at,
        "accounts": accounts,
    }


@router.post("/accounts/register")
@limiter.limit("20/minute")
async def register_ob_account(
    request: Request,
    fintech_use_no: str,
    bank_code: str,
    bank_name: str,
    account_alias: str = "오픈뱅킹 계좌",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """오픈뱅킹 계좌를 자산 계좌로 등록."""
    # 이미 등록된 계좌인지 확인
    existing = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.user_id == current_user.id,
            AssetAccount.ob_fintech_use_no == fintech_use_no,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 등록된 계좌입니다")

    account = AssetAccount(
        user_id=current_user.id,
        name=account_alias,
        asset_type="BANK_ACCOUNT",
        data_source="OPEN_BANKING",
        institution=bank_name,
        ob_bank_code=bank_code,
        ob_fintech_use_no=fintech_use_no,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return {"id": str(account.id), "name": account.name, "institution": account.institution}


@router.delete("/disconnect")
@limiter.limit("10/minute")
async def disconnect_open_banking(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """오픈뱅킹 연결 해제."""
    settings_row = await db.scalar(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    if settings_row:
        settings_row.ob_access_token = None
        settings_row.ob_refresh_token = None
        settings_row.ob_token_expires_at = None
        settings_row.ob_user_seq_no = None
        await db.commit()
    return {"detail": "오픈뱅킹 연결이 해제되었습니다"}
