"""토스증권 Open API OAuth2 토큰 발급 — 캐시 → DB → API 순으로 시도.

토스는 전역 자격증명 개념이 없다(사용자가 계좌 단위로 client_id/client_secret 발급) —
`account_id`는 항상 필수. 토큰 수명은 약 1시간으로 짧아 `jobs/token_refresh.py` 배치
대신 `providers/_retry.with_token_refresh()`의 만료-감지 지연 갱신에 의존한다(키움과 동일).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from app.constants import TOKEN_CACHE_TTL_BUFFER
from app.providers._token_cache import get_or_fetch_token
from app.providers.http_client import _get_client
from app.services.credential_service import encrypt
from app.toss.client import TossApiError
from app.toss.constants import TOSS_BASE_URL, TOSS_TOKEN_CACHE_KEY, TOSS_TOKEN_PATH

logger = structlog.get_logger()

_DEFAULT_EXPIRES_IN = 3600  # 토스 access_token 기본 수명 ~1시간


async def get_access_token(
    client_id: str,
    client_secret: str,
    *,
    cache,
    db,
    user_id: str,
    account_id: str,
    force_refresh: bool = False,
) -> str:
    """토스 액세스 토큰 조회 — 캐시 → DB(TossToken) → 토스 API 순으로 시도."""
    cache_key = TOSS_TOKEN_CACHE_KEY.format(account_id=account_id)

    async def _query_token_row():
        from sqlalchemy import select

        from app.models.token import TossToken

        result = await db.execute(
            select(TossToken).where(
                TossToken.account_id == account_id,
                TossToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def _fetch():
        return await _fetch_and_store_token(
            client_id,
            client_secret,
            cache=cache,
            db=db,
            user_id=user_id,
            account_id=account_id,
        )

    return await get_or_fetch_token(cache_key, cache, force_refresh, TOKEN_CACHE_TTL_BUFFER, _query_token_row, _fetch)


async def _request_token(client_id: str, client_secret: str) -> tuple[str, int]:
    """토스 토큰 엔드포인트를 호출해 (access_token, expires_in)을 반환한다. 저장은 하지 않는다."""
    client = _get_client(ssl_verify=True)
    resp = await client.post(
        f"{TOSS_BASE_URL}{TOSS_TOKEN_PATH}",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            raise TossApiError(
                str(err.get("code") or "unknown"),
                str(err.get("message") or "토큰 발급 실패"),
                status_code=resp.status_code,
            )
        resp.raise_for_status()
    data = resp.json()
    # 표준 OAuth 응답 형태. 방어적으로 result 래핑도 허용.
    token_body = data.get("result") if isinstance(data.get("result"), dict) else data
    access_token = token_body.get("access_token")
    if not access_token:
        raise TossApiError("no-access-token", f"토스 토큰 발급 응답에 access_token이 없습니다: {data}")
    expires_in = int(token_body.get("expires_in") or _DEFAULT_EXPIRES_IN)
    return access_token, expires_in


async def _fetch_and_store_token(
    client_id: str,
    client_secret: str,
    *,
    cache,
    db,
    user_id: str,
    account_id: str,
) -> str:
    access_token, expires_in = await _request_token(client_id, client_secret)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

    cache_key = TOSS_TOKEN_CACHE_KEY.format(account_id=account_id)
    ttl = expires_in - TOKEN_CACHE_TTL_BUFFER
    await cache.setex(cache_key, max(ttl, 60), access_token)

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.token import TossToken

    encrypted_token = encrypt(access_token)
    stmt = pg_insert(TossToken).values(
        user_id=user_id,
        account_id=account_id,
        access_token=encrypted_token,
        expires_at=expires_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["account_id"],
        set_={"access_token": encrypted_token, "expires_at": expires_at},
    )
    await db.execute(stmt)
    await db.commit()

    logger.info("toss_token_issued", account_id=account_id)
    return access_token


async def verify_credentials(client_id: str, client_secret: str) -> None:
    """자격증명 유효성만 확인한다(계좌 생성/토큰 저장 없이). 실패 시 예외 전파."""
    await _request_token(client_id, client_secret)
