"""알림 관련 DB 접근 — 이력 저장."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import AlertHistory


async def save_alert_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    alert_type: str,
    message: str,
) -> None:
    db.add(AlertHistory(user_id=user_id, alert_type=alert_type, message=message))
