"""키움증권 REST API OAuth2 토큰 발급 — 캐시 → DB → API 순으로 시도."""

import json
from datetime import UTC, datetime, timedelta

import structlog

from app.constants import TOKEN_CACHE_TTL_BUFFER
from app.kiwoom.constants import (
    KIWOOM_MOCK_BASE_URL,
    KIWOOM_REAL_BASE_URL,
    KIWOOM_TOKEN_CACHE_KEY,
)
from app.providers._token_cache import get_or_fetch_token
from app.providers.http_client import _get_client

logger = structlog.get_logger()


async def get_access_token(
    app_key: str,
    app_secret: str,
    *,
    is_mock: bool,
    cache,
    db,
    user_id: str,
    account_id: str,
    force_refresh: bool = False,
) -> str:
    """키움 액세스 토큰 조회 — 캐시 → DB → 키움 API 순으로 시도.

    키움은 전역 자격증명 없으므로 account_id는 항상 필수.
    """
    cache_key = KIWOOM_TOKEN_CACHE_KEY.format(account_id=account_id)

    async def _query_token_row():
        from sqlalchemy import select

        from app.models.token import KiwoomToken

        result = await db.execute(
            select(KiwoomToken).where(
                KiwoomToken.account_id == account_id,
                KiwoomToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def _fetch():
        return await _fetch_and_store_token(
            app_key,
            app_secret,
            is_mock=is_mock,
            cache=cache,
            db=db,
            user_id=user_id,
            account_id=account_id,
        )

    return await get_or_fetch_token(cache_key, cache, force_refresh, TOKEN_CACHE_TTL_BUFFER, _query_token_row, _fetch)


async def _fetch_and_store_token(
    app_key: str,
    app_secret: str,
    *,
    is_mock: bool,
    cache,
    db,
    user_id: str,
    account_id: str,
) -> str:
    base_url = KIWOOM_MOCK_BASE_URL if is_mock else KIWOOM_REAL_BASE_URL

    client = _get_client(ssl_verify=True)
    resp = await client.post(
        f"{base_url}/oauth2/token",
        json={"grant_type": "client_credentials", "appkey": app_key, "secretkey": app_secret},
        headers={"Content-Type": "application/json;charset=UTF-8"},
    )
    if resp.status_code >= 400:
        try:
            err_body = resp.json()
        except (ValueError, json.JSONDecodeError):
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

    # 키움 응답: expires_dt = "YYYYMMDDHHMMSS" 형식 문자열 (구분자 없음)
    expires_dt_str: str | None = data.get("expires_dt")
    if expires_dt_str:
        expires_at = datetime.strptime(expires_dt_str, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    else:
        expires_at = datetime.now(UTC) + timedelta(seconds=86400)

    # 캐시 저장
    cache_key = KIWOOM_TOKEN_CACHE_KEY.format(account_id=account_id)
    remaining = int((expires_at - datetime.now(UTC)).total_seconds())
    ttl = remaining - TOKEN_CACHE_TTL_BUFFER
    await cache.setex(cache_key, max(ttl, 60), access_token)

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
