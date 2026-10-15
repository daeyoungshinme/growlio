"""app_state(Postgres durable state) 만료 row 일일 청소 Job.

날짜가 들어간 dedup 키는 다음 날부터 다시 읽히지 않아 get_durable의 opportunistic 삭제가 일어나지
않는다 — 사용자·알림 수 × 일수만큼 쌓이므로 하루 한 번 만료 row를 지운다.
"""

from __future__ import annotations

import structlog

from app.core.database import AsyncSessionLocal
from app.utils.durable_state import purge_expired_durable

logger = structlog.get_logger()


async def run_app_state_sweep() -> None:
    async with AsyncSessionLocal() as db:
        removed = await purge_expired_durable(db)
    if removed:
        logger.info("app_state_sweep_done", removed=removed)
