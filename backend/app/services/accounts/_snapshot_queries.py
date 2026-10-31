"""공통 스냅샷 서브쿼리 헬퍼."""

from __future__ import annotations

import uuid
from collections.abc import Collection
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.asset import AssetAccount, AssetSnapshot


def latest_snapshot_subquery(
    *,
    user_id: uuid.UUID | None = None,
    account_ids: list | None = None,
):
    """account_id별 max(snapshot_date) 서브쿼리를 반환한다.

    - user_id: 특정 사용자의 모든 계좌를 기준으로 필터
    - account_ids: 특정 계좌 ID 목록을 기준으로 필터
    양쪽 모두 지정하면 AND 조건이 된다.
    """
    q = select(
        AssetSnapshot.account_id,
        func.max(AssetSnapshot.snapshot_date).label("max_date"),
    ).group_by(AssetSnapshot.account_id)
    if user_id is not None:
        q = q.where(AssetSnapshot.user_id == user_id)
    if account_ids is not None:
        q = q.where(AssetSnapshot.account_id.in_(account_ids))
    return q.subquery()


async def latest_snapshot_rows(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    account_ids: Collection[uuid.UUID] | None = None,
    asset_types: Collection[str] | None = None,
    with_positions: bool = False,
) -> list[Any]:
    """활성 계좌별 최신 스냅샷 `(AssetSnapshot, AssetAccount)` 행.

    - account_ids: 비어 있지 않으면 그 계좌만(빈 목록·None은 전체)
    - asset_types: 지정하면 그 자산 유형 계좌만
    - with_positions: `AssetSnapshot.position_items`를 함께 로드
    """
    subq = latest_snapshot_subquery(user_id=user_id)
    q = (
        select(AssetSnapshot, AssetAccount)
        .join(subq, (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(AssetAccount.is_active == True)
    )
    if asset_types is not None:
        q = q.where(AssetAccount.asset_type.in_(asset_types))
    if account_ids:
        q = q.where(AssetAccount.id.in_(account_ids))
    if with_positions:
        q = q.options(selectinload(AssetSnapshot.position_items))
    result = await db.execute(q)
    return list(result.all())
