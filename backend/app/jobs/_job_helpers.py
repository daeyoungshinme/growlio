"""APScheduler job 공통 헬퍼."""

from __future__ import annotations

from collections.abc import Callable

import structlog

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal

logger = structlog.get_logger()


def peak_rss_mb() -> float | None:
    """프로세스 시작 이후 최고 상주 메모리(peak RSS, MB)를 반환한다.

    무거운 배치 잡(`asset_sync.py`의 전체 계좌 동기화 등) 전후로 로그에 남겨, 다음 Render 메모리
    알림 때 어느 잡이 급증을 유발했는지 바로 추적할 수 있게 한다. `resource` 모듈은 POSIX 전용이라
    Windows 로컬 개발 환경에서는 None을 반환한다 — 프로덕션(Linux 컨테이너)에서만 유효한 값이 남는다.
    """
    try:
        import resource
    except ImportError:
        return None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # type: ignore[attr-defined]


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
