"""사용자당 생성 상한(알림·추가 환전 항목) 판정 직렬화.

"개수 세기 → 상한 비교 → insert"는 동시 요청 둘이 같은 개수를 보고 둘 다 넣을 수 있다(plans/129 B3).
개수를 세기 전에 사용자 행을 `FOR NO KEY UPDATE`로 잠가 같은 사용자의 생성 판정을 commit/rollback까지 한 줄로 세운다.
`FOR UPDATE`는 users를 참조하는 행 INSERT의 `FOR KEY SHARE`(FK 확인)까지 막아, 알림 발동 잡(알림 UPDATE + 이력
INSERT)과 역순으로 기다리는 교착을 만들 수 있다(plans/132 B2). 상한 판정끼리는 NO KEY UPDATE로도 직렬화된다.
인스턴스·워커 수와 무관하게 DB가 보장한다(`inproc_lock`은 단일 프로세스 전제).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def lock_user_for_quota(db: AsyncSession, user_id: uuid.UUID) -> None:
    """같은 트랜잭션이 끝날 때까지 이 사용자의 다른 생성 상한 판정을 기다리게 한다. 개수를 세기 직전에 부른다."""
    from app.models.user import User

    await db.execute(select(User.id).where(User.id == user_id).with_for_update(key_share=True))
