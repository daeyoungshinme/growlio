"""APScheduler job 공통 헬퍼."""

from __future__ import annotations

from collections.abc import Callable

import sentry_sdk
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
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def report_job_failure(event: str, exc: BaseException, **context: str) -> None:
    """잡 실패 로그 + Sentry 전송.

    structlog는 stdlib logging을 거치지 않아(PrintLogger) Sentry LoggingIntegration이 잡 실패를
    잡지 못하고, 잡 함수가 예외를 삼키므로 APScheduler의 에러 로그도 남지 않는다 — 명시적으로
    capture한다(Sentry 미초기화 시 no-op). 로그 쪽은 redact 프로세서가 문자열만 마스킹하므로
    traceback(exc_info) 대신 error=str(e)만 남긴다. 자격증명을 지역변수로 다루는 잡(token_refresh)은
    Sentry 스택 로컬 전송을 피하려고 이 헬퍼를 쓰지 않는다.
    """
    logger.error(event, error=str(exc), **context)
    sentry_sdk.capture_exception(exc)


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
            report_job_failure(f"{job_name}_failed", e)
