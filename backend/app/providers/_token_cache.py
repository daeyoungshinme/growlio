"""브로커 API 공통 토큰 캐시 헬퍼 — in-memory 캐시 → DB fallback → API 신규 발급 순으로 조회.

KIS/Kiwoom/토스 모두 이 3단계 흐름을 독립적으로 구현하고 있었던 것을 공용화한 것.
브로커별 DB 조회 조건(계좌 단독 vs 유저+모드 복합)과 토큰 발급 응답 파싱은
호출부가 클로저(`query_token_row`/`fetch`)로 주입한다. 발급 직후 저장(캐시 setex + DB 암호화 upsert)은
`store_token`으로 공용화했다 — 브로커별로 다른 건 모델·upsert 충돌 대상·추가 컬럼뿐이다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.constants import TOKEN_CACHE_TTL_BUFFER
from app.services.credential_service import decrypt, encrypt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

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
            try:
                plaintext_token = decrypt(token_row.access_token)
            except ValueError:
                # 암호화 적용 이전에 평문으로 저장된 레거시 row — 캐시 미스로 간주하고 새로 발급
                plaintext_token = None
            if plaintext_token is not None:
                await cache.setex(cache_key, ttl, plaintext_token)
                return plaintext_token

    return await fetch()


async def store_token(
    cache: CacheStore,
    db: AsyncSession,
    *,
    cache_key: str,
    access_token: str,
    expires_at: datetime,
    model: Any,
    values: dict[str, Any],
    index_elements: list[str],
    index_where: Any = None,
) -> None:
    """새로 발급받은 토큰을 캐시(평문)와 DB(암호문 upsert)에 저장한다.

    `values`는 access_token/expires_at을 뺀 insert 컬럼(user_id, account_id, is_mock_mode 등).
    충돌 시 access_token/expires_at만 갱신한다. commit까지 수행한다.
    """
    remaining = int((expires_at - datetime.now(UTC)).total_seconds())
    await cache.setex(cache_key, max(remaining - TOKEN_CACHE_TTL_BUFFER, 60), access_token)

    encrypted_token = encrypt(access_token)
    stmt = pg_insert(model).values(**values, access_token=encrypted_token, expires_at=expires_at)
    stmt = stmt.on_conflict_do_update(
        index_elements=index_elements,
        index_where=index_where,
        set_={"access_token": encrypted_token, "expires_at": expires_at},
    )
    await db.execute(stmt)
    await db.commit()
