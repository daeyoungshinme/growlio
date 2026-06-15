from typing import TypeVar
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount

_T = TypeVar("_T")


async def get_owned_or_404(
    db: AsyncSession,
    model: type[_T],
    resource_id: UUID,
    user_id: UUID,
    detail: str = "찾을 수 없습니다",
) -> _T:
    """model.id == resource_id AND model.user_id == user_id 조건으로 조회 후 없으면 404."""
    obj = await db.scalar(
        select(model).where(
            model.id == resource_id,  # type: ignore[attr-defined]
            model.user_id == user_id,  # type: ignore[attr-defined]
        )
    )
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return obj


async def get_owned_account(account_id: UUID, user_id, db: AsyncSession) -> AssetAccount:
    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.id == account_id,
            AssetAccount.user_id == user_id,
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다")
    return account
