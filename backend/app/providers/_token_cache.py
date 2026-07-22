"""브로커 API 공통 토큰 캐시 헬퍼 — in-memory 캐시 → DB fallback → API 신규 발급 순으로 조회.

KIS/Kiwoom 모두 이 3단계 흐름을 독립적으로 구현하고 있었던 것을 공용화한 것.
브로커별 DB 조회 조건(계좌 단독 vs 유저+모드 복합)과 토큰 발급 응답 파싱은
호출부가 클로저(`query_token_row`/`fetch`)로 주입한다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.core.cache_store import CacheStore


class _TokenRow(Protocol):
    access_token: str
    expires_at: datetime


async def get_or_fetch_token(
    cache_key: str,
    cache: CacheStore,
    force_refresh: bool,
    ttl_buffer: int,
    query_token_row: Callable[[], Awaitable[_TokenRow | None]],
    fetch: Callable[[], Awaitable[str]],
) -> str:
    """캐시 키 기준으로 in-memory 캐시 → DB → 신규 발급 순서로 액세스 토큰을 반환한다."""
    if force_refresh:
        await cache.delete(cache_key)
        return await fetch()

    cached = await cache.get(cache_key)
    if cached:
        return cached

    token_row = await query_token_row()
    if token_row:
        elapsed = (token_row.expires_at - datetime.now(UTC)).total_seconds()
        ttl = int(elapsed - ttl_buffer)
        if ttl > 0:
            await cache.setex(cache_key, ttl, token_row.access_token)
            return token_row.access_token

    return await fetch()
