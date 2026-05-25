"""키움증권 REST API OAuth2 토큰 발급 — Redis 캐시 → DB → API 순으로 시도."""
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from app.kiwoom.constants import (
    KIWOOM_MOCK_BASE_URL,
    KIWOOM_REAL_BASE_URL,
    REDIS_KIWOOM_TOKEN_KEY,
    REDIS_TOKEN_TTL_BUFFER,
)

logger = structlog.get_logger()


async def get_access_token(
    app_key: str,
    app_secret: str,
    *,
    is_mock: bool,
    redis,
    db,
    user_id: str,
    account_id: str,
    force_refresh: bool = False,
) -> str:
    """키움 액세스 토큰 조회 — Redis 캐시 → DB → 키움 API 순으로 시도.

    키움은 전역 자격증명 없으므로 account_id는 항상 필수.
    """
    cache_key = REDIS_KIWOOM_TOKEN_KEY.format(account_id=account_id)

    if force_refresh:
        await redis.delete(cache_key)
        return await _fetch_and_store_token(
            app_key, app_secret, is_mock=is_mock, redis=redis, db=db,
            user_id=user_id, account_id=account_id,
        )

    # 1. Redis 캐시 확인
    cached = await redis.get(cache_key)
    if cached:
        return cached

    # 2. DB fallback
    from sqlalchemy import select

    from app.models.token import KiwoomToken

    result = await db.execute(
        select(KiwoomToken).where(
            KiwoomToken.account_id == account_id,
            KiwoomToken.expires_at > datetime.now(UTC),
        )
    )
    token_row = result.scalar_one_or_none()
    if token_row:
        elapsed = (token_row.expires_at - datetime.now(UTC)).total_seconds()
        ttl = int(elapsed - REDIS_TOKEN_TTL_BUFFER)
        if ttl > 0:
            await redis.setex(cache_key, ttl, token_row.access_token)
            return token_row.access_token

    # 3. 키움 API에서 신규 발급
    return await _fetch_and_store_token(
        app_key, app_secret, is_mock=is_mock, redis=redis, db=db,
        user_id=user_id, account_id=account_id,
    )


async def _fetch_and_store_token(
    app_key: str,
    app_secret: str,
    *,
    is_mock: bool,
    redis,
    db,
    user_id: str,
    account_id: str,
) -> str:
    base_url = KIWOOM_MOCK_BASE_URL if is_mock else KIWOOM_REAL_BASE_URL

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{base_url}/oauth2/token",
            json={"grant_type": "client_credentials", "appkey": app_key, "secretkey": app_secret},
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )
        if resp.status_code >= 400:
            try:
                err_body = resp.json()
            except Exception:
                err_body = resp.text
            logger.error(
                "kiwoom_token_http_error",
                status=resp.status_code,
                return_code=err_body.get("return_code") if isinstance(err_body, dict) else None,
                return_msg=err_body.get("return_msg") if isinstance(err_body, dict) else err_body,
                is_mock=is_mock,
                base_url=base_url,
            )
        resp.raise_for_status()
        data = resp.json()

    if str(data.get("return_code", "0")) != "0":
        raise RuntimeError(f"키움 토큰 발급 실패: {data.get('return_msg')}")

    access_token: str = data["token"]  # 키움은 token (표준 access_token 아님)

    # 키움 응답: expires_dt = "YYYY-MM-DD HH:MM:SS" 형식 문자열
    expires_dt_str: str | None = data.get("expires_dt")
    if expires_dt_str:
        expires_at = datetime.strptime(expires_dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    else:
        expires_at = datetime.now(UTC) + timedelta(seconds=86400)

    # Redis 캐시 저장
    cache_key = REDIS_KIWOOM_TOKEN_KEY.format(account_id=account_id)
    remaining = int((expires_at - datetime.now(UTC)).total_seconds())
    ttl = remaining - REDIS_TOKEN_TTL_BUFFER
    await redis.setex(cache_key, max(ttl, 60), access_token)

    # DB upsert (account_id unique 제약 기반)
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.token import KiwoomToken

    stmt = pg_insert(KiwoomToken).values(
        user_id=user_id,
        account_id=account_id,
        access_token=access_token,
        expires_at=expires_at,
        is_mock_mode=is_mock,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id"],
        set_={"access_token": access_token, "expires_at": expires_at},
    )
    await db.execute(stmt)
    await db.commit()

    logger.info("kiwoom_token_issued", account_id=account_id, is_mock=is_mock)
    return access_token
