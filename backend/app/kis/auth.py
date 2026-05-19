from datetime import datetime, timedelta, timezone

import httpx
import structlog

from app.kis.constants import KIS_MOCK_BASE_URL, KIS_REAL_BASE_URL, REDIS_TOKEN_KEY, REDIS_TOKEN_TTL_BUFFER

logger = structlog.get_logger()


async def get_access_token(
    app_key: str,
    app_secret: str,
    *,
    is_mock: bool,
    redis,
    db,
    user_id: str,
    force_refresh: bool = False,
) -> str:
    """KIS 액세스 토큰 조회 — Redis 캐시 → DB → KIS API 순으로 시도."""
    cache_key = REDIS_TOKEN_KEY.format(user_id=user_id, mode="mock" if is_mock else "real")

    if force_refresh:
        await redis.delete(cache_key)
        return await _fetch_and_store_token(app_key, app_secret, is_mock=is_mock, redis=redis, db=db, user_id=user_id)

    # 1. Redis 캐시 확인
    cached = await redis.get(cache_key)
    if cached:
        return cached

    # 2. DB fallback
    from sqlalchemy import select

    from app.models.token import KisToken

    result = await db.execute(
        select(KisToken).where(
            KisToken.user_id == user_id,
            KisToken.is_mock_mode == is_mock,
            KisToken.expires_at > datetime.now(timezone.utc),
        )
    )
    token_row = result.scalar_one_or_none()
    if token_row:
        ttl = int((token_row.expires_at - datetime.now(timezone.utc)).total_seconds() - REDIS_TOKEN_TTL_BUFFER)
        if ttl > 0:
            await redis.setex(cache_key, ttl, token_row.access_token)
            return token_row.access_token

    # 3. KIS API에서 신규 발급
    return await _fetch_and_store_token(app_key, app_secret, is_mock=is_mock, redis=redis, db=db, user_id=user_id)


async def _fetch_and_store_token(
    app_key: str,
    app_secret: str,
    *,
    is_mock: bool,
    redis,
    db,
    user_id: str,
) -> str:
    base_url = KIS_MOCK_BASE_URL if is_mock else KIS_REAL_BASE_URL
    async with httpx.AsyncClient(timeout=30.0, verify=not is_mock) as client:
        resp = await client.post(
            f"{base_url}/oauth2/tokenP",
            json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
        )
        resp.raise_for_status()
        data = resp.json()

    access_token: str = data["access_token"]
    expires_in: int = int(data.get("expires_in", 86400))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Redis 캐시 저장
    cache_key = REDIS_TOKEN_KEY.format(user_id=user_id, mode="mock" if is_mock else "real")
    ttl = expires_in - REDIS_TOKEN_TTL_BUFFER
    await redis.setex(cache_key, max(ttl, 60), access_token)

    # DB upsert
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.token import KisToken

    stmt = pg_insert(KisToken).values(
        user_id=user_id,
        access_token=access_token,
        expires_at=expires_at,
        is_mock_mode=is_mock,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_kis_token_user_mode",
        set_={"access_token": access_token, "expires_at": expires_at},
    )
    await db.execute(stmt)
    await db.commit()

    logger.info("kis_token_issued", user_id=user_id, is_mock=is_mock)
    return access_token
