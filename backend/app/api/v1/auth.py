import httpx
import sentry_sdk
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_token_payload
from app.core.cache_store import get_cache_store
from app.core.job_runner import report_handled_failure
from app.limiter import ip_rate_limit_key, limiter, peer_rate_limit_key
from app.models.asset import AssetAccount
from app.models.user import User, UserSettings
from app.schemas.auth import (
    AccountDeleteRequest,
    FindAccountRequest,
    FindAccountResponse,
    SyncProfileRequest,
    UserResponse,
)
from app.services.auth_service import delete_supabase_user, supabase_user_exists, verify_password
from app.utils.cache_keys import invalidate_all_user_caches, invalidate_user_caches
from app.utils.masking import mask_email

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
@limiter.limit("120/minute")
async def me(request: Request, current_user: User = Depends(get_current_user)):
    return current_user


async def _supabase_user_exists_or_503(user_id: str, *, event: str) -> bool:
    try:
        return await supabase_user_exists(user_id)
    except httpx.HTTPError as e:
        # Supabase Auth 장애는 HTTPException으로 바뀌어 Sentry 자동 수집에 안 잡힌다(plans/95 B)
        report_handled_failure(event, e, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="계정 확인에 실패했습니다. 잠시 후 다시 시도해주세요.",
        ) from e


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

    # 탈퇴 직후 다른 기기에 남은 access token(~1시간 유효, 서명만 검증됨)으로 호출되면 지운 계정이
    # 이메일과 함께 다시 생긴다 — 새 row를 만들기 전에 Supabase Auth에 실제로 있는 사용자인지 본다(plans/61 A5).
    if not await _supabase_user_exists_or_503(user_id, event="sync_profile_user_check_failed"):
        logger.warning("sync_profile_deleted_user", user_id=user_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="탈퇴했거나 존재하지 않는 계정입니다")

    # 탈퇴 처리 중 Supabase Auth 삭제는 성공했으나 로컬 DB 삭제가 실패해 남은 고아 row 정리.
    # (같은 이메일로 재가입 시 Supabase가 새 sub를 발급하므로 위 id 조회로는 찾을 수 없음)
    orphan = await db.scalar(select(User).where(User.email == email))
    if orphan:
        # 이메일만 보고 지우면, 같은 이메일이 다른 sub로 들어오는 경로(nestlio와 공유하는 Supabase의
        # 미연결 OAuth identity·이메일 확인 설정 변경 등)에서 살아 있는 사용자의 데이터가 CASCADE로
        # 지워진다. 옛 sub가 Supabase Auth에서 실제로 사라졌을 때만 고아로 보고 정리한다.
        still_exists = await _supabase_user_exists_or_503(str(orphan.id), event="sync_profile_orphan_check_failed")
        if still_exists:
            logger.error(
                "sync_profile_email_conflict",
                old_user_id=str(orphan.id),
                new_user_id=user_id,
                email=mask_email(email),
            )
            sentry_sdk.capture_message("sync_profile_email_conflict: live user shares email", level="error")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 다른 계정에서 사용 중인 이메일입니다. 고객센터로 문의해주세요.",
            )
        logger.warning(
            "sync_profile_orphan_email_cleanup",
            old_user_id=str(orphan.id),
            new_user_id=user_id,
            email=mask_email(email),
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


@router.post("/password-reset-complete", response_model=UserResponse)
@limiter.limit("10/minute")
async def password_reset_complete(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """비밀번호를 새로 설정했음을 기록한다 — 재설정 안내 배너(needs_password_reset)를 끈다.

    m1(Supabase Auth 전환)이 기존 유저를 TRUE로 채웠는데 DB에서 끄는 경로가 없어, 재설정을 마쳐도
    다음 /auth/me마다 배너가 다시 떴다. 비밀번호 변경 자체는 Supabase가 처리하므로 여기선 플래그만 바꾼다(멱등).
    """
    if current_user.needs_password_reset:
        current_user.needs_password_reset = False
        await db.commit()
    return current_user


@router.post("/find-account", response_model=FindAccountResponse)
@limiter.limit("3/hour", key_func=ip_rate_limit_key)
@limiter.limit("30/hour", key_func=peer_rate_limit_key)
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
    except httpx.HTTPError as e:
        report_handled_failure("account_delete_password_verify_unreachable", e)
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
        report_handled_failure("account_delete_supabase_failed", e, user_id=str(user_id))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="탈퇴 처리 중 오류가 발생했습니다. 다시 시도해주세요"
        ) from e

    try:
        await db.delete(current_user)
        await db.commit()
    except Exception as e:
        # Supabase 유저는 이미 삭제됐다 — 로컬 데이터가 고아로 남으므로 Sentry로 알린다
        report_handled_failure(
            "account_delete_local_cleanup_failed", e, user_id=str(user_id), email=mask_email(user_email)
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="탈퇴 처리 중 오류가 발생했습니다. 다시 시도해주세요"
        ) from e

    cache = await get_cache_store()
    for account_id in account_ids:
        await invalidate_user_caches(cache, f"kis_token:account:{account_id}", f"kiwoom_token:account:{account_id}")
    await invalidate_all_user_caches(cache, user_id)

    from app.services.notifications.email_service import send_account_deletion_email

    await send_account_deletion_email(user_email)

    logger.info("account_deleted", user_id=str(user_id))
