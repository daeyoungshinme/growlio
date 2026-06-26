import uuid
from typing import Annotated, Any, TypeVar

import structlog
from fastapi import Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import verify_supabase_token

T = TypeVar("T")

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None  # noqa: E501


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_token(authorization)
    try:
        payload = verify_supabase_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from None  # noqa: E501

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")  # noqa: E501

    user = await db.scalar(select(User).where(User.id == user_id, User.is_active == True))  # noqa: E712
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


class PaginationParams(BaseModel):
    skip: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]


async def get_owned_or_404(
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
