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


@router.post("/sync-profile", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def sync_profile(
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


def _mask_email(email: str) -> str:
    local, domain = email.rsplit("@", 1)
    masked = local[0] + "***" if len(local) > 1 else local
    return f"{masked}@{domain}"


@router.post("/find-account", response_model=FindAccountResponse)
@limiter.limit("5/minute")
async def find_account(request: Request, req: FindAccountRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.display_name == req.display_name, User.is_active == True)  # noqa: E712
    )
    users = result.scalars().all()
    return FindAccountResponse(masked_emails=[_mask_email(u.email) for u in users])
