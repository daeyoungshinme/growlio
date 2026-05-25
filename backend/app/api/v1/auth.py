import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.models.user import PasswordResetToken, User, UserSettings
from app.schemas.auth import (
    FindAccountRequest,
    FindAccountResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services.email_service import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    is_prod = settings.app_env == "production"
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.jwt_access_token_expire_minutes * 60,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 3600,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        path=_REFRESH_COOKIE_PATH,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path=_REFRESH_COOKIE_PATH)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def register(request: Request, req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == req.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 사용 중인 이메일입니다")

    user = User(email=req.email, hashed_password=hash_password(req.password), display_name=req.display_name)
    db.add(user)
    await db.flush()

    user_settings = UserSettings(user_id=user.id)
    db.add(user_settings)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=UserResponse)
@limiter.limit("5/minute")
async def login(request: Request, req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == req.email, User.is_active == True))  # noqa: E712
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="이메일 또는 비밀번호가 올바르지 않습니다")
    _set_auth_cookies(
        response,
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
    return user


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="리프레시 토큰이 없습니다")
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰입니다")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="잘못된 토큰 유형입니다")
    user_id = payload["sub"]
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active == True))  # noqa: E712
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다")
    _set_auth_cookies(
        response,
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response):
    _clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


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


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/hour")
async def forgot_password(request: Request, req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == req.email, User.is_active == True))  # noqa: E712
    if not user:
        return  # 이메일 존재 여부 노출 방지

    # 기존 미사용 토큰 무효화
    existing = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False,  # noqa: E712
        )
    )
    for token in existing.scalars().all():
        token.used = True

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(reset_token)
    await db.commit()

    reset_link = f"{settings.frontend_url}/reset-password?token={raw_token}"
    await send_password_reset_email(user.email, reset_link)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def reset_password(request: Request, req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hashlib.sha256(req.token.encode()).hexdigest()
    reset_token = await db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    if not reset_token or reset_token.used or reset_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="유효하지 않거나 만료된 링크입니다")

    user = await db.scalar(select(User).where(User.id == reset_token.user_id, User.is_active == True))  # noqa: E712
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="사용자를 찾을 수 없습니다")

    user.hashed_password = hash_password(req.new_password)
    reset_token.used = True
    await db.commit()
