"""사용자 설정(UserSettings) 조회 쿼리 헬퍼."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount
from app.models.user import UserSettings


async def get_settings_row(db: AsyncSession, user_id: uuid.UUID) -> UserSettings | None:
    return await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))


async def get_or_create_settings(db: AsyncSession, user_id: uuid.UUID) -> UserSettings:
    row = await get_settings_row(db, user_id)
    if not row:
        row = UserSettings(user_id=user_id)
        db.add(row)
        await db.flush()
    return row


async def has_active_kis_credentials(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """자격증명이 설정된 활성 KIS 계좌 존재 여부."""
    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.user_id == user_id,
            AssetAccount.data_source == "KIS_API",
            AssetAccount.is_active == True,  # noqa: E712
            AssetAccount.kis_app_key != None,  # noqa: E711
        )
    )
    return account is not None
