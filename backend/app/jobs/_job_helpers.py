"""APScheduler job 공통 헬퍼."""

from __future__ import annotations

from collections.abc import Callable

import structlog

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis

logger = structlog.get_logger()


async def run_alert_job(
    service_func: Callable,
    job_name: str,
    *,
    needs_redis: bool = False,
) -> None:
    """알림 체크 job 공통 실행 패턴: DB 세션 생성 → 서비스 호출 → 오류 로깅."""
    redis = await get_redis() if needs_redis else None
    async with AsyncSessionLocal() as db:
        try:
            if redis is not None:
                await service_func(db, redis)
            else:
                await service_func(db)
        except Exception as e:
            logger.error(f"{job_name}_failed", error=str(e))
