import uuid
from typing import Annotated, Any

import structlog
from fastapi import Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.services.auth_service import verify_supabase_token

logger = structlog.get_logger()


def _extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return authorization.removeprefix("Bearer ").strip()


async def get_token_payload(
    authorization: str | None = Header(default=None),
) -> dict:
    """DB 조회 없이 Supabase JWT payload만 반환. sync-profile 같은 엔드포인트에서 사용."""
    token = _extract_token(authorization)
    try:
        return verify_supabase_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_token(authorization)
    try:
        payload = verify_supabase_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = await db.scalar(select(User).where(User.id == user_id, User.is_active == True))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    # 이 조회가 autobegin한 트랜잭션을 바로 끝내 커넥션을 풀에 돌려준다 — 안 그러면 요청이 끝날 때까지
    # (외부 API 대기 포함) 커넥션을 쥐고 있어, 콜드 스타트에 홈 요청 10여 개가 몰리면 풀(5+2)이 고갈돼
    # 나머지가 pool_timeout까지 줄을 섰다. 아직 쓰기 전이라 커밋할 내용이 없고, expire_on_commit=False라
    # user 속성도 그대로 쓸 수 있다. 이후 쿼리는 새 트랜잭션을 autobegin한다.
    await db.commit()
    return user


class PaginationParams(BaseModel):
    skip: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]


async def get_owned_or_404[T](
    db: AsyncSession,
    model: type[T],
    resource_id: Any,
    user_id: uuid.UUID,
    detail: str = "찾을 수 없습니다",
) -> T:
    """user_id 소유 리소스를 조회하고 없으면 404를 raise한다."""
    row: T | None = await db.scalar(
        select(model).where(model.id == resource_id, model.user_id == user_id)  # type: ignore[attr-defined, arg-type]
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return row
