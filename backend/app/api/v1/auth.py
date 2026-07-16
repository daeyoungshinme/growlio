import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_token_payload
from app.core.redis_client import get_redis
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.user import User, UserSettings
from app.schemas.auth import (
    AccountDeleteRequest,
    FindAccountRequest,
    FindAccountResponse,
    SyncProfileRequest,
    UserResponse,
)
from app.services.auth_service import delete_supabase_user, verify_password
from app.utils.cache_keys import invalidate_all_user_caches, invalidate_user_caches

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
@limiter.limit("120/minute")
async def me(request: Request, current_user: User = Depends(get_current_user)):
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

    # 탈퇴 처리 중 Supabase Auth 삭제는 성공했으나 로컬 DB 삭제가 실패해 남은 고아 row 정리.
    # (같은 이메일로 재가입 시 Supabase가 새 sub를 발급하므로 위 id 조회로는 찾을 수 없음)
    orphan = await db.scalar(select(User).where(User.email == email))
    if orphan:
        logger.warning(
            "sync_profile_orphan_email_cleanup",
            old_user_id=str(orphan.id),
            new_user_id=user_id,
            email=email,
        )
        await db.delete(orphan)
        await db.flush()

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


@router.post("/account/delete", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/hour")
async def delete_account(
    request: Request,
    req: AccountDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """회원 탈퇴. 비밀번호 재인증 후 Supabase Auth 유저와 로컬 데이터를 전부 삭제한다.

    로컬 데이터는 user_id FK의 ondelete=CASCADE로 자동 정리된다.
    """
    try:
        password_ok = await verify_password(current_user.email, req.password)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.error("account_delete_password_verify_unreachable", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="인증 서버에 연결할 수 없습니다"
        ) from e
    if not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="비밀번호가 올바르지 않습니다")

    user_id = current_user.id
    user_email = current_user.email
    account_ids = (await db.execute(select(AssetAccount.id).where(AssetAccount.user_id == user_id))).scalars().all()

    try:
        await delete_supabase_user(str(user_id))
    except httpx.HTTPError as e:
        logger.error("account_delete_supabase_failed", user_id=str(user_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="탈퇴 처리 중 오류가 발생했습니다. 다시 시도해주세요"
        ) from e

    try:
        await db.delete(current_user)
        await db.commit()
    except Exception as e:
        logger.critical("account_delete_local_cleanup_failed", user_id=str(user_id), email=user_email, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="탈퇴 처리 중 오류가 발생했습니다. 다시 시도해주세요"
        ) from e

    redis = await get_redis()
    for account_id in account_ids:
        await invalidate_user_caches(redis, f"kis_token:account:{account_id}", f"kiwoom_token:account:{account_id}")
    await invalidate_all_user_caches(redis, user_id)

    from app.services.email_service import send_account_deletion_email

    await send_account_deletion_email(user_email)

    logger.info("account_deleted", user_id=str(user_id))
