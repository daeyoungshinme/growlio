"""활성 계좌 조회 쿼리 헬퍼.

is_active == True 필터 누락이 자산 수배 부풀림의 핵심 원인 (CLAUDE.md 참고).
직접 is_active 조건을 작성하는 대신 이 헬퍼를 사용하면 누락 위험을 방지한다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select

from app.models.asset import AssetAccount


def active_accounts_stmt(user_id: uuid.UUID) -> Select[tuple[AssetAccount]]:
    """user_id의 활성 계좌를 조회하는 SELECT 구문 반환."""
    return select(AssetAccount).where(
        AssetAccount.user_id == user_id,
        AssetAccount.is_active == True,  # noqa: E712
    )


def active_accounts_filter() -> tuple:
    """is_active 단독 조건 튜플 — JOIN 쿼리에서 .where()에 스프레드할 때 사용."""
    return (AssetAccount.is_active == True,)  # noqa: E712
