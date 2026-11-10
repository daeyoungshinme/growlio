"""정액 적립 환전 대기 재확인 Job — 30분 간격(plans/120).

달러 부족으로 WAITING_FX가 된 해외 매수 leg를 미국장 중에 다시 확인해 달러가 충분해졌으면 매수 대기(PENDING)로
되돌린다(실행은 1분 매수 잡). 자동 재확인 기한이 지난 leg는 장 시간과 무관하게 만료로 마감한다.
"""

from __future__ import annotations

import structlog

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal
from app.services.rebalancing.plan_service import recheck_fx_waiting_legs

logger = structlog.get_logger()


async def run_dca_fx_wait_retry() -> None:
    cache = await get_cache_store()
    async with AsyncSessionLocal() as db:
        count = await recheck_fx_waiting_legs(db, cache)
        if count:
            logger.info("dca_fx_wait_retry_done", count=count)
