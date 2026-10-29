"""공통 스냅샷 서브쿼리 헬퍼."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.asset import AssetSnapshot


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
