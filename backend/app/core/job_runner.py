"""배치 작업(jobs·알림 서비스) 공용 실패 보고 + 유저별 실행 골격.

services는 jobs를 import할 수 없어(90 C5) jobs와 알림 서비스가 함께 쓰는 헬퍼를 core에 둔다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import TYPE_CHECKING

import sentry_sdk
import structlog

if TYPE_CHECKING:
    from app.models.user import User, UserSettings

logger = structlog.get_logger()


def report_job_failure(event: str, exc: BaseException, **context: str) -> None:
    """잡 실패 로그 + Sentry 전송.

    structlog는 stdlib logging을 거치지 않아(PrintLogger) Sentry LoggingIntegration이 잡 실패를
    잡지 못하고, 잡 함수가 예외를 삼키므로 APScheduler의 에러 로그도 남지 않는다 — 명시적으로
    capture한다(Sentry 미초기화 시 no-op). 로그 쪽은 redact 프로세서가 문자열만 마스킹하므로
    traceback(exc_info) 대신 error=str(e)만 남긴다. 자격증명을 지역변수로 다루는 잡(token_refresh)은
    Sentry 스택 로컬 전송을 피하려고 이 헬퍼를 쓰지 않고 스택 없는 capture_message를 쓴다
    (`token_refresh._report_refresh_failure`).
    """
    logger.error(event, error=str(exc), **context)
    sentry_sdk.capture_exception(exc)


async def run_per_user(
    rows: Iterable[tuple[User, UserSettings]],
    handle_user: Callable[[User, UserSettings, str], Awaitable[None]],
    *,
    concurrency: int,
    failure_event: str,
) -> None:
    """유저별 알림 잡 공통 골격: 동시성 제한 → 수신 이메일 결정 → 핸들러 → 실패는 유저 단위로 Sentry 보고.

    한 유저의 예외가 다른 유저 처리를 막지 않는다. DB 세션은 핸들러가 연다(유저마다 세션 수·시점이 다르다).
    `handle_user(user, settings_row, to_email)`의 `to_email`은 알림 수신 이메일(없으면 가입 이메일)이다.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(user: User, settings_row: UserSettings) -> None:
        async with sem:
            try:
                await handle_user(user, settings_row, settings_row.notification_email or user.email)
            except Exception as e:
                report_job_failure(failure_event, e, user_id=str(user.id))

    await asyncio.gather(*(_one(user, settings_row) for user, settings_row in rows))
