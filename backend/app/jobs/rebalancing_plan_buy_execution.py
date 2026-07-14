"""리밸런싱 매수 대기 플랜 실행 Job — 1분 간격, 대기시간이 지난 BUY leg를 자동 실행한다."""

from __future__ import annotations

import structlog

from app.database import AsyncSessionLocal
from app.redis_client import get_redis
from app.services.rebalancing.plan_service import execute_due_buy_legs
from app.utils.cache_keys import TTL_JOB_LOCK_REBALANCING_PLAN_BUY
from app.utils.market_hours import is_korean_market_open
from app.utils.redis_lock import redis_lock

logger = structlog.get_logger()


async def run_rebalancing_plan_buy_execution() -> None:
    """1분 간격 실행 — deadline_at이 지난 PENDING 매수 leg를 실행한다.

    buy_wait_minutes가 최소 1분까지 허용되므로, 5분 간격 잡이면 약속한 대기시간보다
    최대 5분 더 늦어질 수 있어 1분 간격으로 촘촘히 확인한다.
    """
    if not is_korean_market_open():
        return

    redis = await get_redis()
    async with redis_lock(
        redis, "rebalancing_plan_buy_execution_lock", ttl=TTL_JOB_LOCK_REBALANCING_PLAN_BUY
    ) as acquired:
        if not acquired:
            return
        async with AsyncSessionLocal() as db:
            count = await execute_due_buy_legs(db, redis)
            if count:
                logger.info("rebalancing_plan_buy_execution_done", count=count)
