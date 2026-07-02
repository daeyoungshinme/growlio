"""환율/주가 알림 라우터 공용 reactivate·delete 엔드포인트 팩토리.

두 라우터의 list/create는 스키마(target_rate vs target_price 등)가 달라 그대로 두고,
구조가 완전히 동일한 reactivate/delete만 제네릭화한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._account_deps import get_owned_or_404
from app.limiter import limiter
from app.models.user import User

InvalidateCache = Callable[[uuid.UUID], Awaitable[None]]


def register_alert_reactivate_delete(
    router: APIRouter,
    *,
    path_prefix: str,
    model: type[Any],
    response_model: type[BaseModel],
    not_found_msg: str = "알림을 찾을 수 없습니다",
    invalidate_cache: InvalidateCache | None = None,
    rate_limit: str = "20/minute",
) -> None:
    """`{path_prefix}/{{alert_id}}/reactivate`(PATCH), `{path_prefix}/{{alert_id}}`(DELETE) 등록."""

    @limiter.limit(rate_limit)
    async def reactivate(
        request: Request,
        alert_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        alert = await get_owned_or_404(db, model, alert_id, current_user.id, not_found_msg)
        alert.is_active = True
        alert.trigger_count = 0
        await db.commit()
        await db.refresh(alert)
        if invalidate_cache:
            await invalidate_cache(current_user.id)
        return response_model.model_validate(alert)

    @limiter.limit(rate_limit)
    async def delete(
        request: Request,
        alert_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        alert = await get_owned_or_404(db, model, alert_id, current_user.id, not_found_msg)
        await db.delete(alert)
        await db.commit()
        if invalidate_cache:
            await invalidate_cache(current_user.id)

    router.patch(f"{path_prefix}/{{alert_id}}/reactivate", response_model=response_model)(reactivate)
    router.delete(f"{path_prefix}/{{alert_id}}", status_code=status.HTTP_204_NO_CONTENT)(delete)
