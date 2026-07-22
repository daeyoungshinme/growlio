"""APScheduler job 공통 헬퍼."""

from __future__ import annotations

from collections.abc import Callable

import structlog

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal

logger = structlog.get_logger()


async def run_alert_job(
    service_func: Callable,
    job_name: str,
    *,
    needs_cache: bool = False,
) -> None:
    """알림 체크 job 공통 실행 패턴: DB 세션 생성 → 서비스 호출 → 오류 로깅."""
    cache = await get_cache_store() if needs_cache else None
    async with AsyncSessionLocal() as db:
        try:
            if cache is not None:
                await service_func(db, cache)
            else:
                await service_func(db)
        except Exception as e:
            logger.error(f"{job_name}_failed", error=str(e))
