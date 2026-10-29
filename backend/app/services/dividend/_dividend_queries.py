"""배당 서비스 DB 쿼리 헬퍼 — 순수 DB 접근만 담당한다."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import UserSettings
from app.services.accounts.credential_service import decrypt


async def fetch_dart_api_key(user_id: uuid.UUID, db: AsyncSession) -> str:
    """user_settings에서 DART API 키 조회 및 복호화. 없으면 config 기본값 사용."""
    row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))
    if row and row.dart_api_key:
        return decrypt(row.dart_api_key)
    return settings.dart_api_key
