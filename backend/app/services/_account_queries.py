"""활성 계좌 조회 쿼리 헬퍼.

is_active == True 필터 누락이 자산 수배 부풀림의 핵심 원인 (CLAUDE.md 참고).
직접 is_active 조건을 작성하는 대신 이 헬퍼를 사용하면 누락 위험을 방지한다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount

_BROKER_ASSET_TYPES = ["STOCK_KIS", "STOCK_KIWOOM"]


def active_accounts_stmt(user_id: uuid.UUID) -> Select[tuple[AssetAccount]]:
    """user_id의 활성 계좌를 조회하는 SELECT 구문 반환."""
    return select(AssetAccount).where(
        AssetAccount.user_id == user_id,
        AssetAccount.is_active == True,  # noqa: E712
    )


def active_broker_accounts_stmt(user_id: uuid.UUID) -> Select[tuple[AssetAccount]]:
    """user_id의 활성 KIS/키움 연동 계좌를 조회하는 SELECT 구문 반환."""
    return active_accounts_stmt(user_id).where(AssetAccount.asset_type.in_(_BROKER_ASSET_TYPES))


async def get_account_including_inactive(
    db: AsyncSession, account_id: uuid.UUID, user_id: uuid.UUID
) -> AssetAccount | None:
    """비활성 계좌도 포함해 소유 계좌를 조회한다 (실시간 잔고 조회 등 일부 API에서 필요)."""
    return await db.scalar(
        select(AssetAccount).where(
            AssetAccount.id == account_id,
            AssetAccount.user_id == user_id,
        )
    )
