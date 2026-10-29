"""전체 계좌 동기화("전체 갱신")를 백그라운드로 처리하는 서비스.

프론트가 계좌 수만큼 동기 sync 요청을 병렬로 쏘면, 각 요청이 DB 커넥션 풀
슬롯을 외부 API 응답이 올 때까지 오래 점유해 다른 화면의 신규 쿼리가
커넥션을 못 받아 로딩이 길어지는 문제가 있었다. 이 서비스는 요청을 즉시
반환하고, 실제 동기화는 세마포어 기반 배치 로직(`sync_accounts` — 15:30/18:00
스냅샷 잡도 재사용)으로 백그라운드에서 처리한다 — 계좌별로 짧게 스코프된
세션을 쓰므로 요청 커넥션을 붙잡지 않는다.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal
from app.core.logging import format_sync_error
from app.models.asset import AssetAccount
from app.services.asset_service import sync_account
from app.utils.cache_keys import TTL_SYNC_ALL_STATUS, get_cached_json, set_cached_json, sync_all_status_key
from app.utils.inproc_lock import inproc_lock

logger = structlog.get_logger()

_LOCK_TTL_SECONDS = 600
_ACCOUNT_SYNC_CONCURRENCY = 3

ProgressCallback = Callable[[int, int, int], Awaitable[None]]


async def sync_accounts(
    accounts: list[AssetAccount],
    job_name: str,
    on_progress: ProgressCallback | None = None,
) -> list[tuple[str, str, str]]:
    """세마포어(3)로 동시성을 제한하며 계좌들을 동기화한다.

    각 계좌는 자신만의 짧게 스코프된 AsyncSessionLocal을 열어서 사용하므로,
    이 함수를 호출하는 쪽의 요청 DB 커넥션을 오래 붙잡지 않는다.
    """
    cache = await get_cache_store()
    failed: list[tuple[str, str, str]] = []
    sem = asyncio.Semaphore(_ACCOUNT_SYNC_CONCURRENCY)
    done_count = 0
    progress_lock = asyncio.Lock()

    async def sync_one(account: AssetAccount) -> None:
        nonlocal done_count
        async with sem:
            try:
                async with AsyncSessionLocal() as db:
                    # account는 이 함수 호출 전 다른(이미 닫힌) 세션에서 조회되어 detached 상태이므로,
                    # merge로 새 세션에 편입해야 sync_account() 내부의 account.deposit_krw 등
                    # 속성 변경이 commit 시 실제로 반영된다.
                    merged_account = await db.merge(account)
                    await sync_account(merged_account, db, cache)
                logger.info("account_synced", job=job_name, account_id=str(account.id), name=account.name)
            except Exception as e:
                logger.error(
                    "account_sync_failed",
                    job=job_name,
                    account_id=str(account.id),
                    name=account.name,
                    error=str(e),
                )
                failed.append((str(account.id), account.name, str(e)))
        if on_progress:
            async with progress_lock:
                done_count += 1
                await on_progress(done_count, len(accounts), len(failed))

    await asyncio.gather(*(sync_one(account) for account in accounts))

    if failed:
        logger.warning(
            f"{job_name}_partial_failure",
            total=len(accounts),
            failed=len(failed),
            failed_accounts=[{"id": fid, "name": fname} for fid, fname, _ in failed],
        )

    return failed


def _lock_key(user_id: uuid.UUID) -> str:
    return f"sync_all_lock:{user_id}"


async def get_sync_all_status(user_id: uuid.UUID) -> dict[str, Any]:
    """현재 유저의 "전체 갱신" 진행 상태를 조회한다. 기록이 없으면 idle."""
    cache = await get_cache_store()
    status = await get_cached_json(cache, sync_all_status_key(user_id))
    return status or {"status": "idle"}


async def is_sync_all_running(user_id: uuid.UUID) -> bool:
    """다른 "전체 갱신"이 이미 진행 중인지 확인한다 (락 존재 여부)."""
    cache = await get_cache_store()
    return bool(await cache.get(_lock_key(user_id)))


async def run_sync_all(user_id: uuid.UUID, accounts: list[AssetAccount]) -> None:
    """FastAPI BackgroundTasks에서 fire-and-forget으로 실행되는 배치 동기화 본체.

    락 획득~해제를 이 코루틴이 전 구간 소유한다 (요청-응답 생명주기와 독립적).
    """
    cache = await get_cache_store()
    status_key = sync_all_status_key(user_id)
    total = len(accounts)

    async with inproc_lock(cache, _lock_key(user_id), ttl=_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            logger.info("sync_all_already_running", user_id=str(user_id))
            return

        await set_cached_json(
            cache,
            status_key,
            {
                "status": "running",
                "total": total,
                "done": 0,
                "failed": 0,
                "started_at": datetime.now(UTC).isoformat(),
            },
            TTL_SYNC_ALL_STATUS,
        )

        async def on_progress(done: int, total_: int, failed_count: int) -> None:
            await set_cached_json(
                cache,
                status_key,
                {"status": "running", "total": total_, "done": done, "failed": failed_count},
                TTL_SYNC_ALL_STATUS,
            )

        try:
            failed = await sync_accounts(accounts, "sync_all", on_progress=on_progress)
        except Exception as e:
            logger.error("sync_all_failed", user_id=str(user_id), error=str(e))
            await set_cached_json(
                cache,
                status_key,
                {
                    "status": "error",
                    "total": total,
                    "done": 0,
                    "failed": total,
                    "failed_accounts": [],
                    "error": format_sync_error(e),
                },
                TTL_SYNC_ALL_STATUS,
            )
            return

        failed_accounts = [
            {
                "account_id": fid,
                "account_name": fname,
                "error": format_sync_error(ferr),
            }
            for fid, fname, ferr in failed
        ]
        await set_cached_json(
            cache,
            status_key,
            {
                "status": "done",
                "total": total,
                "done": total,
                "failed": len(failed),
                "failed_accounts": failed_accounts,
            },
            TTL_SYNC_ALL_STATUS,
        )
