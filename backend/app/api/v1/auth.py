from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_token_payload
from app.database import get_db
from app.limiter import limiter
from app.models.user import User, UserSettings
from app.schemas.auth import (
    FindAccountRequest,
    FindAccountResponse,
    SyncProfileRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/sync-profile", response_model=UserResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def sync_profile(
    request: Request,
    req: SyncProfileRequest,
    payload: dict = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
):
    """Supabase 회원가입 후 앱 DB에 users + user_settings 행 생성. 멱등 (이미 있으면 기존 반환)."""
    user_id = payload.get("sub")
    email = payload.get("email")
    if not user_id or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    existing = await db.scalar(select(User).where(User.id == user_id))
    if existing:
        return existing

    user = User(
        id=user_id,
        email=email,
        display_name=req.display_name,
        needs_password_reset=False,
    )
    db.add(user)
    await db.flush()

    db.add(UserSettings(user_id=user.id))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/find-account", response_model=FindAccountResponse)
@limiter.limit("3/hour")
async def find_account(request: Request, req: FindAccountRequest):
    # 계정 존재 여부를 응답에서 노출하지 않음 (사용자 열거 방지)
    msg = "가입 시 사용하신 이름과 이메일로 로그인을 시도해 보세요."
    return FindAccountResponse(message=msg)
