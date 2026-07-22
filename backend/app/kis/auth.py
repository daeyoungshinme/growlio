from datetime import UTC, datetime, timedelta

import structlog

from app.constants import TOKEN_CACHE_TTL_BUFFER
from app.exceptions import ProviderTokenError
from app.kis.constants import (
    KIS_MOCK_BASE_URL,
    KIS_REAL_BASE_URL,
    TOKEN_CACHE_KEY,
)
from app.providers._token_cache import get_or_fetch_token
from app.providers.http_client import _get_client

logger = structlog.get_logger()

ACCOUNT_TOKEN_CACHE_KEY = "kis_token:account:{account_id}"  # nosec B105 — 캐시 키 템플릿


async def get_access_token(
    app_key: str,
    app_secret: str,
    *,
    is_mock: bool,
    cache,
    db,
    user_id: str,
    account_id: str | None = None,
    force_refresh: bool = False,
) -> str:
    """KIS 액세스 토큰 조회 — 캐시 → DB → KIS API 순으로 시도.

    account_id가 있으면 계좌별 토큰 캐시를 사용하고,
    없으면 기존 유저 레벨 캐시를 사용한다.
    """
    if account_id:
        cache_key = ACCOUNT_TOKEN_CACHE_KEY.format(account_id=account_id)
    else:
        cache_key = TOKEN_CACHE_KEY.format(user_id=user_id, mode="mock" if is_mock else "real")

    async def _query_token_row():
        from sqlalchemy import select

        from app.models.token import KisToken

        if account_id:
            result = await db.execute(
                select(KisToken).where(
                    KisToken.account_id == account_id,
                    KisToken.expires_at > datetime.now(UTC),
                )
            )
        else:
            result = await db.execute(
                select(KisToken).where(
                    KisToken.user_id == user_id,
                    KisToken.is_mock_mode == is_mock,
                    KisToken.account_id == None,  # noqa: E711
                    KisToken.expires_at > datetime.now(UTC),
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
    account_id: str | None = None,
) -> str:
    base_url = KIS_MOCK_BASE_URL if is_mock else KIS_REAL_BASE_URL
    client = _get_client(ssl_verify=not is_mock)
    resp = await client.post(
        f"{base_url}/oauth2/tokenP",
        json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
    )
    resp.raise_for_status()
    data = resp.json()

    if "access_token" not in data:
        logger.error("kis_token_issue_failed", user_id=user_id, account_id=account_id, response=data)
        detail = data.get("msg1") or data.get("error_description") or "알 수 없는 오류"
        raise ProviderTokenError(f"KIS 토큰 발급에 실패했습니다: {detail}")

    access_token: str = data["access_token"]
    expires_in: int = int(data.get("expires_in", 86400))
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

    # 캐시 저장
    if account_id:
        cache_key = ACCOUNT_TOKEN_CACHE_KEY.format(account_id=account_id)
    else:
        cache_key = TOKEN_CACHE_KEY.format(user_id=user_id, mode="mock" if is_mock else "real")
    ttl = expires_in - TOKEN_CACHE_TTL_BUFFER
    await cache.setex(cache_key, max(ttl, 60), access_token)

    # DB upsert
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.token import KisToken

    if account_id:
        stmt = pg_insert(KisToken).values(
            user_id=user_id,
            account_id=account_id,
            access_token=access_token,
            expires_at=expires_at,
            is_mock_mode=is_mock,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["account_id"],
            index_where=KisToken.account_id != None,  # noqa: E711
            set_={"access_token": access_token, "expires_at": expires_at},
        )
    else:
        stmt = pg_insert(KisToken).values(
            user_id=user_id,
            account_id=None,
            access_token=access_token,
            expires_at=expires_at,
            is_mock_mode=is_mock,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "is_mock_mode"],
            index_where=KisToken.account_id == None,  # noqa: E711
            set_={"access_token": access_token, "expires_at": expires_at},
        )
    await db.execute(stmt)
    await db.commit()

    logger.info("kis_token_issued", user_id=user_id, account_id=account_id, is_mock=is_mock)
    return access_token


async def promote_user_token_to_account(
    user_id: str,
    account_id: str,
    is_mock: bool,
    cache,
    db,
) -> bool:
    """계좌 등록 직전 자격증명 검증(verify-kis-credentials)으로 발급된 유저 레벨 토큰을
    방금 생성된 계좌의 account-scoped 토큰으로 승격한다.

    verify와 등록 직후 첫 동기화는 동일한 app_key/app_secret을 사용하지만 토큰 캐시 키가
    (user_id, mode) vs account_id로 서로 달라 재사용되지 않았다 — 그 결과 짧은 시간에 KIS
    토큰 발급 API를 2번 호출하게 되어 KIS의 발급 속도 제한에 걸려 등록 직후 첫 동기화가
    실패하는 문제가 있었다. 재사용 가능한 유저 레벨 토큰이 없으면 False를 반환하고,
    호출부는 평소대로 최초 동기화 시점에 새로 발급받는다.
    """
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.token import KisToken

    row = await db.scalar(
        select(KisToken).where(
            KisToken.user_id == user_id,
            KisToken.account_id == None,  # noqa: E711
            KisToken.is_mock_mode == is_mock,
            KisToken.expires_at > datetime.now(UTC),
        )
    )
    if row is None:
        return False

    stmt = pg_insert(KisToken).values(
        user_id=user_id,
        account_id=account_id,
        access_token=row.access_token,
        expires_at=row.expires_at,
        is_mock_mode=is_mock,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id"],
        index_where=KisToken.account_id != None,  # noqa: E711
        set_={"access_token": row.access_token, "expires_at": row.expires_at},
    )
    await db.execute(stmt)
    await db.commit()

    ttl = int((row.expires_at - datetime.now(UTC)).total_seconds() - TOKEN_CACHE_TTL_BUFFER)
    if ttl > 0:
        await cache.setex(ACCOUNT_TOKEN_CACHE_KEY.format(account_id=account_id), ttl, row.access_token)

    logger.info("kis_token_promoted_to_account", user_id=user_id, account_id=account_id, is_mock=is_mock)
    return True
