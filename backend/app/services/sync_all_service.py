"""전체 계좌 동기화("전체 갱신")를 백그라운드로 처리하는 서비스.

프론트가 계좌 수만큼 동기 sync 요청을 병렬로 쏘면, 각 요청이 DB 커넥션 풀
슬롯을 외부 API 응답이 올 때까지 오래 점유해 다른 화면의 신규 쿼리가
커넥션을 못 받아 로딩이 길어지는 문제가 있었다. 이 서비스는 요청을 즉시
반환하고, 실제 동기화는 jobs/asset_sync.py의 세마포어 기반 배치 로직
(_sync_accounts)을 재사용해 백그라운드에서 처리한다 — 계좌별로 짧게
스코프된 세션을 쓰므로 요청 커넥션을 붙잡지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.core.redis_client import get_redis
from app.jobs.asset_sync import _sync_accounts
from app.models.asset import AssetAccount
from app.utils.cache_keys import TTL_SYNC_ALL_STATUS, get_cached_json, set_cached_json, sync_all_status_key
from app.utils.redis_lock import redis_lock

logger = structlog.get_logger()

_LOCK_TTL_SECONDS = 600


def _lock_key(user_id: uuid.UUID) -> str:
    return f"sync_all_lock:{user_id}"


async def get_sync_all_status(user_id: uuid.UUID) -> dict[str, Any]:
    """현재 유저의 "전체 갱신" 진행 상태를 조회한다. 기록이 없으면 idle."""
    redis = await get_redis()
    status = await get_cached_json(redis, sync_all_status_key(user_id))
    return status or {"status": "idle"}


async def is_sync_all_running(user_id: uuid.UUID) -> bool:
    """다른 "전체 갱신"이 이미 진행 중인지 확인한다 (락 존재 여부)."""
    redis = await get_redis()
    return bool(await redis.get(_lock_key(user_id)))


async def run_sync_all(user_id: uuid.UUID, accounts: list[AssetAccount]) -> None:
    """FastAPI BackgroundTasks에서 fire-and-forget으로 실행되는 배치 동기화 본체.

    락 획득~해제를 이 코루틴이 전 구간 소유한다 (요청-응답 생명주기와 독립적).
    """
    redis = await get_redis()
    status_key = sync_all_status_key(user_id)
    total = len(accounts)

    async with redis_lock(redis, _lock_key(user_id), ttl=_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            logger.info("sync_all_already_running", user_id=str(user_id))
            return

        await set_cached_json(
            redis,
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

        async def on_progress(done: int, total_: int) -> None:
            await set_cached_json(
                redis,
                status_key,
                {"status": "running", "total": total_, "done": done, "failed": 0},
                TTL_SYNC_ALL_STATUS,
            )

        try:
            failed = await _sync_accounts(accounts, "sync_all", on_progress=on_progress)
        except Exception as e:
            logger.error("sync_all_failed", user_id=str(user_id), error=str(e))
            await set_cached_json(
                redis,
                status_key,
                {"status": "error", "total": total, "done": 0, "failed": total},
                TTL_SYNC_ALL_STATUS,
            )
            return

        await set_cached_json(
            redis,
            status_key,
            {"status": "done", "total": total, "done": total, "failed": len(failed)},
            TTL_SYNC_ALL_STATUS,
        )
